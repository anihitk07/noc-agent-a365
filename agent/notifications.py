# Copyright (c) Microsoft. All rights reserved.

"""Outbound, multi-persona incident-lifecycle email notifications.

Answers the Accenture review gap: the agent could *receive* email (see
`agent.py`'s EMAIL_NOTIFICATION handling) but had no path to *originate*
one. This module is the reference implementation for that outbound path --
see docs/OUTBOUND_NOTIFICATIONS.md for the full design, permission model,
and its current limitations.

Call chain: NocAgent.broadcast_incident_update() -> broadcast() (this file)
-> one Graph `sendMail` call per persona, using a Graph-scoped OBO token
(delegated `Mail.Send`) exchanged the same way Fabric IQ/Work IQ already
exchange theirs -- see agent.py's `_exchange_user_token`.

ponytail: recipients are a static env-var-driven allow-list, not a real
stakeholder directory; each persona gets ONE template (not per-lifecycle-
stage variants); there's no delivery retry/dedup. Upgrade path: back
PERSONAS recipients with the Fabric IQ Service/Stakeholder ontology entities
once this graduates past PoC (the data already exists in Fabric IQ).
"""

import logging
import os
import string
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "runbooks" / "customer_communication_template.md"

# One persona = one audience = one recipient list + one template section
# heading (matched literally against "### Persona: <name>" in the template
# file) + an allow-list of which {Variable} placeholders that audience may
# see (enforced by simply omitting any other key from the render context).
PERSONAS: dict[str, dict] = {
    "executives": {
        "recipients_env": "NOTIFY_EXECUTIVES_EMAILS",
        "allowed_fields": {
            "LifecycleStage", "ServiceName", "CustomerFacingImpactCount",
            "CurrentStatus", "BusinessImpactSummary", "ETR",
        },
    },
    "technical": {
        "recipients_env": "NOTIFY_TECHNICAL_EMAILS",
        "allowed_fields": {
            "LifecycleStage", "ServiceName", "IncidentId", "RootCauseSummary",
            "TelemetrySummary", "ActionSummary", "RunbookReference",
        },
    },
    "venue": {
        "recipients_env": "NOTIFY_VENUE_EMAILS",
        "allowed_fields": {"LifecycleStage", "VenueName", "VenueImpactDescription", "ETR"},
    },
    "partners": {
        "recipients_env": "NOTIFY_PARTNER_EMAILS",
        "allowed_fields": {"LifecycleStage", "ServiceId", "ServiceName", "IncidentId", "SLAStatus"},
    },
}


class _SafeDict(dict):
    """Leaves unknown/omitted {Placeholder} tokens untouched instead of raising KeyError."""

    def __missing__(self, key):
        return "{" + key + "}"


def _extract_persona_section(persona: str) -> tuple[str, str]:
    """Pull the `### Persona: <persona>` subject/body out of the template file.

    Uses the same single-brace {Variable} convention as the rest of
    customer_communication_template.md -- no new templating syntax.
    """
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    marker = f"### Persona: {persona}\n"
    start = text.index(marker) + len(marker)
    end = text.find("\n### ", start)
    section = text[start : end if end != -1 else None]

    subject_line = next(line for line in section.splitlines() if line.startswith("**Subject**:"))
    subject = subject_line.split("**Subject**:", 1)[1].strip()

    body_marker = "**Body**:\n\n"
    body = section[section.index(body_marker) + len(body_marker):].strip()
    return subject, body


def render_persona_message(persona: str, context: dict) -> tuple[str, str]:
    """Render (subject, body) for one persona, restricted to its allowed fields."""
    allowed = PERSONAS[persona]["allowed_fields"]
    safe_context = _SafeDict({k: v for k, v in context.items() if k in allowed})
    subject, body = _extract_persona_section(persona)
    return (
        string.Formatter().vformat(subject, (), safe_context),
        string.Formatter().vformat(body, (), safe_context),
    )


def _recipients_for(persona: str) -> list[str]:
    raw = os.getenv(PERSONAS[persona]["recipients_env"], "")
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


async def send_persona_email(persona: str, context: dict, graph_token: str) -> bool:
    """Send one persona's rendered email via Graph `sendMail`, on the agentic mailbox's own behalf."""
    recipients = _recipients_for(persona)
    if not recipients:
        logger.info("⏭️ Skipping persona '%s' -- no recipients configured (%s unset)", persona, PERSONAS[persona]["recipients_env"])
        return False

    subject, body = render_persona_message(persona, context)
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in recipients],
        },
        "saveToSentItems": True,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            GRAPH_SEND_MAIL_URL,
            headers={"Authorization": f"Bearer {graph_token}"},
            json=payload,
        )
    if response.status_code == 202:
        logger.info("✅ Sent '%s' notification to %d recipient(s)", persona, len(recipients))
        return True
    logger.error("❌ Graph sendMail failed for persona '%s': %s %s", persona, response.status_code, response.text)
    return False


async def broadcast(context: dict, graph_token: str, personas: Optional[list[str]] = None) -> dict[str, bool]:
    """Send the incident-lifecycle update to every requested persona (default: all four)."""
    targets = personas or list(PERSONAS)
    return {persona: await send_persona_email(persona, context, graph_token) for persona in targets}


def _demo() -> None:
    """Self-check: template parsing + persona field-restriction, no network needed."""
    sample_context = {
        "LifecycleStage": "escalation", "ServiceName": "Sydney-Melbourne Fibre",
        "CustomerFacingImpactCount": "12", "CurrentStatus": "Mitigating",
        "BusinessImpactSummary": "Enterprise VPN customers degraded", "ETR": "45 min",
        "IncidentId": "INC-1", "RootCauseSummary": "Fibre cut", "TelemetrySummary": "n/a",
        "ActionSummary": "Rerouting", "RunbookReference": "fibre_cut_runbook.md",
        "VenueName": "Sydney DC1", "VenueImpactDescription": "Backup link active",
        "ServiceId": "VPN-1", "SLAStatus": "At risk",
    }
    for persona in PERSONAS:
        subject, body = render_persona_message(persona, sample_context)
        assert subject and body, f"{persona}: empty render"
        assert "{" not in subject, f"{persona}: unrendered placeholder in subject: {subject}"
        # Fields NOT in this persona's allow-list must never leak into its email.
        leaked = [f for f in sample_context if f not in PERSONAS[persona]["allowed_fields"] and f in body]
        assert not leaked, f"{persona}: leaked restricted fields {leaked}"
    print("PASS: notifications.py self-check passed for all", len(PERSONAS), "personas")


if __name__ == "__main__":
    _demo()
