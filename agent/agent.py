# Copyright (c) Microsoft. All rights reserved.

"""
NOC Agent — MAF orchestrator with four IQ tools (Foundry IQ, Fabric IQ, Web IQ, Work IQ).

Unlike microsoft/iq-samples/refund-agent-a365's agent.py (which bridges to a
pre-built Foundry agent over the OpenAI Responses API), this agent runs an
in-process Microsoft Agent Framework (MAF) `Agent` directly, per the pattern
demonstrated in microsoft/iqdeepdive's src/agent-workiq-maf and
agent-foundryiq-mcp samples: a single `Agent` with multiple tools bound, where
the model's own tool-selection performs the routing across IQ surfaces. No
hand-rolled dispatcher is needed.

Auth-type matrix (see docs/ARCHITECTURE.md for the full rationale):
  - Foundry IQ (knowledge base MCP) -> service credential (not user-scoped data)
  - Web IQ (web MCP)                -> static API key (CustomKeys / x-apikey)
  - Fabric IQ (Fabric Data Agent MCP) -> per-user OBO token (identity passthrough)
  - Work IQ (FoundryToolbox)          -> per-user OBO token (identity passthrough)

Fabric IQ and Work IQ tools are therefore rebuilt on every turn from the user's
OBO token (obtained via the A365 AgenticUserAuthorization handler) and merged
into the agent's default tool set for that one `agent.run()` call, rather than
held open for the lifetime of the process.
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import Generator
from contextlib import AsyncExitStack
from typing import Optional

import httpx
from agent_framework import Agent, MCPStreamableHTTPTool, Message
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox
from azure.core.credentials import AccessToken, TokenCredential
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

# Foundry IQ (knowledge base MCP over the NOC runbook/ticket/spec corpus)
SEARCH_ENDPOINT = os.environ["AZURE_AI_SEARCH_SERVICE_ENDPOINT"]
KNOWLEDGE_BASE_NAME = os.getenv("AZURE_AI_SEARCH_KNOWLEDGE_BASE_NAME", "noc-knowledge-kb")
SEARCH_SCOPE = "https://search.azure.com/.default"

# Web IQ (Microsoft web MCP server, static API key -- CustomKeys, NOT identity passthrough)
WEB_IQ_MCP_ENDPOINT = os.getenv("WEB_IQ_MCP_ENDPOINT", "https://api.microsoft.ai/v3/mcp")
WEB_IQ_API_KEY = os.getenv("WEB_IQ_API_KEY", "")

# Fabric IQ (Fabric Data Agent MCP over the NOC network ontology -- OBO identity passthrough)
FABRIC_DATA_AGENT_MCP_URL = os.getenv("FABRIC_DATA_AGENT_MCP_URL", "")
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

# Work IQ (Microsoft 365 toolbox -- Teams/Outlook/on-call context, OBO identity passthrough)
WORKIQ_TOOLBOX_NAME = os.getenv("CUSTOM_FOUNDRY_WORKIQ_TOOLBOX_NAME", "work-iq-tools")

# OBO token scope used to call Fabric IQ / Work IQ through the Foundry project.
FOUNDRY_USER_TOKEN_SCOPES = os.getenv("FOUNDRY_USER_TOKEN_SCOPES", "https://ai.azure.com/.default")

# ponytail: bound to a few seconds so one slow/hanging IQ tool (observed with
# Work IQ toolbox) degrades that tool gracefully instead of the whole turn
# hitting the mcp/anyio library's misleading "Cancelled via cancel scope" error.
TOOL_CONNECT_TIMEOUT_SECONDS = float(os.getenv("TOOL_CONNECT_TIMEOUT_SECONDS", "15"))

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
  If this tool is unavailable, say so explicitly rather than guessing at topology.
  If the tool returns a Fabric consent/authorization requirement, relay the consent
  instructions verbatim to the user.
- web search (Web IQ): live public information -- vendor advisories, carrier status pages,
  breaking news about an outage. Use it to corroborate or find advisories not yet in the
  knowledge base.
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


class _BearerTokenAuth(httpx.Auth):
    """Attach a fixed bearer token to every request on an httpx client.

    Used for MCP tools where the token is already resolved (a service
    credential fetch, or a per-turn OBO token) -- as opposed to
    AzureTokenCredentialAuth patterns elsewhere that refresh from a
    TokenCredential on every call. Fixed-per-turn is fine here because each
    NOC chat turn is short-lived and the tool objects are rebuilt per turn.
    """

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


class _StaticTokenCredential(TokenCredential):
    """Wrap an already-acquired token string as a TokenCredential.

    FoundryToolbox (Work IQ) expects a TokenCredential, not a raw token string.
    This lets us forward the per-user OBO token acquired via the A365
    AgenticUserAuthorization handler into MAF's Work IQ tool.
    """

    def __init__(self, token: str) -> None:
        self._token = token

    def get_token(self, *scopes: str, **kwargs) -> AccessToken:  # noqa: D102
        # expires_on is set an hour out -- these tools are only used for the
        # single agent turn during which this credential instance is alive.
        return AccessToken(self._token, int(time.time()) + 3600)


def _get_service_credential():
    """Return the app-level (non-user) credential used for Foundry IQ + the model.

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


