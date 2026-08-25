"""Create the Fabric RTI Foundry project connection (authType=UserEntraToken).

`noc-incident-agent` will use a direct `MCPTool(project_connection_id=...)`
to the Eventhouse/KQL MCP endpoint, not a toolbox hop (see
docs/TROUBLESHOOTING.md B2-c). This script creates that underlying Foundry
project connection and writes its resolved connection id back to the repo
`.env` as `FABRIC_RTI_CONNECTION_ID`.

Required env (from `azd env get-values` / `.env`):
  AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_AI_ACCOUNT_NAME,
  AZURE_AI_PROJECT_NAME, AZURE_TENANT_ID, FABRIC_RTI_MCP_URL
"""

import os
import time
from pathlib import Path

import httpx
from azure.identity import AzureDeveloperCliCredential
from dotenv import load_dotenv, set_key

REPO_ROOT = Path(__file__).parents[1]
ENV_PATH = REPO_ROOT / ".env"
ARM_API_VERSION = "2025-06-01"
CONNECTION_NAME = "fabric-rti-connection"
FABRIC_AUDIENCE = "https://api.fabric.microsoft.com"

load_dotenv(ENV_PATH, override=True)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required to create the Fabric RTI connection.")
    return value


def log_message(message: str) -> None:
    print(message, flush=True)


def write_connection_id(connection_id: str) -> None:
    ENV_PATH.touch()
    set_key(ENV_PATH, "FABRIC_RTI_CONNECTION_ID", connection_id, quote_mode="never")


def put_rti_connection(
    *,
    subscription_id: str,
    resource_group: str,
    account_name: str,
    project_name: str,
    tenant_id: str,
    mcp_url: str,
) -> dict:
    credential = AzureDeveloperCliCredential(tenant_id=tenant_id)
    try:
        arm_token = credential.get_token("https://management.azure.com/.default").token
    finally:
        credential.close()

    headers = {"Authorization": f"Bearer {arm_token}"}
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        f"/projects/{project_name}/connections/{CONNECTION_NAME}"
        f"?api-version={ARM_API_VERSION}"
    )

    existing = httpx.get(url, headers=headers, timeout=60)
    if existing.status_code == 200:
        props = existing.json().get("properties", {})
        if (
            props.get("authType") == "UserEntraToken"
            and props.get("target") == mcp_url
            and props.get("audience") == FABRIC_AUDIENCE
        ):
            log_message(
                f"[OK] Foundry connection '{CONNECTION_NAME}' already exists with the correct "
                "UserEntraToken configuration and current Fabric RTI MCP URL -- skipping PUT."
            )
            return existing.json()
        log_message(f"[..] Foundry connection '{CONNECTION_NAME}' exists but is stale -- refreshing it.")

    payload = {
        "properties": {
            "authType": "UserEntraToken",
            "category": "RemoteTool",
            "target": mcp_url,
            "audience": FABRIC_AUDIENCE,
            "group": "GenericProtocol",
            "isSharedToAll": False,
            "metadata": {"type": "custom_MCP"},
        }
    }
    # ponytail: plain retry on 500 is enough here; the preview connections API
    # flakes transiently, and anything smarter would just be more code.
    last_error: Exception | None = None
    response: httpx.Response | None = None
    for attempt in range(5):
        response = httpx.put(url, json=payload, headers=headers, timeout=120)
        if response.status_code < 500:
            break
        last_error = httpx.HTTPStatusError(
            f"{response.status_code} on attempt {attempt + 1}",
            request=response.request,
            response=response,
        )
        log_message(f"  ...transient {response.status_code}, retrying in 5s ({attempt + 1}/5)")
        time.sleep(5)
    assert response is not None
    if response.status_code >= 500:
        raise last_error or RuntimeError("Fabric RTI connection PUT failed after retries.")
    response.raise_for_status()
    return response.json()


def main() -> None:
    subscription_id = require_env("AZURE_SUBSCRIPTION_ID")
    resource_group = require_env("AZURE_RESOURCE_GROUP")
    account_name = require_env("AZURE_AI_ACCOUNT_NAME")
    project_name = require_env("AZURE_AI_PROJECT_NAME")
    tenant_id = require_env("AZURE_TENANT_ID")
    mcp_url = require_env("FABRIC_RTI_MCP_URL")

    log_message("Creating Fabric RTI Foundry connection (authType=UserEntraToken)...")
    body = put_rti_connection(
        subscription_id=subscription_id,
        resource_group=resource_group,
        account_name=account_name,
        project_name=project_name,
        tenant_id=tenant_id,
        mcp_url=mcp_url,
    )

    connection_id = body["id"]
    auth_type = body["properties"]["authType"]
    write_connection_id(connection_id)
    log_message(f"[OK] Foundry connection '{CONNECTION_NAME}' ready ({connection_id}, authType={auth_type}).")


if __name__ == "__main__":
    main()
