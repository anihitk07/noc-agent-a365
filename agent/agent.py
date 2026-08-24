# Copyright (c) Microsoft. All rights reserved.

"""
NOC Agent — MAF orchestrator delegating to four persisted Foundry Prompt Agents.

**Multi-agent design** (see docs/ARCHITECTURE.md for the full rationale and
migration history from the single-agent/single-toolbox design). Each IQ
surface is now its own **persisted Foundry Prompt Agent**
(`project.agents.create_version(...)`, provisioned by
`scripts/create_foundry_agents.py`), holding exactly one native
`MCPTool(project_connection_id=...)` pointed directly at its own project
Connection -- no toolbox layer needed, since nothing is shared across these
agents:
  - `noc-knowledge-agent`   -> Foundry IQ  (runbooks/tickets/specs KB)
  - `noc-topology-agent`    -> Fabric IQ   (live network topology graph)
  - `noc-threatintel-agent` -> Web IQ      (public vendor/carrier advisories)
  - `noc-comms-agent`       -> Work IQ     (Teams/Outlook: on-call, bridge chatter)

This app runs ONE ephemeral, in-process MAF `Agent` (the "orchestrator"),
always authenticated as the app's own SERVICE identity, with each specialist
exposed as a plain Python tool function (**agents-as-tools**). The
orchestrator's own model performs the routing across specialists exactly as
the old single-agent design routed across IQ tools -- only the granularity of
what's being routed to has changed (a whole persisted agent turn, not a raw
MCP tool call).

Each specialist tool function calls its persisted agent via
`AIProjectClient(allow_preview=True).get_openai_client(agent_name=...)`,
which binds an `openai.OpenAI` client directly to that agent's own endpoint
(`{project_endpoint}/agents/{name}/endpoint/protocols/openai`) -- no
`extra_body={"agent_reference": ...}` needed, the SDK does that internally.

Auth-type matrix (unchanged from the single-agent design):
  - Foundry IQ (knowledge base MCP)   -> project connection, service identity
  - Web IQ (web MCP)                  -> project connection, CustomKeys (x-apikey)
  - Fabric IQ (Fabric Data Agent MCP) -> project connection, UserEntraToken (OBO identity passthrough)
  - Work IQ (Microsoft 365 toolbox)   -> project connection, UserEntraToken (OBO identity passthrough)

**What changed with persisted Prompt Agents vs. the old ephemeral design**:
tool execution moves server-side into Agent Service, so identity passthrough
for the two `UserEntraToken` surfaces becomes Agent-Service-managed **OAuth
identity passthrough**: the credential used to construct the per-call
`AIProjectClient`/OpenAI client for `noc-topology-agent`/`noc-comms-agent`
must be the CALLING USER's OBO token (`_StaticTokenCredential`, below), not
the service credential -- Agent Service attributes the stored OAuth consent
grant to whichever identity signed the call. Consent surfaces as an
`oauth_consent_request` item inside a normal (200 OK) `response.output`, NOT
as a raised MCP error (that was the old client-side-MCP consent shape; see
`_extract_oauth_consent_url`, replacing the old `_extract_a2a_consent_url`).
Every user who calls `noc-topology-agent`/`noc-comms-agent` also needs the
**Foundry Agent Consumer** role at *project* scope (`infra/core/ai/rbac.bicep`)
and must be in the project's own tenant -- cross-tenant token exchange isn't
supported.
"""


import asyncio
import base64
import contextvars
import json
import logging
import os
import re
import time
from typing import Optional

from agent_framework import Agent, Message, tool
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AccessToken, TokenCredential
from azure.identity import AzureDeveloperCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv
from microsoft_agents.activity import Activity
from microsoft_agents.hosting.core import Authorization, CardFactory, TurnContext
from microsoft_agents_a365.notifications.agent_notification import NotificationTypes

from agent_interface import AgentInterface

load_dotenv()

# Enable GenAI tracing before any OpenAI/Foundry client is constructed.
os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"