# =============================================================================
# Agent
# =============================================================================


class NocAgent(AgentInterface):
    """A365-hosted NOC assistant running an in-process MAF agent with 4 IQ tools."""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._service_credential = _get_service_credential()
        self._chat_client: Optional[FoundryChatClient] = None
        self._agent: Optional[Agent] = None
        # Per-user conversation history for context continuity across turns.
        self._conversations: dict[str, list] = {}

    # -------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------

    async def initialize(self) -> None:
        """Build the MAF agent shell. All MCP tools are built fresh per turn
        (see _build_turn_tools) -- Teams can redeliver a message concurrently
        (slow-ack retry), and a shared, connect-once MCP tool instance entered/
        exited by two overlapping agent.run() calls hits an anyio cross-task
        cancel-scope error ("MCP server failed to initialize: Cancelled via
        cancel scope ..."). Building every tool fresh per turn, like Fabric IQ
        and Work IQ already did, avoids the whole bug class.
        """
        logger.info("🔌 Initializing NOC agent against %s", PROJECT_ENDPOINT)

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
        """No persistent HTTP clients to close -- all tool clients are per-turn."""
        logger.info("🧹 Agent cleanup completed")

    # -------------------------------------------------------------------
    # PER-TURN TOOLS -- Foundry IQ, Web IQ, Fabric IQ, Work IQ
    # -------------------------------------------------------------------

    def _build_turn_tools(
        self, foundry_user_token: Optional[str], fabric_user_token: Optional[str]
    ) -> tuple[list, list[httpx.AsyncClient]]:
        """Build all four IQ tools fresh for one turn.

        Returns (tools, http_clients_to_close) -- the caller must close the
        clients after the run() call completes, since MCPStreamableHTTPTool
        needs its auth attached at construction/session-init time, not applied
        later via a header_provider.

        All tools are built per-turn (not cached on self) because MAF's Agent
        connects each MCP tool via its own per-run() async exit stack; a tool
        instance shared across concurrent turns (Teams can redeliver a message
        while the first is still processing) gets entered/exited by two
        different tasks at once, which anyio surfaces as "Cancelled via cancel
        scope ...". Fabric IQ and Work IQ already used this per-turn pattern
        for OBO-token reasons; Foundry IQ and Web IQ now follow it too.

        Fabric IQ and Work IQ need SEPARATE OBO tokens: Work IQ lives under
        the Foundry project (ai.azure.com audience), Fabric IQ's Data Agent
        lives under api.fabric.microsoft.com -- a different token audience
        entirely. Sending one resource's token to the other's endpoint fails
        auth, which the mcp/anyio client mis-surfaces as the same misleading
        "Cancelled via cancel scope ..." error (see docs/TROUBLESHOOTING.md).
        """
        tools: list = []
        clients: list[httpx.AsyncClient] = []

        service_token = self._service_credential.get_token(SEARCH_SCOPE).token
        foundry_iq_http_client = httpx.AsyncClient(
            auth=_BearerTokenAuth(service_token), timeout=120.0
        )
        clients.append(foundry_iq_http_client)
        knowledge_base_endpoint = (
            f"{SEARCH_ENDPOINT.rstrip('/')}/knowledgebases/{KNOWLEDGE_BASE_NAME}"
            "/mcp?api-version=2026-05-01-preview"
        )
        tools.append(
            MCPStreamableHTTPTool(
                name="knowledge-base",
                url=knowledge_base_endpoint,
                http_client=foundry_iq_http_client,
                allowed_tools=["knowledge_base_retrieve"],
                load_prompts=False,
            )
        )

        if WEB_IQ_API_KEY:
            web_iq_http_client = httpx.AsyncClient(
                headers={"x-apikey": WEB_IQ_API_KEY}, timeout=60.0
            )
            clients.append(web_iq_http_client)
            tools.append(
                MCPStreamableHTTPTool(
                    name="web-search",
                    url=WEB_IQ_MCP_ENDPOINT,
                    http_client=web_iq_http_client,
                    load_prompts=False,
                )
            )
        else:
            logger.warning("⚠️ WEB_IQ_API_KEY not set — Web IQ tool disabled this turn")

        if fabric_user_token and FABRIC_DATA_AGENT_MCP_URL:
            # NB: Fabric routes MCP requests through a redirect layer -- the
            # client MUST set follow_redirects=True or every call fails with a
            # misleading 500 Internal Server Error.
            fabric_http_client = httpx.AsyncClient(
                auth=_BearerTokenAuth(fabric_user_token), timeout=120.0, follow_redirects=True
            )
            clients.append(fabric_http_client)
            tools.append(
                MCPStreamableHTTPTool(
                    name="network-ontology",
                    url=FABRIC_DATA_AGENT_MCP_URL,
                    http_client=fabric_http_client,
                    load_prompts=False,
                )
            )
        elif not FABRIC_DATA_AGENT_MCP_URL:
            logger.warning("⚠️ FABRIC_DATA_AGENT_MCP_URL not set — Fabric IQ tool disabled this turn")

        if not foundry_user_token:
            return tools, clients

        toolbox_endpoint = f"{PROJECT_ENDPOINT.rstrip('/')}/toolboxes/{WORKIQ_TOOLBOX_NAME}/mcp?api-version=v1"
        tools.append(
            FoundryToolbox(
                credential=_StaticTokenCredential(foundry_user_token),
                url=toolbox_endpoint,
                name="work_iq_toolbox",
                load_prompts=False,
            )
        )

        return tools, clients

    # -------------------------------------------------------------------
    # MESSAGE PROCESSING
    # -------------------------------------------------------------------

    async def _connect_tools(self, tools: list) -> tuple[list, AsyncExitStack]:
        """Pre-connect each tool with a bounded timeout, in isolation.

        agent_framework's _prepare_run_context connects any not-yet-connected
        MCP tool with `enter_async_context()` right before the turn runs. If
        one tool hangs (observed live with the Work IQ toolbox -- Foundry IQ,
        Web IQ, and Fabric IQ connect fine, but the 4th tool's initialize()
        never completes), that hang surfaces as a misleading "Cancelled via
        cancel scope ..." anyio error that kills the *entire* turn, taking
        down the 3 healthy tools with it. Connecting each tool ourselves
        first, with a timeout, drops only the bad tool for this turn --
        connecting it here sets `tool.is_connected = True`, so the library's
        own connect loop just skips it.
        """
        stack = AsyncExitStack()
        healthy: list = []
        for tool in tools:
            try:
                await asyncio.wait_for(
                    stack.enter_async_context(tool), timeout=TOOL_CONNECT_TIMEOUT_SECONDS
                )
                healthy.append(tool)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "⚠️ Tool '%s' failed to connect within %.0fs, skipping for this turn: %s",
                    getattr(tool, "name", tool),
                    TOOL_CONNECT_TIMEOUT_SECONDS,
                    exc,
                )
        return healthy, stack

    async def process_user_message(
        self,
        message: str,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> str:
        """Run one turn of the MAF NOC agent, adding OBO-scoped tools for this user."""
        from_prop = context.activity.from_property
        user_id = getattr(from_prop, "id", "default") if from_prop else "default"
        display_name = getattr(from_prop, "name", None) or "unknown"
        logger.info("📨 Message from %s (%s): %s...", display_name, user_id, message[:80])

        foundry_user_token = await self._exchange_user_token(
            auth, auth_handler_name, context, FOUNDRY_USER_TOKEN_SCOPES
        )
        fabric_user_token = await self._exchange_user_token(
            auth, auth_handler_name, context, FABRIC_SCOPE
        )
        history: list[Message] = self._conversations.get(user_id, [])
        history.append(Message("user", [message]))

        # ponytail: real root cause of the "Cancelled via cancel scope ..."
        # bug was two Teams-redelivered messages racing on the SAME shared,
        # connect-once Foundry IQ/Web IQ tool instances (fixed by making all
        # 4 tools per-turn in _build_turn_tools). This retry is a leftover
        # safety net for any other transient MCP-init hiccup.
        for attempt in range(2):
            turn_tools, turn_clients = self._build_turn_tools(foundry_user_token, fabric_user_token)
            connected_tools, tool_stack = await self._connect_tools(turn_tools)
            try:
                response = await self._agent.run(history, tools=connected_tools)
                self._conversations[user_id] = history + [Message("assistant", [response.text])]
                return response.text or "I processed your request but couldn't generate a response."
            except McpError as exc:
                consent_url = _extract_a2a_consent_url(exc)
                if consent_url:
                    return f"{_WORK_IQ_CONSENT_PREFIX}{consent_url}"
                logger.error("❌ MCP tool error: %s", exc, exc_info=True)
                return f"Sorry, one of my tools failed: {exc}"
            except Exception as exc:  # noqa: BLE001
                if attempt == 0 and "cancel scope" in str(exc).lower():
                    logger.warning("⚠️ Transient MCP init cancellation, retrying once: %s", exc)
                    continue
                logger.error("❌ Error processing message: %s", exc, exc_info=True)
                self._conversations.pop(user_id, None)
                return f"Sorry, I encountered an error: {exc}"
            finally:
                await tool_stack.aclose()
                for client in turn_clients:
                    await client.aclose()
        return "Sorry, I encountered a repeated error and could not complete this request."

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
                email_body = getattr(email, "html_body", "") or getattr(email, "body", "")
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
    # OBO TOKEN EXCHANGE (Fabric Data Agent + Work IQ require user delegation)
    # -------------------------------------------------------------------

    async def _exchange_user_token(
        self,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
        scope: str,
    ) -> Optional[str]:
        """Get a user-delegated token via the AgenticUserAuthorization handler.

        The A365 platform (with inheritable permissions configured on the
        blueprint) provides user-delegated tokens through this exchange. This
        token allows Fabric Data Agent and Work IQ to act on behalf of the
        Teams user rather than a service identity.

        `scope` must match the AUDIENCE of the resource being called (Work IQ
        lives under the Foundry project -> ai.azure.com; Fabric IQ's Data
        Agent lives under api.fabric.microsoft.com) -- an access token minted
        for one audience is rejected by the other, and that rejection is
        mis-surfaced by the mcp/anyio client as "Cancelled via cancel scope
        ...", not a clean 401 (see docs/TROUBLESHOOTING.md).
        """
        if not auth_handler_name:
            logger.warning("⚠️ No auth handler configured — Fabric IQ/Work IQ will be unavailable this turn")
            return None

        try:
            token_response = await auth.exchange_token(
                context, scopes=[scope], auth_handler_id=auth_handler_name
            )
            if token_response and token_response.token:
                logger.info("✅ User OBO token acquired (len=%d)", len(token_response.token))
                return token_response.token
            logger.warning("⚠️ Token exchange returned empty response")
        except Exception as exc:  # noqa: BLE001
            logger.warning("⚠️ OBO token exchange failed: %s", exc, exc_info=True)
        return None
