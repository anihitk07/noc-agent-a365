"""Standalone self-check for agent.parse_incident_email().

Not a pytest suite -- run directly: `python agent/test_parse_incident_email.py`.
Sets dummy values for the two hard-required env vars agent.py reads at import
time (FOUNDRY_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT_NAME) so this check
can run without a live Foundry deployment or a populated .env file.
"""

import os

os.environ.setdefault("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid/api/projects/dummy")
os.environ.setdefault("AZURE_AI_MODEL_DEPLOYMENT_NAME", "dummy-model")

from agent import parse_incident_email  # noqa: E402  (import after env setup, by design)


def _check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {label}")
    assert condition, label


def main():
    # Tagged subject + well-formed body -> parsed dict with lifecycle stage.
    result = parse_incident_email(
        "[INCIDENT:ESCALATION] Sydney fibre cut",
        "<p>Site: SYD-CORE-04</p>\nSeverity: SEV1\nETA: 45 minutes",
    )
    _check("tagged subject is parsed (not None)", result is not None)
    _check("lifecycle stage extracted", result["LifecycleStage"] == "ESCALATION")
    _check("HTML-wrapped field parsed", result["Site"] == "SYD-CORE-04")
    _check("plain field parsed", result["Severity"] == "SEV1")
    _check("field with spaces in value parsed", result["ETA"] == "45 minutes")

    # Untagged subject -> None (falls through to conversational handling).
    plain = parse_incident_email("Question about last night's outage", "Can you summarize?")
    _check("untagged subject returns None", plain is None)

    # Case-sensitivity: lowercase tag should NOT match (convention is upper-case).
    lowercase_tag = parse_incident_email("[incident:detection] test", "Site: X")
    _check("lowercase tag does not match (by design)", lowercase_tag is None)

    # Leading whitespace before the tag is tolerated.
    padded = parse_incident_email("   [INCIDENT:MITIGATION] update", "Owner: NOC-Team")
    _check("leading whitespace before tag tolerated", padded is not None and padded["LifecycleStage"] == "MITIGATION")

    print("PASS: test_parse_incident_email.py self-check passed (5 cases)")


if __name__ == "__main__":
    main()
