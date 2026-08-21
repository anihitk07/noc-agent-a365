"""Refresh all IQ connections/toolbox after a fresh provision or Data Agent
recreation.

This is the single entry point for the manual steps that had to be redone by
hand after the last fresh-RG deploy (fabric-iq-connection + WorkIQ never
existing, causing `fabric_iq`/`work_iq` tools to be silently disabled -- see
docs/TROUBLESHOOTING.md). Foundry IQ's `kb-mcp-connection` and Web IQ's
`web-iq-connection` are already provisioned declaratively by
infra/core/ai/ai-project.bicep at `azd provision` time and do NOT need this
script; only the two connections with no Bicep resource type (Fabric IQ,
Work IQ) do.

Run this:
  - Once after every `azd provision`/`azd up` against a fresh resource group
    (wired as the `postprovision` hook in azure.yaml -- see there).
  - Any time `create_fabric_data_agent.py` is re-run and prints a NEW
    FABRIC_DATA_AGENT_MCP_URL (e.g. the Data Agent was deleted/recreated),
    since fabric-iq-connection's `target` must track that URL.
  - After running `az webapp restart`/`azd deploy`, if the app logs
    "Could not resolve connection '<name>' (<key> tool disabled)" --
    that means a connection this app expects doesn't exist yet.

Idempotent: safe to run repeatedly; each step no-ops if already correct.
"""

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
PYTHON = sys.executable

STEPS = [
    ("Fabric IQ: create/refresh the Fabric Data Agent", "create_fabric_data_agent.py"),
    ("Fabric IQ: create/refresh the Foundry project connection", "create_fabric_iq_connection.py"),
    ("Work IQ: create/refresh the Foundry project connection", "create_workiq_toolbox.py"),
]


def main() -> None:
    for description, script_name in STEPS:
        print(f"\n=== {description} ({script_name}) ===", flush=True)
        result = subprocess.run([PYTHON, str(SCRIPTS_DIR / script_name)])
        if result.returncode != 0:
            print(
                f"\n[FAILED] {script_name} exited with code {result.returncode} -- "
                "stopping here so the failure isn't masked by later steps.",
                file=sys.stderr,
            )
            sys.exit(result.returncode)

    print(
        "\n=== Done ===\n"
        "All 4 IQ connections (kb-mcp-connection, web-iq-connection, "
        "fabric-iq-connection, WorkIQ) should now resolve. Restart the app "
        "(`az webapp restart`) so agent.py's initialize() re-reads them and "
        "rebuilds the toolbox with all 4 tools.",
        flush=True,
    )


if __name__ == "__main__":
    main()