_appinsights_conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if _appinsights_conn:
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=_appinsights_conn)
    logging.getLogger(__name__).info("📊 Tracing enabled → Application Insights")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL_DEPLOYMENT_NAME = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")

# The 4 persisted Foundry Prompt Agents this orchestrator delegates to (see
# scripts/create_foundry_agents.py, which provisions them, and the module
# docstring). Each agent name maps 1:1 to one IQ surface / connection.
KNOWLEDGE_AGENT_NAME = os.getenv("NOC_KNOWLEDGE_AGENT_NAME", "noc-knowledge-agent")
TOPOLOGY_AGENT_NAME = os.getenv("NOC_TOPOLOGY_AGENT_NAME", "noc-topology-agent")
THREATINTEL_AGENT_NAME = os.getenv("NOC_THREATINTEL_AGENT_NAME", "noc-threatintel-agent")
COMMS_AGENT_NAME = os.getenv("NOC_COMMS_AGENT_NAME", "noc-comms-agent")

# fabric_iq/work_iq require the CALLING USER's OBO token (UserEntraToken
# identity passthrough); foundry_iq/web_iq use the app's own service
# credential. See module docstring "What changed with persisted Prompt Agents".
SPECIALIST_AGENTS: dict[str, tuple[str, bool]] = {
    "foundry_iq": (KNOWLEDGE_AGENT_NAME, False),
    "fabric_iq": (TOPOLOGY_AGENT_NAME, True),
    "web_iq": (THREATINTEL_AGENT_NAME, False),
    "work_iq": (COMMS_AGENT_NAME, True),
}

# OBO token scope used to call each specialist agent's endpoint as the
# calling Teams user (fabric_iq/work_iq only). Agent Service performs its own
# server-side OAuth exchange from this identity to each UserEntraToken tool
# connection's real audience, so a single ai.azure.com-scoped token is enough
# for both user-scoped specialists -- no separate per-tool token exchange
# needed.
FOUNDRY_USER_TOKEN_SCOPES = os.getenv("FOUNDRY_USER_TOKEN_SCOPES", "https://ai.azure.com/.default")

# Separate OBO scope for outbound email (agent.notifications / broadcast_incident_update).
# Requires delegated Mail.Send consented on the agentic identity the same way
# Mail.Read already is for Work IQ -- see docs/OUTBOUND_NOTIFICATIONS.md.
GRAPH_MAIL_TOKEN_SCOPES = os.getenv("GRAPH_MAIL_TOKEN_SCOPES", "https://graph.microsoft.com/.default")

# ponytail: each specialist call is a full model turn on Agent Service, so
# the orchestrator's own wall-clock cap has to cover several sequential/
# fanned-out specialist round trips, not one MCP tool call.
AGENT_RUN_TIMEOUT_SECONDS = float(os.getenv("AGENT_RUN_TIMEOUT_SECONDS", "90"))

