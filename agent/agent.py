# Copyright (c) Microsoft. All rights reserved.

"""
NOC Agent — MAF orchestrator with four IQ tools (Foundry IQ, Fabric IQ, Web IQ, Work IQ).

This agent runs an in-process Microsoft Agent Framework (MAF) `Agent`
directly (not a bridge to a pre-built, persisted Foundry Agent object): a
single `Agent` with multiple tools bound, where the model's own
tool-selection performs the routing across IQ surfaces. No hand-rolled
dispatcher is needed.

All four IQ tools are bundled behind a single **Foundry Toolbox** MCP
endpoint (`project.toolboxes.create_version(...)`, one `MCPToolboxTool` per
project Connection), attached to the MAF `Agent` as ONE client-side
`agent_framework.MCPStreamableHTTPTool` pointed at that toolbox's own MCP
URL. This is the pattern Microsoft's own docs specify for *hosted agents*
(an ephemeral MAF `Agent`/`FoundryChatClient` calling the raw Responses API
directly, with no persisted server-side Agent object / `agent_reference`) --
see "Hosted agents" in
https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/model-context-protocol.
`FoundryChatClient.get_mcp_tool(project_connection_id=...)` (a native/hosted
tool attached directly to `tools=[...]` on the Responses call) was tried
first and looked structurally correct, but the Responses API rejected it
with `400 missing_mutually_exclusive_parameters` -- that field only resolves
for **Prompt Agents** created via `project.agents.create_version(...)` and
invoked with `extra_body={"agent_reference": ...}`, which this code does not
do. Routing all 4 tools through one Toolbox also means Foundry's own service
runs each individual tool's MCP round-trip, and the *toolbox* is the only
thing this code has to manage, replacing an earlier hand-rolled 4-connection
`MCPStreamableHTTPTool`/`FoundryToolbox`-over-httpx design that hit three
separate asyncio/anyio bug classes (hang, shared-stack corruption,
BaseExceptionGroup escape) trying to manage 4 raw MCP client connections by
hand (see docs/TROUBLESHOOTING.md for the full history).

Auth-type matrix (see docs/ARCHITECTURE.md for the full rationale):
  - Foundry IQ (knowledge base MCP)   -> project connection, service identity
  - Web IQ (web MCP)                  -> project connection, CustomKeys (x-apikey)
  - Fabric IQ (Fabric Data Agent MCP) -> project connection, UserEntraToken (OBO identity passthrough)
  - Work IQ (Microsoft 365 toolbox)   -> project connection, UserEntraToken (OBO identity passthrough)

The `FoundryChatClient` itself is ALWAYS authenticated as this app's own
SERVICE identity (per the docs' "Hosted agents" sample, which uses
`AzureCliCredential`/`DefaultAzureCredential`, not a per-user token) --
identity passthrough for Fabric IQ/Work IQ instead happens one layer down, at
the Toolbox's own MCP HTTP call: the calling Teams user's OBO token (obtained
via the A365 AgenticUserAuthorization handler) is injected as the
`Authorization` header on that one HTTP client via `header_provider`, and the
Toolbox's `user-entra-token`-configured connections forward that identity to
Fabric/Work IQ server-side. (An earlier version of this file swapped the
*whole* FoundryChatClient's credential to the user's OBO token instead, which
caused the raw Responses API call itself to require Foundry project RBAC
roles a per-user identity would never sensibly hold -- see
docs/TROUBLESHOOTING.md's "Foundry project RBAC" entry.)
"""


import asyncio
import base64
import json
import logging
import os
import re
import time
from typing import Optional

from agent_framework import Agent, MCPStreamableHTTPTool, Message
from agent_framework.exceptions import ToolException
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPToolboxTool
from azure.identity import AzureDeveloperCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv
from mcp import McpError
from microsoft_agents.hosting.core import Authorization, TurnContext
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

