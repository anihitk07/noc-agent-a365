"""Create the Fabric IQ Foundry project connection (authType=UserEntraToken).

Neither `create_fabric_ontology.py` nor `create_fabric_data_agent.py` creates
a Foundry project connection -- they only touch Fabric-side resources
(workspace, lakehouse, ontology, Data Agent). `agent.py` resolves Fabric IQ
via `self._project_client.connections.get("fabric-iq-connection")` -- if that
connection doesn't exist, it's silently caught and skipped (Fabric IQ just
never appears in the toolbox, no error at startup). This was previously a
manual, undocumented-in-code ARM PUT step (see docs/DEPLOYMENT.md section 4c)
that had to be redone by hand after every fresh-RG deploy; this script
automates it, mirroring the same `UserEntraToken` idempotent-PUT pattern
`create_workiq_toolbox.py` uses for Work IQ.

Run this AFTER `create_fabric_data_agent.py` (needs FABRIC_DATA_AGENT_MCP_URL
in .env, which that script writes).

Required env (from `azd env get-values` / .env):
  AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_AI_ACCOUNT_NAME,
  AZURE_AI_PROJECT_NAME, AZURE_TENANT_ID, FABRIC_DATA_AGENT_MCP_URL
"""

import os
import time
from pathlib import Path

import httpx
from azure.identity import AzureDeveloperCliCredential
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parents[1]
ENV_PATH = REPO_ROOT / ".env"
ARM_API_VERSION = "2025-06-01"
CONNECTION_NAME = "fabric-iq-connection"
# Must match the scope consented for the agent-user identity (see
# docs/DEPLOYMENT.md section 4b) so the OBO exchange mints a Fabric-scoped
# token for this connection's identity passthrough.
FABRIC_AUDIENCE = "https://api.fabric.microsoft.com"

load_dotenv(ENV_PATH, override=True)


def require_env(name: str) -> str:
    """Return a required environment variable or fail with a useful message."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required to create the Fabric IQ connection.")
    return value


def log_message(message: str) -> None:
    """Print a progress message immediately (unbuffered)."""
    print(message, flush=True)


def put_fabric_iq_connection(
    *,
    subscription_id: str,
    resource_group: str,
    account_name: str,
    project_name: str,
    tenant_id: str,
    mcp_url: str,
) -> None:
    """Create/update the Fabric IQ project connection with authType=UserEntraToken."""
    credential = AzureDeveloperCliCredential(tenant_id=tenant_id)
    try:
        arm_token = credential.get_token("https://management.azure.com/.default").token
    finally:
        credential.close()

    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        f"/projects/{project_name}/connections/{CONNECTION_NAME}"
        f"?api-version={ARM_API_VERSION}"
    )
    existing = httpx.get(url, headers={"Authorization": f"Bearer {arm_token}"}, timeout=60)
    if existing.status_code == 200:
        props = existing.json().get("properties", {})
        if (
            props.get("authType") == "UserEntraToken"
            and props.get("target") == mcp_url
            and props.get("audience") == FABRIC_AUDIENCE
        ):
            log_message(
                f"[OK] Foundry connection '{CONNECTION_NAME}' already exists with the correct "
                "UserEntraToken configuration and current Fabric Data Agent URL -- skipping PUT."
            )
            return
        log_message(
            f"[..] Foundry connection '{CONNECTION_NAME}' exists but target/authType is stale "
            "(likely a re-created Fabric Data Agent) -- refreshing it."
        )

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
    # NB: the account-rp ARM front-end for this preview connections API is
    # flaky and intermittently returns a bare 500 InternalServerError with no
    # retry-after -- a plain retry with a short backoff clears it (same
    # behavior documented in create_workiq_toolbox.py).
    last_error: Exception | None = None
    response: httpx.Response | None = None
    for attempt in range(5):
        response = httpx.put(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {arm_token}"},
            timeout=120,
        )
        if response.status_code < 500:
            break
        last_error = httpx.HTTPStatusError(
            f"{response.status_code} on attempt {attempt + 1}", request=response.request, response=response
        )
        log_message(f"  ...transient {response.status_code}, retrying in 5s ({attempt + 1}/5)")
        time.sleep(5)
    assert response is not None
    if response.status_code >= 500:
        raise last_error or RuntimeError("Fabric IQ connection PUT failed after retries.")
    response.raise_for_status()
    auth_type = response.json()["properties"]["authType"]
    log_message(f"[OK] Foundry connection '{CONNECTION_NAME}' created/updated (authType={auth_type}).")


def main() -> None:
    subscription_id = require_env("AZURE_SUBSCRIPTION_ID")
    resource_group = require_env("AZURE_RESOURCE_GROUP")
    account_name = require_env("AZURE_AI_ACCOUNT_NAME")
    project_name = require_env("AZURE_AI_PROJECT_NAME")
    tenant_id = require_env("AZURE_TENANT_ID")
    mcp_url = require_env("FABRIC_DATA_AGENT_MCP_URL")

    log_message("Creating Fabric IQ Foundry connection (authType=UserEntraToken)...")
    put_fabric_iq_connection(
        subscription_id=subscription_id,
        resource_group=resource_group,
        account_name=account_name,
        project_name=project_name,
        tenant_id=tenant_id,
        mcp_url=mcp_url,
    )

    log_message(
        "\nDone. agent.py resolves Fabric IQ by looking up this "
        "'fabric-iq-connection' project connection directly "
        "(FABRIC_IQ_CONNECTION_NAME env var, default 'fabric-iq-connection')."
    )


if __name__ == "__main__":
    main()