ORCHESTRATOR_INSTRUCTIONS = """You are the NOC/NOA network operations orchestrator for a
telecom provider. You help on-call engineers triage incidents such as fibre cuts, router
failures, and amplifier faults by delegating to four specialist agents. Call as many of them
as the question needs, in any order, and synthesize their answers yourself -- each specialist
only sees the single question you send it, not the rest of the conversation.

Delegate as follows:
- ask_knowledge_agent (Foundry IQ): runbooks, equipment specs, infra specs, and past ticket
  history. Use it for "how do we handle X" and "what's the spec / history for Y" questions.
- ask_topology_agent (Fabric IQ): the live network topology graph -- core routers, transport
  links, physical conduits, amplifier sites, services, and SLA policies. Use it for blast-radius
  questions ("what depends on link X", "what conduit does this link ride on", "is any other
  link sharing that same conduit"). ALWAYS check for shared-conduit risk when analyzing a
  physical fault -- two logically independent links can still share one physical conduit,
  which is the most common non-obvious root cause of a "redundant" path also failing.
  This tool's connection is verified working end-to-end. If it returns no data or an empty
  result for a specific query, that means no matching entity/relationship exists in the
  topology for what was asked -- say so plainly (e.g. "no data found for X in the network
  topology") and do NOT claim there was a connection/access/technical problem reaching
  Fabric IQ. Only report an actual connection/consent problem if the tool call itself
  errors out (e.g. a Fabric consent/authorization requirement -- relay the consent
  instructions verbatim to the user in that case).
- ask_threatintel_agent (Web IQ): live public information -- vendor advisories, carrier status
  pages, breaking news about an outage. Use it ONLY to corroborate or find public information
  directly relevant to a NOC/NOA network-operations question (equipment vendor advisories,
  carrier/fibre outage news, etc.). If the user asks about public/web data unrelated to the
  NOC/NOA domain (e.g. general news, unrelated companies, personal topics), do NOT call it --
  politely decline and explain you're scoped to network-operations incidents for this
  telecom provider.
- ask_comms_agent (Work IQ): the user's Teams/Outlook context -- bridge chatter, on-call
  roster, pending change approvals. Use it to answer "who is on-call", "what's being discussed
  on the incident bridge", or to draft a status update. If it requires consent, relay the
  consent URL to the user verbatim.

Always cite which specialist grounded each factual claim. When summarizing an incident,
report: (1) blast radius (services + SLA exposure), (2) any shared-conduit or other
non-obvious compounding risk, (3) the relevant runbook step, (4) any live vendor advisory,
and (5) on-call / bridge context, in that order, clearly labeled. Say plainly when a specialist
was unavailable or returned nothing rather than inventing an answer.
"""


# =============================================================================
# Auth helpers
# =============================================================================


def _get_service_credential():
    """Return the app-level (non-user) credential used for the model AND all 4 IQ tools.

    WEBSITE_INSTANCE_ID is set by the Azure App Service platform itself (Linux
    and Windows, all SKUs) and is the standard way to detect "running inside App
    Service" -- unlike the previous FOUNDRY_HOSTING_ENVIRONMENT check, which was
    never actually set by anything in this repo's infra and caused the deployed
    container to fall through to AzureDeveloperCliCredential, which shells out to
    the `azd` binary. That binary doesn't exist in the App Service container, so
    every credential.get_token() call failed with
    `CredentialUnavailableError: Azure Developer CLI could not be found.`
    """
    if "WEBSITE_INSTANCE_ID" in os.environ:
        return ManagedIdentityCredential()
    return AzureDeveloperCliCredential(tenant_id=AZURE_TENANT_ID, process_timeout=60)


def _jwt_exp_epoch(token: str, default_ttl_seconds: float = 300.0) -> float:
    """Best-effort JWT `exp` claim (unverified -- we already trust this token, we're
    only reading its own stated expiry to know when to stop reusing it from cache).
    Falls back to a short default TTL if the token isn't a standard 3-part JWT.
    """
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # restore stripped base64url padding
        return float(json.loads(base64.urlsafe_b64decode(payload_b64))["exp"])
    except Exception:  # noqa: BLE001
        return time.time() + default_ttl_seconds



def _build_consent_activity(consent_url: str, surface_label: str) -> Activity:
    """Build a Teams Adaptive Card (with an Action.OpenUrl button) for an OAuth consent link.

    Consent URLs are long, ugly, single-use, and short-TTL -- rendering them as
    raw chat text relies on Teams' own auto-linkification (not always reliable
    for URLs this size/shape) and makes the link hard for a user to actually
    tap. An Adaptive Card with a dedicated "Sign in" button is the standard
    Bot Framework/Teams pattern for this and guarantees a tappable action.
    Shared by both `noc-topology-agent` (Fabric IQ) and `noc-comms-agent`
    (Work IQ) -- the two specialists using OAuth identity passthrough.
    """
    card = {
        "type": "AdaptiveCard",
        "version": "1.4",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": [
            {
                "type": "TextBlock",
                "text": f"🔐 {surface_label} needs your consent",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": (
                    f"Before I can pull this data from {surface_label}, please sign in and "
                    "grant consent. This link is single-use and expires quickly -- please "
                    "open it right away."
                ),
                "wrap": True,
            },
        ],
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": f"Sign in to {surface_label}",
                "url": consent_url,
            }
        ],
    }
    return Activity(type="message", attachments=[CardFactory.adaptive_card(card)])