# All four IQ tools are wired as NATIVE Foundry-hosted MCP tools (Foundry's
# Responses API runs the MCP session server-side against a pre-registered
# project Connection) instead of a local Python MCP client we manage
# ourselves. See docs/TROUBLESHOOTING.md's "moved to native Foundry tools"
# entry for why: our own asyncio/anyio MCP client wrapper hit three separate
# bug classes (hang, shared-stack corruption, BaseExceptionGroup escape)
# trying to manage this connection lifecycle by hand; Foundry's own service
# already solves this exact problem for its own hosted tool connections.
FOUNDRY_IQ_CONNECTION_NAME = os.getenv("FOUNDRY_IQ_CONNECTION_NAME", "kb-mcp-connection")
WEB_IQ_CONNECTION_NAME = os.getenv("WEB_IQ_CONNECTION_NAME", "web-iq-connection")
FABRIC_IQ_CONNECTION_NAME = os.getenv("FABRIC_IQ_CONNECTION_NAME", "fabric-iq-connection")
WORK_IQ_CONNECTION_NAME = os.getenv("WORK_IQ_CONNECTION_NAME", "WorkIQ")

# All 4 connections are bundled behind one Foundry Toolbox (see module
# docstring) so the MAF Agent only has to manage a single client-side MCP
# tool, rather than 4 raw MCP client connections.
NOC_TOOLBOX_NAME = os.getenv("NOC_TOOLBOX_NAME", "noc-iq-toolbox")

# OBO token scope used to authenticate the WHOLE per-turn Foundry chat client
# as the calling Teams user (not just one tool call). Fabric IQ/Work IQ's
# Foundry connections use identity passthrough (UserEntraToken): Foundry
# performs its own server-side OBO exchange from THIS token's identity to
# each tool's actual audience, so a single ai.azure.com-scoped token is
# enough for all four tools -- no separate per-tool token exchange needed.
FOUNDRY_USER_TOKEN_SCOPES = os.getenv("FOUNDRY_USER_TOKEN_SCOPES", "https://ai.azure.com/.default")

# Separate OBO scope for outbound email (agent.notifications / broadcast_incident_update).
# Requires delegated Mail.Send consented on the agentic identity the same way
# Mail.Read already is for Work IQ -- see docs/OUTBOUND_NOTIFICATIONS.md.
GRAPH_MAIL_TOKEN_SCOPES = os.getenv("GRAPH_MAIL_TOKEN_SCOPES", "https://graph.microsoft.com/.default")

# ponytail: a native Foundry tool call still round-trips over the network
# server-side, so agent.run() keeps its own wall-clock cap rather than being
# able to hang the turn forever if Foundry's own tool-call plumbing stalls.
AGENT_RUN_TIMEOUT_SECONDS = float(os.getenv("AGENT_RUN_TIMEOUT_SECONDS", "90"))
# ponytail: bounded retry for the "Cancelled via cancel scope" MCP-connect
# race documented in docs/TROUBLESHOOTING.md -- see process_user_message.
MCP_CONNECT_MAX_ATTEMPTS = int(os.getenv("MCP_CONNECT_MAX_ATTEMPTS", "3"))
MCP_CONNECT_RETRY_DELAY_SECONDS = float(os.getenv("MCP_CONNECT_RETRY_DELAY_SECONDS", "1.0"))

