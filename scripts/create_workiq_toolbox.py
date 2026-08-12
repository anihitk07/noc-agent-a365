"""Create the Work IQ Foundry connection and toolbox (Work IQ).

Work IQ has no dedicated SDK connection class and is not automatable via the
Foundry portal in a headless-safe way: the portal's "Add connection" wizard
defaults new Work IQ connections to `authType: OAuth2`, which requires
interactive browser consent per call. That works fine in the Foundry
playground (a human is present to click "Allow") but fails in Teams/A365 --
a non-interactive caller -- with a repeating `oauth_consent_request` loop, and
the agent silently falls back to hallucinating an answer instead of calling
Work IQ. See docs/DEPLOYMENT.md and iq-samples/refund-agent-a365's
TROUBLESHOOTING.md for the full writeup.

The fix is to create the connection directly against ARM with
`authType: UserEntraToken` (OBO identity passthrough: Foundry forwards the
caller's own Entra token and mints a Work IQ-scoped token for it, no client
secret or app registration required -- unlike iqdeepdive's
create-toolbox-workiq.py, which additionally registers its own Entra app and
grants tenant admin consent for an OAuth2 connection; that machinery is not
needed here because UserEntraToken has no credential of its own to provision).

Steps:
  1. PUT the Foundry project connection "WorkIQ" with authType=UserEntraToken
     (idempotent -- PUT again to update if it already exists).
  2. Create a toolbox version containing a WorkIQPreviewToolboxTool bound to
     that connection, and promote it to the default version.

Required env (from `azd env get-values` / .env):
  AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_AI_ACCOUNT_NAME,
  AZURE_AI_PROJECT_NAME, AZURE_TENANT_ID, AZURE_AI_PROJECT_ENDPOINT (or
  FOUNDRY_PROJECT_ENDPOINT)

Optional env:
  WORKIQ_TOOLBOX_NAME (default "work-iq-tools", must match
  CUSTOM_FOUNDRY_WORKIQ_TOOLBOX_NAME / agent/agent.py's WORKIQ_TOOLBOX_NAME)
"""

import os
import time
from pathlib import Path

import httpx
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import WorkIQPreviewToolboxTool
from azure.identity import AzureDeveloperCliCredential
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parents[1]
ENV_PATH = REPO_ROOT / ".env"
ARM_API_VERSION = "2025-06-01"
CONNECTION_NAME = "WorkIQ"
# Unified Work IQ resource appId -- api://workiq.svc.cloud.microsoft, scope
# WorkIQAgent.Ask. UserEntraToken stores no credential; only this audience
# (which token to mint via OBO) and the MCP target matter.
WORKIQ_AUDIENCE = "fdcc1f02-fc51-4226-8753-f668596af7f7"
WORKIQ_TARGET = "https://workiq.svc.cloud.microsoft/mcp"

load_dotenv(ENV_PATH, override=True)


def require_env(name: str) -> str:
    """Return a required environment variable or fail with a useful message."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required to create the Work IQ toolbox.")
    return value


def log_message(message: str) -> None:
    """Print a progress message immediately (unbuffered)."""
    print(message, flush=True)


def put_workiq_connection(
    *, subscription_id: str, resource_group: str, account_name: str, project_name: str, tenant_id: str
) -> None:
    """Create/update the Work IQ project connection with authType=UserEntraToken."""
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
            and props.get("target") == WORKIQ_TARGET
            and props.get("audience") == WORKIQ_AUDIENCE
        ):
            log_message(
                f"[OK] Foundry connection '{CONNECTION_NAME}' already exists with the correct "
                "UserEntraToken configuration -- skipping PUT (the account-rp preview "
                "connections API is flaky on repeat PUTs to an existing connection)."
            )
            return
    payload = {
        "properties": {
            "authType": "UserEntraToken",
            "category": "RemoteTool",
            "target": WORKIQ_TARGET,
            "audience": WORKIQ_AUDIENCE,
            "group": "GenericProtocol",
            "isSharedToAll": False,
            "metadata": {"type": "custom_MCP"},
        }
    }
    # NB: the account-rp ARM front-end for this preview connections API is
    # flaky and intermittently returns a bare 500 InternalServerError with no
    # retry-after -- a plain retry with a short backoff clears it.
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
        raise last_error or RuntimeError("Work IQ connection PUT failed after retries.")
    response.raise_for_status()
    auth_type = response.json()["properties"]["authType"]
    log_message(f"[OK] Foundry connection '{CONNECTION_NAME}' created/updated (authType={auth_type}).")


def create_toolbox(*, project_endpoint: str, tenant_id: str, toolbox_name: str) -> None:
    """Create and promote a toolbox version containing the Work IQ tool."""
    credential = AzureDeveloperCliCredential(tenant_id=tenant_id)
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    version = project.toolboxes.create_version(
        name=toolbox_name,
        tools=[
            WorkIQPreviewToolboxTool(
                name="work_iq",
                description=(
                    "Answer questions about the signed-in NOC on-call engineer's "
                    "Microsoft 365 mail, Teams chats/bridge threads, meetings, "
                    "and change-approval documents."
                ),
                project_connection_id=CONNECTION_NAME,
            )
        ],
        description="Microsoft 365 work context tools for the NOC agent (Work IQ).",
    )
    project.toolboxes.update(name=toolbox_name, default_version=version.version)
    log_message(f"[OK] Toolbox '{toolbox_name}' created; default version set to {version.version}.")


def main() -> None:
    subscription_id = require_env("AZURE_SUBSCRIPTION_ID")
    resource_group = require_env("AZURE_RESOURCE_GROUP")
    account_name = require_env("AZURE_AI_ACCOUNT_NAME")
    project_name = require_env("AZURE_AI_PROJECT_NAME")
    tenant_id = require_env("AZURE_TENANT_ID")
    project_endpoint = (
        os.getenv("AZURE_AI_PROJECT_ENDPOINT", "").strip()
        or os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    )
    if not project_endpoint:
        raise RuntimeError("AZURE_AI_PROJECT_ENDPOINT or FOUNDRY_PROJECT_ENDPOINT is required.")
    toolbox_name = os.getenv("WORKIQ_TOOLBOX_NAME", "work-iq-tools").strip()

    log_message("Creating Work IQ Foundry connection (authType=UserEntraToken)...")
    put_workiq_connection(
        subscription_id=subscription_id,
        resource_group=resource_group,
        account_name=account_name,
        project_name=project_name,
        tenant_id=tenant_id,
    )

    log_message(f"Creating Work IQ toolbox '{toolbox_name}'...")
    create_toolbox(project_endpoint=project_endpoint, tenant_id=tenant_id, toolbox_name=toolbox_name)

    log_message(
        "\nDone. Set CUSTOM_FOUNDRY_WORKIQ_TOOLBOX_NAME="
        f"{toolbox_name} in the App Service app settings if it differs from the "
        "agent.py default ('work-iq-tools')."
    )


if __name__ == "__main__":
    main()
