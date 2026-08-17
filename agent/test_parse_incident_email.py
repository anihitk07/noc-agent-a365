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

    # Body-first-line tag (no subject available at all) -- the PRIMARY
    # real-world convention: live testing showed the A365 email connector's
    # "message" activity delivers no subject, only channel_data =
    # {"tenant": {...}, "productContext": "email"}. See docs/OUTBOUND_NOTIFICATIONS.md.
    body_tagged = parse_incident_email(
        "",
        "[INCIDENT:ESCALATION]\nSite: SYD-CORE-04\nSeverity: SEV1\nETA: 45 minutes",
    )
    _check("body-first-line tag is parsed (no subject)", body_tagged is not None)
    _check("body-tag lifecycle stage extracted", body_tagged["LifecycleStage"] == "ESCALATION")
    _check("body-tag Site field parsed", body_tagged["Site"] == "SYD-CORE-04")

    # Blank lines before the body tag are tolerated.
    body_tagged_padded = parse_incident_email(
        "",
        "\n\n[INCIDENT:MITIGATION]\nOwner: NOC-Team",
    )
    _check(
        "blank lines before body tag tolerated",
        body_tagged_padded is not None and body_tagged_padded["LifecycleStage"] == "MITIGATION",
    )

    # Untagged body and no subject -> None.
    untagged_body = parse_incident_email("", "Just a regular question, no tag here.")
    _check("untagged body with no subject returns None", untagged_body is None)

    print("PASS: test_parse_incident_email.py self-check passed (9 cases)")


if __name__ == "__main__":
    main()