def _extract_oauth_consent_url(response) -> Optional[str]:
    """Pull an OAuth identity-passthrough consent link out of a Prompt Agent response, if present.

    Persisted Prompt Agents surface a first-use consent requirement as an
    `oauth_consent_request`-typed item inside a normal (200 OK)
    `response.output` list, under `consent_link` -- NOT as a raised
    exception (that was the old client-side-MCP `a2a_preview` error shape
    this replaces; see docs/ARCHITECTURE.md).
    """
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) == "oauth_consent_request":
            return getattr(item, "consent_link", None)
    return None



def parse_incident_email(subject: str, body: str) -> Optional[dict]:
    """Detect and parse a "[INCIDENT:<stage>]"-tagged notification email.

    Returns the `incident_context` dict for `broadcast_incident_update()` if
    the tag is present, else None (meaning: handle as a normal conversational
    email per the existing EMAIL_NOTIFICATION path).

    The tag is looked for in TWO places, in order:
      1. `subject` (kept for forward-compatibility / other delivery shapes
         that do carry a subject, e.g. a future typed notification entity).
      2. The first non-blank line of `body`. This is the primary, reliable
         convention: live testing showed the A365 email connector's plain
         "message" activity delivers `channel_data` as only
         `{"tenant": {...}, "productContext": "email"}` -- the email Subject
         line is NOT transmitted at all on this path. See
         docs/OUTBOUND_NOTIFICATIONS.md, which documents the tag as the
         first line of the email BODY for this reason.

    Remaining body convention is one `Field: value` pair per line (HTML tags
    stripped first) -- deliberately simple, no YAML/JSON parser dependency.
    """
    clean_body = re.sub("<[^>]+>", "", body or "")
    lines = clean_body.splitlines()

    match = re.match(r"\s*\[INCIDENT:(\w+)\]", subject or "")
    remaining_lines = lines
    if not match:
        for idx, line in enumerate(lines):
            if line.strip():
                match = re.match(r"\s*\[INCIDENT:(\w+)\]", line)
                if match:
                    remaining_lines = lines[idx + 1 :]
                break

    if not match:
        return None
    context: dict = {"LifecycleStage": match.group(1)}
    for line in remaining_lines:
        if ":" in line:
            key, _, value = line.partition(":")
            if key.strip():
                context[key.strip()] = value.strip()
    return context


# =============================================================================
# Agent
# =============================================================================

# Per-turn context, isolated per asyncio Task (set at the top of
# process_user_message's _run_turn(), read by the specialist tool functions
# and by process_user_message itself afterwards). Using contextvars rather
# than threading extra parameters through agent_framework's tool-calling
# machinery (whose function signatures we don't control) keeps the specialist
# tool functions to a plain `(question: str) -> str` shape.
_current_user_token: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_user_token", default=None
)
_pending_consent: contextvars.ContextVar[Optional[tuple[str, str]]] = contextvars.ContextVar(
    "_pending_consent", default=None
)


class _StaticTokenCredential(TokenCredential):
    """ponytail: minimal TokenCredential wrapping an already-fetched OBO token.

    AIProjectClient only ever calls `get_token()` on the credential it's
    given (to build a bearer-token-provider for the OpenAI client) -- no
    other TokenCredential method is needed here.
    """

    def __init__(self, token: str, expires_on: float):
        self._token = token
        self._expires_on = int(expires_on)

    def get_token(self, *scopes: str, **kwargs) -> AccessToken:  # noqa: ARG002
        return AccessToken(self._token, self._expires_on)