NOC_AGENT_INSTRUCTIONS = """You are the NOC/NOA network operations assistant for a telecom
provider. You help on-call engineers triage incidents such as fibre cuts, router failures,
and amplifier faults.

Use your tools as follows:
- knowledge-base (Foundry IQ): runbooks, equipment specs, infra specs, and past ticket history.
  Use it for "how do we handle X" and "what's the spec / history for Y" questions.
- network-ontology (Fabric IQ): the live network topology graph -- core routers, transport
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
- web search (Web IQ): live public information -- vendor advisories, carrier status pages,
  breaking news about an outage. Use it ONLY to corroborate or find public information
  directly relevant to a NOC/NOA network-operations question (equipment vendor advisories,
  carrier/fibre outage news, etc.). If the user asks about public/web data unrelated to the
  NOC/NOA domain (e.g. general news, unrelated companies, personal topics), do NOT call Web IQ
  -- politely decline and explain you're scoped to network-operations incidents for this
  telecom provider.
- Microsoft 365 tools (Work IQ): the user's Teams/Outlook context -- bridge chatter, on-call
  roster, pending change approvals. Use it to answer "who is on-call", "what's being discussed
  on the incident bridge", or to draft a status update. If Work IQ requires consent, relay the
  consent URL to the user verbatim.

Always cite which tool/source grounded each factual claim. When summarizing an incident,
report: (1) blast radius (services + SLA exposure), (2) any shared-conduit or other
non-obvious compounding risk, (3) the relevant runbook step, (4) any live vendor advisory,
and (5) on-call / bridge context, in that order, clearly labeled. Say plainly when a tool
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


_WORK_IQ_CONSENT_PREFIX = "Work IQ needs your consent before it can access this data. Please open: "


def _extract_a2a_consent_url(exc: BaseException) -> Optional[str]:
    """Pull a Work IQ (a2a_preview) consent URL out of an MCP tool-call error, if present.

    Work IQ surfaces its OAuth consent requirement as an MCP error whose message
    embeds a JSON payload with an "a2a_preview"-typed CONSENT_REQUIRED error. MAF's
    hosted-agent Responses server has its own handling for this
    (microsoft/agent-framework#7227 tracks upstream support), but since this agent
    calls `agent.run()` directly rather than going through ResponsesHostServer, we
    parse it ourselves and relay a friendly message instead of a raw exception.
    """
    inner = next((arg for arg in exc.args if isinstance(arg, McpError)), None)
    if inner is None:
        return None
    message = inner.error.message or ""
    start = message.find("{")
    if start == -1:
        return None
    try:
        details = json.loads(message[start:])
    except json.JSONDecodeError:
        return None
    for error in details.get("errors", []):
        if not isinstance(error, dict) or error.get("type") != "a2a_preview":
            continue
        error_details = error.get("error") or {}
        if error_details.get("code") == "CONSENT_REQUIRED":
            consent_url = error_details.get("message")
            if isinstance(consent_url, str):
                return consent_url
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


class NocAgent(AgentInterface):
    """A365-hosted NOC assistant running an in-process MAF agent with 4 IQ tools."""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._service_credential = _get_service_credential()
        self._project_client: Optional[AIProjectClient] = None
        self._connection_ids: dict[str, Optional[str]] = {}
        self._toolbox_mcp_url: Optional[str] = None
        # Long-lived FoundryChatClient/Agent: always authenticated as the
        # SERVICE identity (see module docstring) so it can be built once and
        # reused across turns -- identity passthrough for Fabric IQ/Work IQ
        # happens at the per-turn toolbox HTTP call instead.
        self._chat_client: Optional[FoundryChatClient] = None
        self._agent: Optional[Agent] = None
        # Per-user conversation history for context continuity across turns.
        self._conversations: dict[str, list] = {}
        # ponytail: (user_id, scope) -> (token, exp_epoch). _exchange_user_token
        # was re-running the A365 SDK's full OBO broker (several sequential
        # Graph/Observability/ai.azure.com round trips, ~5-6s) on every single
        # turn even when the previous token was still valid -- caching it here
        # cuts that to zero on cache hits, which also removes several seconds
        # of event-loop-blocking work sitting immediately before the MCP
        # connect (a suspect in the "cancel scope" crash investigation).
        self._token_cache: dict[tuple[str, str], tuple[str, float]] = {}

    # -------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------

    async def initialize(self) -> None:
        """Resolve the 4 IQ connections, bundle them into one Foundry Toolbox, build the agent.

        The Toolbox is what Foundry's own docs specify for "hosted agents"
        (an ephemeral MAF Agent/FoundryChatClient calling the raw Responses
        API, no persisted server-side Agent object) -- see module docstring.
        A new toolbox VERSION is created on every startup, which is simple
        and correct but does accumulate versions across app restarts/deploys;
        acceptable for this demo, but worth pruning old versions periodically
        (`project.toolboxes.list_versions()` / a delete loop) if this ever
        runs long-lived in a real environment.
        """
        logger.info("🔌 Initializing NOC agent against %s", PROJECT_ENDPOINT)

        self._project_client = AIProjectClient(
            endpoint=PROJECT_ENDPOINT, credential=self._service_credential
        )
        connection_names = {
            "foundry_iq": FOUNDRY_IQ_CONNECTION_NAME,
            "web_iq": WEB_IQ_CONNECTION_NAME,
            "fabric_iq": FABRIC_IQ_CONNECTION_NAME,
            "work_iq": WORK_IQ_CONNECTION_NAME,
        }
        toolbox_tools = []
        for key, name in connection_names.items():
            try:
                connection = self._project_client.connections.get(name, include_credentials=False)
                self._connection_ids[key] = connection.id
                logger.info("✅ Resolved connection '%s' -> %s", name, connection.id)
                toolbox_tools.append(
                    MCPToolboxTool(
                        server_label=key.replace("_", "-"),
                        server_url=connection.target,
                        project_connection_id=connection.id,
                        require_approval="never",
                    )
                )
            except Exception as exc:  # noqa: BLE001 -- degrade this one tool, not the whole agent
                logger.warning(
                    "⚠️ Could not resolve connection '%s' (%s tool disabled): %s", name, key, exc
                )
                self._connection_ids[key] = None

        if toolbox_tools:
            try:
                toolbox = self._project_client.toolboxes.create_version(
                    NOC_TOOLBOX_NAME,
                    tools=toolbox_tools,
                    description="NOC/NOA IQ tools: Foundry IQ, Web IQ, Fabric IQ, Work IQ",
                )
                self._toolbox_mcp_url = (
                    f"{PROJECT_ENDPOINT}/toolboxes/{toolbox.name}/versions/{toolbox.version}/mcp?api-version=v1"
                )
                logger.info(
                    "✅ Toolbox '%s' v%s ready with %d tool(s) -> %s",
                    toolbox.name,
                    toolbox.version,
                    len(toolbox_tools),
                    self._toolbox_mcp_url,
                )
            except Exception:
                logger.error("❌ Failed to create/update the NOC IQ toolbox", exc_info=True)
        else:
            logger.error("❌ No IQ connections resolved -- toolbox not created, no tools this session")

        # The chat client/agent are long-lived and always authenticated as
        # the service identity; only the toolbox tool is rebuilt per turn.
        self._chat_client = FoundryChatClient(
            project_endpoint=PROJECT_ENDPOINT,
            model=MODEL_DEPLOYMENT_NAME,
            credential=self._service_credential,
        )
        self._agent = Agent(
            client=self._chat_client,
            name="NocAgent",
            instructions=NOC_AGENT_INSTRUCTIONS,
            default_options={"store": False},
        )

        logger.info("✅ NOC agent ready")

    async def cleanup(self) -> None:
        """Close the long-lived project client; per-turn toolbox tools close themselves."""
        if self._project_client is not None:
            try:
                self._project_client.close()
            except Exception:  # noqa: BLE001
                pass
        logger.info("🧹 Agent cleanup completed")

    # -------------------------------------------------------------------
    # PER-TURN TOOL -- one Toolbox MCP tool bundling all 4 IQ surfaces
    # -------------------------------------------------------------------

    def _build_turn_tool(self, foundry_user_token: Optional[str]) -> Optional[MCPStreamableHTTPTool]:
        """Build the single Toolbox MCP tool for this turn.

        Authenticates the outer HTTP call to the toolbox MCP endpoint as the
        calling Teams user's OBO token when available (falls back to the
        service identity otherwise), so Fabric IQ/Work IQ's UserEntraToken
        connections can forward that identity downstream. Requires the
        calling user to hold "Azure AI Developer" (or "Foundry User" +
        appropriate access) scoped to the *project* resource specifically
        (`.../accounts/{account}/projects/{project}`) -- an assignment
        scoped only to the parent account is NOT honored by this data-plane
        endpoint's authorization check, unlike most ARM RBAC which inherits
        downward. This was the actual root cause of a lengthy "cancel
        scope"/403 investigation; see docs/PRIMER_MCP_CANCEL_SCOPE_BUG.md.
        """
        if not self._toolbox_mcp_url:
            logger.error("❌ No toolbox MCP URL available -- this turn will have no tools")
            return None

        bearer_token = foundry_user_token or self._service_credential.get_token(FOUNDRY_USER_TOKEN_SCOPES).token

        def _header_provider(_kwargs: dict) -> dict[str, str]:
            auth_scheme = "Bearer"
            return {"Authorization": auth_scheme + " " + bearer_token}

        return MCPStreamableHTTPTool(
            name="noc-iq-toolbox",
            url=self._toolbox_mcp_url,
            header_provider=_header_provider,
            load_prompts=False,
            approval_mode="never_require",
        )

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
        """Run one turn of the MAF NOC agent, using the per-turn toolbox tool scoped to this user."""
        from_prop = context.activity.from_property
        user_id = getattr(from_prop, "id", "default") if from_prop else "default"
        display_name = getattr(from_prop, "name", None) or "unknown"
        logger.info("📨 Message from %s (%s): %s...", display_name, user_id, message[:80])

        foundry_user_token = await self._exchange_user_token(
            auth, auth_handler_name, context, FOUNDRY_USER_TOKEN_SCOPES, user_id=user_id
        )
        history: list[Message] = self._conversations.get(user_id, [])
        history.append(Message("user", [message]))

        async def _run_turn() -> "AgentResponse":
            # ponytail: self._agent is a long-lived singleton (see initialize()),
            # and agent_framework.Agent.run() -- when handed `tools=[...]` that
            # aren't already connected -- registers each MCP tool on the
            # *Agent's own* `_async_exit_stack`, which is created once in
            # Agent.__init__ and only ever closed by the Agent's own
            # __aexit__ (never called here, since the Agent lives for the
            # process lifetime). Every turn's fresh MCPStreamableHTTPTool was
            # therefore piling onto one shared, never-closed exit stack across
            # concurrent turns/tasks -- the exact shape that trips anyio's
            # "cancel scope in a different task" check and was surfacing as
            # `MCP server failed to initialize: Cancelled via cancel scope`
            # on every single turn. Connecting/disconnecting the tool
            # ourselves here, scoped to this turn's own task via `async with`,
            # means it's already `is_connected` by the time `agent.run()`
            # looks at it, so agent_framework skips the shared exit stack
            # entirely for this tool.
            #
            # ponytail: even with the tool disconnected from the shared exit
            # stack above, the SAME "Cancelled via cancel scope" error was
            # still reproducible in complete isolation (a standalone script,
            # no Agent/host/concurrency at all) -- but only intermittently,
            # and traces show the A365 hosting SDK's own agentic-token-broker
            # calls (Graph / Observability / ai.azure.com scopes, several
            # round trips) run just before the MCP connect and appear to
            # briefly stall the event loop; when the MCP transport's
            # initialize() finally gets scheduled after that stall, its
            # internal anyio timing gets corrupted. This looks like a
            # transient race in agent_framework/the hosting SDK, not a
            # deterministic bug in our code -- so retry with a *fresh* tool
            # instance (a clean cancel-scope/session) a couple of times
            # before giving up.
            last_exc: Optional[BaseException] = None
            for attempt in range(1, MCP_CONNECT_MAX_ATTEMPTS + 1):
                tool = self._build_turn_tool(foundry_user_token)
                turn_tools = [tool] if tool else []
                try:
                    if tool is not None:
                        async with tool:
                            return await self._agent.run(history, tools=turn_tools)
                    return await self._agent.run(history, tools=turn_tools)
                except ToolException as exc:
                    last_exc = exc
                    if "cancel scope" not in str(exc).lower() or attempt == MCP_CONNECT_MAX_ATTEMPTS:
                        raise
                    logger.warning(
                        "⚠️ MCP connect hit a cancel-scope race (attempt %d/%d), retrying with a fresh tool: %s",
                        attempt,
                        MCP_CONNECT_MAX_ATTEMPTS,
                        exc,
                    )
                    await asyncio.sleep(MCP_CONNECT_RETRY_DELAY_SECONDS)
            raise last_exc  # pragma: no cover -- unreachable, loop always returns or raises

        run_task = asyncio.ensure_future(_run_turn())
        try:
            response = await asyncio.wait_for(asyncio.shield(run_task), timeout=AGENT_RUN_TIMEOUT_SECONDS)
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
        except McpError as exc:
            consent_url = _extract_a2a_consent_url(exc)
            if consent_url:
                return f"{_WORK_IQ_CONSENT_PREFIX}{consent_url}"
            logger.error("❌ MCP tool error: %s", exc, exc_info=True)
            return f"Sorry, one of my tools failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            logger.error("❌ Error processing message: %s", exc, exc_info=True)
            self._conversations.pop(user_id, None)
            return f"Sorry, I encountered an error: {exc}"
        # ponytail: no explicit `finally: tool.close()` here anymore -- each
        # attempt's tool is opened/closed via `async with tool:` inside
        # _run_turn() itself, scoped to that attempt's own task.

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
