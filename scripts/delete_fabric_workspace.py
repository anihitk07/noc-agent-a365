"""Delete the Fabric workspace (and everything in it) once the Azure resource group teardown is triggered.

Fabric objects (workspace, lakehouse, ontology, Data Agent, Eventhouse + KQL database) are
tenant-level Fabric items, not ARM resources -- `az group delete` never touches them, so they
keep running (and billing the capacity) unless deleted separately. Deleting the workspace
itself cascades to every item inside it, so this is the one call needed; no per-item
lakehouse/ontology/eventhouse deletion is required.

Usage:
  python delete_fabric_workspace.py           # prints what would be deleted, does nothing
  python delete_fabric_workspace.py --yes      # actually deletes the workspace

Environment variables (from the repo-root .env):
  FABRIC_WORKSPACE_ID   - Existing Fabric workspace GUID to delete (required)
  FABRIC_TENANT_ID      - Required Microsoft Entra tenant ID for Fabric auth
"""

import argparse
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity import AzureDeveloperCliCredential
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=SyntaxWarning, module=r"microsoft_fabric_api\..*")

from microsoft_fabric_api import FabricClient  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
load_dotenv(REPO_ROOT / ".env", override=True)

FABRIC_TENANT_ID = os.getenv("FABRIC_TENANT_ID", "").strip().strip("'\"")
WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "").strip().strip("'\"")
WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "NOCTopologyWorkspace").strip().strip("'\"")


def log_message(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def get_fabric_client() -> FabricClient:
    if not FABRIC_TENANT_ID:
        raise RuntimeError("FABRIC_TENANT_ID is required for Fabric authentication.")
    credential = AzureDeveloperCliCredential(tenant_id=FABRIC_TENANT_ID)
    return FabricClient(credential)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes", action="store_true", help="Actually delete the workspace (default: dry-run)."
    )
    return parser


def self_check() -> None:
    # ponytail: the only real logic here is "is --yes wired up" -- everything else is one SDK
    # call, not worth mocking a whole Fabric client for.
    parser = build_arg_parser()
    assert parser.parse_args([]).yes is False
    assert parser.parse_args(["--yes"]).yes is True


def main() -> None:
    self_check()
    args = build_arg_parser().parse_args()

    if not WORKSPACE_ID:
        log_message("FABRIC_WORKSPACE_ID is not set in .env -- nothing to delete.")
        return

    client = get_fabric_client()
    try:
        workspace = client.core.workspaces.get_workspace(WORKSPACE_ID)
        display_name = workspace.display_name
    except ResourceNotFoundError:
        log_message(f"Workspace {WORKSPACE_ID} already gone -- nothing to do.")
        return

    if not args.yes:
        log_message(
            f"DRY RUN -- would delete Fabric workspace '{display_name}' ({WORKSPACE_ID}) "
            f"and everything in it (lakehouse, ontology, Data Agent, Eventhouse + KQL DB). "
            f"Re-run with --yes to actually delete it."
        )
        return

    log_message(f"Deleting Fabric workspace '{display_name}' ({WORKSPACE_ID}) ...")
    client.core.workspaces.delete_workspace(WORKSPACE_ID)
    log_message("Workspace deleted.")


if __name__ == "__main__":
    try:
        main()
    except HttpResponseError as error:
        log_message(f"ERROR: Fabric API request failed: {error}")
        sys.exit(1)
    except Exception as error:  # noqa: BLE001
        log_message(f"ERROR: {error}")
        sys.exit(1)