class NocAgent(AgentInterface):
    """A365-hosted MAF orchestrator delegating to 4 persisted Foundry Prompt Agents."""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._service_credential = _get_service_credential()
        self._project_client: Optional[AIProjectClient] = None
        # Specialist agents confirmed to exist at startup (key -> agent name);
        # a missing one degrades that single specialist, not the whole app.
        self._available_agents: dict[str, str] = {}
        # Long-lived orchestrator FoundryChatClient/Agent: always
        # authenticated as the SERVICE identity -- identity passthrough for
        # fabric_iq/work_iq happens per-call, inside each specialist tool
        # function (see _call_specialist).
        self._chat_client: Optional[FoundryChatClient] = None
        self._agent: Optional[Agent] = None
        # Per-user conversation history for context continuity across turns.
        self._conversations: dict[str, list] = {}
        # ponytail: (user_id, scope) -> (token, exp_epoch). _exchange_user_token
        # was re-running the A365 SDK's full OBO broker (several sequential
        # Graph/Observability/ai.azure.com round trips, ~5-6s) on every single
        # turn even when the previous token was still valid -- caching it here
        # cuts that to zero on cache hits.
        self._token_cache: dict[tuple[str, str], tuple[str, float]] = {}

    # -------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------

    async def initialize(self) -> None:
        """Confirm the 4 persisted Prompt Agents exist, then build the orchestrator.

        Connection resolution and toolbox/tool wiring now happen once, at
        provisioning time, in `scripts/create_foundry_agents.py` -- each
        Prompt Agent already holds its own `MCPTool(project_connection_id=...)`
        baked into its persisted definition. This app only needs to know each
        agent's NAME to call it, so startup here is a cheap existence check
        per agent (degrade that one specialist, not the whole app, if it's
        missing), matching the same "degrade this one tool" pattern the old
        toolbox-resolution code used.
        """
        logger.info("🔌 Initializing NOC orchestrator against %s", PROJECT_ENDPOINT)

        self._project_client = AIProjectClient(
            endpoint=PROJECT_ENDPOINT, credential=self._service_credential, allow_preview=True
        )
        for key, (agent_name, _) in SPECIALIST_AGENTS.items():
            try:
                self._project_client.agents.get(agent_name)
                self._available_agents[key] = agent_name
                logger.info("✅ Specialist agent '%s' (%s) confirmed", agent_name, key)
            except Exception as exc:  # noqa: BLE001 -- degrade this one specialist, not the whole agent
                logger.warning(
                    "⚠️ Specialist agent '%s' (%s) not found -- run "
                    "scripts/create_foundry_agents.py first (%s tool disabled): %s",
                    agent_name,
                    key,
                    key,
                    exc,
                )

        self._chat_client = FoundryChatClient(
            project_endpoint=PROJECT_ENDPOINT,
            model=MODEL_DEPLOYMENT_NAME,
            credential=self._service_credential,
        )
        orchestrator_tools = self._build_orchestrator_tools()
        self._agent = Agent(
            client=self._chat_client,
            name="NocOrchestrator",
            instructions=ORCHESTRATOR_INSTRUCTIONS,
            tools=orchestrator_tools,
            default_options={"store": False},
        )

        logger.info("✅ NOC orchestrator ready with %d specialist tool(s)", len(orchestrator_tools))

    async def cleanup(self) -> None:
        """Close the long-lived project client."""
        if self._project_client is not None:
            try:
                self._project_client.close()
            except Exception:  # noqa: BLE001
                pass
        logger.info("🧹 Agent cleanup completed")

    # -------------------------------------------------------------------
    # AGENTS-AS-TOOLS -- one plain Python tool per specialist Prompt Agent
    # -------------------------------------------------------------------

    def _build_orchestrator_tools(self) -> list:
        """Build the orchestrator's tool list: one FunctionTool per available specialist."""
        specs = [
            ("foundry_iq", "ask_knowledge_agent", "Ask the Foundry IQ knowledge-base specialist (runbooks, equipment/infra specs, past ticket history) a question."),
            ("fabric_iq", "ask_topology_agent", "Ask the Fabric IQ network-topology specialist (live topology graph, blast radius, shared-conduit risk) a question."),
            ("web_iq", "ask_threatintel_agent", "Ask the Web IQ specialist (public vendor advisories, carrier status, outage news) a question."),
            ("work_iq", "ask_comms_agent", "Ask the Work IQ specialist (Teams/Outlook: on-call roster, bridge chatter, change approvals) a question."),
        ]
        tools = []
        for key, tool_name, description in specs:
            if key not in self._available_agents:
                continue
            tools.append(tool(self._make_ask_specialist(key), name=tool_name, description=description))
        return tools

    def _make_ask_specialist(self, key: str):
        """Return a plain `(question: str) -> str` closure bound to one specialist.

        A true closure (not a default-argument trick) so `key` never appears
        as a parameter in the schema the model sees for this tool.
        """

        async def _ask(question: str) -> str:
            return await self._call_specialist(key, question)

        return _ask

    async def _call_specialist(self, key: str, question: str) -> str:
        """Invoke one persisted Prompt Agent and return its text answer.

        fabric_iq/work_iq authenticate as the CALLING USER (OAuth identity
        passthrough); foundry_iq/web_iq authenticate as the service identity.
        See module docstring. A fresh `AIProjectClient` is built per call
        (cheap -- no network round trip at construction) so each specialist
        call carries the right identity for THIS turn/user, never a stale one
        from a previous turn.
        """
        agent_name = self._available_agents[key]
        _, needs_user_identity = SPECIALIST_AGENTS[key]
        if needs_user_identity:
            user_token = _current_user_token.get()
            credential = (
                _StaticTokenCredential(user_token, time.time() + 300)
                if user_token
                else self._service_credential
            )
        else:
            credential = self._service_credential

        project_client = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential, allow_preview=True)
        try:
            openai_client = project_client.get_openai_client(agent_name=agent_name)
            response = await asyncio.to_thread(openai_client.responses.create, input=question)
        except Exception as exc:  # noqa: BLE001 -- degrade this one specialist call, not the whole turn
            logger.error("❌ Specialist '%s' call failed: %s", agent_name, exc, exc_info=True)
            return f"({agent_name} is currently unavailable: {exc})"
        finally:
            project_client.close()

        consent_url = _extract_oauth_consent_url(response)
        if consent_url:
            _pending_consent.set((agent_name, consent_url))
            return f"({agent_name} requires the user to sign in first; a consent link has been sent.)"
        return response.output_text or f"({agent_name} returned no answer.)"

    # -------------------------------------------------------------------
    # MESSAGE PROCESSING
    # -------------------------------------------------------------------

    async def process_user_message(
        self,
        message: str,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> str:
        """Run one turn of the MAF orchestrator, delegating to specialist Prompt Agents."""
        from_prop = context.activity.from_property
        user_id = getattr(from_prop, "id", "default") if from_prop else "default"
        display_name = getattr(from_prop, "name", None) or "unknown"
        logger.info("📨 Message from %s (%s): %s...", display_name, user_id, message[:80])

        foundry_user_token = await self._exchange_user_token(
            auth, auth_handler_name, context, FOUNDRY_USER_TOKEN_SCOPES, user_id=user_id
        )
        history: list[Message] = self._conversations.get(user_id, [])
        history.append(Message("user", [message]))

        async def _run_turn():
            # Isolated per-Task: only visible to this turn's own agent.run()
            # call and the specialist tool functions it invokes, never to a
            # concurrent turn from another user (see contextvars docstring above).
            _current_user_token.set(foundry_user_token)
            _pending_consent.set(None)
            return await self._agent.run(history)

        run_task = asyncio.ensure_future(_run_turn())
        try:
            response = await asyncio.wait_for(asyncio.shield(run_task), timeout=AGENT_RUN_TIMEOUT_SECONDS)
            pending = _pending_consent.get()
            if pending:
                agent_name, consent_url = pending
                # Send the sign-in Adaptive Card directly (context is already
                # available here) and return an empty string so the caller's
                # own `send_activity(response)` is a no-op -- avoids sending
                # both a card AND a redundant plain-text message.
                await context.send_activity(_build_consent_activity(consent_url, agent_name))
                return ""
            self._conversations[user_id] = history + [Message("assistant", [response.text])]
            return response.text or "I processed your request but couldn't generate a response."
        except asyncio.TimeoutError:
            if not run_task.done():
                run_task.cancel()

                def _swallow(t: "asyncio.Task") -> None:
                    if not t.cancelled():
                        t.exception()

                run_task.add_done_callback(_swallow)
            logger.error(
                "❌ agent.run() exceeded %.0fs watchdog; abandoning this turn",
                AGENT_RUN_TIMEOUT_SECONDS,
            )
            return (
                "Sorry, that request is taking longer than expected. "
                "Please try again -- one of my tools may be slow to respond."
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("❌ Error processing message: %s", exc, exc_info=True)
            self._conversations.pop(user_id, None)
            return f"Sorry, I encountered an error: {exc}"

    # -------------------------------------------------------------------
    # NOTIFICATION HANDLING (A365 email / Word-comment triggers)
    # -------------------------------------------------------------------

    async def handle_agent_notification_activity(
        self,
        notification_activity,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> str:
        """Handle A365 notifications by forwarding to the same MAF agent turn."""
        try:
            notification_type = notification_activity.notification_type
            logger.info("📬 Processing notification: %s", notification_type)

            if notification_type == NotificationTypes.EMAIL_NOTIFICATION:
                email = notification_activity.email
                email_subject = getattr(email, "subject", "") or ""
                email_body = getattr(email, "html_body", "") or getattr(email, "body", "")

                # Event-driven incident-lifecycle trigger: an incident-management
                # system emails the monitored inbox with a "[INCIDENT:<stage>]"
                # subject tag instead of a Teams/webhook call needing a stored
                # conversation_id -- inspired by the OnNewEmailV3 connector
                # trigger pattern in Azure-Samples/m365-inbox-serverless-agent-python
                # (this repo's own EMAIL_NOTIFICATION handler is the equivalent
                # building block: already event-driven on new mail, no prior
                # conversation needed). See docs/OUTBOUND_NOTIFICATIONS.md.
                incident_context = parse_incident_email(email_subject, email_body)
                if incident_context is not None:
                    results = await self.broadcast_incident_update(incident_context, auth, auth_handler_name, context)
                    return f"Incident notification broadcast: {results}"

                message = (
                    "You received the following email about a network incident. "
                    "Please review and summarize the blast radius and next steps.\n\n"
                    f"{email_body}"
                )
            elif notification_type == NotificationTypes.WPX_COMMENT:
                comment_text = notification_activity.text or ""
                message = (
                    f"You were mentioned in a Word document comment: {comment_text}\n"
                    "Please review and respond."
                )
            else:
                message = notification_activity.text or f"Notification received: {notification_type}"

            return await self.process_user_message(message, auth, auth_handler_name, context)
        except Exception as exc:  # noqa: BLE001
            logger.error("❌ Notification error: %s", exc)
            return f"Sorry, I encountered an error processing the notification: {exc}"

    # -------------------------------------------------------------------
    # OUTBOUND MULTI-PERSONA EMAIL (proactive, not turn-initiated)
    # -------------------------------------------------------------------

    async def handle_email_message(
        self,
        subject: str,
        body: str,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
        sender_email: Optional[str] = None,
    ) -> Optional[str]:
        """Detect a "[INCIDENT:<stage>]"-tagged email delivered as a plain
        "message" activity (channel_id "agents:email") rather than an
        `AgentNotificationActivity` -- a directly-composed/forwarded email
        to the agent's mailbox arrives this way (see host_agent_server.py's
        `on_message`, which has no NOC-specific knowledge and calls this
        hook first). Returns the broadcast summary if the tag matched, else
        None so the caller falls back to normal conversational handling.

        `sender_email`, if given, is CC'd on every persona email sent --
        so whoever emailed the incident report in gets visibility into the
        stakeholder broadcast without being added as a primary NOTIFY_*
        recipient (which stays the configured stakeholder distribution
        list, not the ad-hoc sender).
        """
        incident_context = parse_incident_email(subject, body)
        if incident_context is None:
            return None
        cc_recipients = [sender_email] if sender_email else None
        results = await self.broadcast_incident_update(
            incident_context, auth, auth_handler_name, context, cc_recipients=cc_recipients
        )
        return f"Incident notification broadcast: {results}"

    async def broadcast_incident_update(
        self,
        incident_context: dict,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
        personas: Optional[list] = None,
        cc_recipients: Optional[list] = None,
    ) -> dict:
        """Send an incident-lifecycle update to one or more stakeholder personas.

        Reachable only via a resumed (proactive) conversation -- see
        host_agent_server.py's `POST /api/incidents/notify` route and
        docs/OUTBOUND_NOTIFICATIONS.md. Requires the SAME OBO machinery as
        Fabric IQ/Work IQ (`_exchange_user_token`), just scoped to
        `https://graph.microsoft.com/.default` with delegated `Mail.Send`
        consented instead of `Mail.Read` -- see docs/DEPLOYMENT.md.
        """
        from notifications import broadcast  # local import: optional feature, keep agent.py importable without it

        graph_token = await self._exchange_user_token(auth, auth_handler_name, context, GRAPH_MAIL_TOKEN_SCOPES)
        if not graph_token:
            logger.error("❌ No Graph OBO token -- cannot send outbound notifications this turn")
            return {}
        return await broadcast(incident_context, graph_token, personas, cc_recipients=cc_recipients)

    # -------------------------------------------------------------------
    # OBO TOKEN EXCHANGE (Fabric Data Agent + Work IQ require user delegation)
    # -------------------------------------------------------------------

    async def _exchange_user_token(
        self,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
        scope: str,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """Get a user-delegated token via the AgenticUserAuthorization handler.

        The A365 platform (with inheritable permissions configured on the
        blueprint) provides a user-delegated token through this exchange,
        scoped to `https://ai.azure.com/.default`. This single token is used
        to build the whole per-turn FoundryChatClient/Agent as the calling
        Teams user; Foundry's own service then performs its own server-side
        OBO exchange from this identity to each UserEntraToken-typed tool
        connection's real audience (Fabric IQ -> api.fabric.microsoft.com,
        Work IQ -> its own audience) -- so only one token exchange is needed
        here, unlike the old local-MCP-client design which needed a separate
        per-tool-audience token (see docs/TROUBLESHOOTING.md).

        ponytail: cached per (user_id, scope) for the token's own lifetime
        (minus a 60s safety margin) when `user_id` is supplied -- see
        `self._token_cache`. Skips the cache entirely (old behaviour) when
        `user_id` is None, e.g. the outbound-notification path.
        """
        if not auth_handler_name:
            logger.warning("⚠️ No auth handler configured — Fabric IQ/Work IQ will be unavailable this turn")
            return None

        cache_key = (user_id, scope) if user_id else None
        if cache_key:
            cached = self._token_cache.get(cache_key)
            if cached and cached[1] > time.time():
                logger.info("✅ Reusing cached OBO token for scope %s (no broker round trip)", scope)
                return cached[0]

        try:
            token_response = await auth.exchange_token(
                context, scopes=[scope], auth_handler_id=auth_handler_name
            )
            if token_response and token_response.token:
                logger.info("✅ User OBO token acquired (len=%d)", len(token_response.token))
                if cache_key:
                    self._token_cache[cache_key] = (
                        token_response.token,
                        _jwt_exp_epoch(token_response.token) - 60,
                    )
                return token_response.token
            logger.warning("⚠️ Token exchange returned empty response")
        except Exception as exc:  # noqa: BLE001
            logger.warning("⚠️ OBO token exchange failed: %s", exc, exc_info=True)
        return None
