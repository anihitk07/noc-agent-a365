"""Standalone self-check for agent.SPECIALIST_AGENTS (the agents-as-tools routing map).

Not a pytest suite -- run directly: `python agent/test_specialist_routing.py`.
Sets dummy values for the two hard-required env vars agent.py reads at import
time (FOUNDRY_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT_NAME) so this check
can run without a live Foundry deployment or a populated .env file.

Verifies the static routing table that agents-as-tools orchestration depends
on: each IQ key maps to the right persisted agent name, and to the right
credential kind (service identity vs. calling-user OAuth identity
passthrough) per the auth-type matrix in agent.py's module docstring.
"""

import os

os.environ.setdefault("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid/api/projects/dummy")
os.environ.setdefault("AZURE_AI_MODEL_DEPLOYMENT_NAME", "dummy-model")

from agent import SPECIALIST_AGENTS  # noqa: E402  (import after env setup, by design)


def _check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {label}")
    assert condition, label


def main():
    _check("all 4 IQ surfaces are present", set(SPECIALIST_AGENTS) == {"foundry_iq", "fabric_iq", "web_iq", "work_iq"})

    knowledge_agent, knowledge_needs_user = SPECIALIST_AGENTS["foundry_iq"]
    _check("foundry_iq -> noc-knowledge-agent", knowledge_agent == "noc-knowledge-agent")
    _check("foundry_iq uses the service identity (no UserEntraToken connection)", knowledge_needs_user is False)

    topology_agent, topology_needs_user = SPECIALIST_AGENTS["fabric_iq"]
    _check("fabric_iq -> noc-topology-agent", topology_agent == "noc-topology-agent")
    _check("fabric_iq requires the calling user's OAuth identity (UserEntraToken)", topology_needs_user is True)

    threatintel_agent, threatintel_needs_user = SPECIALIST_AGENTS["web_iq"]
    _check("web_iq -> noc-threatintel-agent", threatintel_agent == "noc-threatintel-agent")
    _check("web_iq uses the service identity (CustomKeys connection)", threatintel_needs_user is False)

    comms_agent, comms_needs_user = SPECIALIST_AGENTS["work_iq"]
    _check("work_iq -> noc-comms-agent", comms_agent == "noc-comms-agent")
    _check("work_iq requires the calling user's OAuth identity (UserEntraToken)", comms_needs_user is True)

    print("PASS: test_specialist_routing.py self-check passed (10 cases)")


if __name__ == "__main__":
    main()
