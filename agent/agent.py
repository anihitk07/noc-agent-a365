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

import json
import logging
import os
import time
from collections.abc import Generator
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
    """Return the app-level (non-user) credential used for Foundry IQ + the model."""
    if "FOUNDRY_HOSTING_ENVIRONMENT" in os.environ:
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
        self._foundry_iq_http_client: Optional[httpx.AsyncClient] = None
        self._web_iq_http_client: Optional[httpx.AsyncClient] = None
        self._foundry_iq_tool: Optional[MCPStreamableHTTPTool] = None
        self._web_iq_tool: Optional[MCPStreamableHTTPTool] = None
        self._chat_client: Optional[FoundryChatClient] = None
        self._agent: Optional[Agent] = None
        # Per-user conversation history for context continuity across turns.
        self._conversations: dict[str, list] = {}

    # -------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------

    async def initialize(self) -> None:
        """Build the shared (non-user-scoped) tools and the MAF agent."""
        logger.info("🔌 Initializing NOC agent against %s", PROJECT_ENDPOINT)

        service_token = self._service_credential.get_token(SEARCH_SCOPE).token
        self._foundry_iq_http_client = httpx.AsyncClient(
            auth=_BearerTokenAuth(service_token), timeout=120.0
        )
        knowledge_base_endpoint = (
            f"{SEARCH_ENDPOINT.rstrip('/')}/knowledgebases/{KNOWLEDGE_BASE_NAME}"
            "/mcp?api-version=2026-05-01-preview"
        )
        self._foundry_iq_tool = MCPStreamableHTTPTool(
            name="knowledge-base",
            url=knowledge_base_endpoint,
            http_client=self._foundry_iq_http_client,
            allowed_tools=["knowledge_base_retrieve"],
            load_prompts=False,
        )
        logger.info("✅ Foundry IQ tool wired: %s", knowledge_base_endpoint)

        default_tools: list = [self._foundry_iq_tool]

        if WEB_IQ_API_KEY:
            self._web_iq_http_client = httpx.AsyncClient(
                headers={"x-apikey": WEB_IQ_API_KEY}, timeout=60.0
            )
            self._web_iq_tool = MCPStreamableHTTPTool(
                name="web-search",
                url=WEB_IQ_MCP_ENDPOINT,
                http_client=self._web_iq_http_client,
                load_prompts=False,
            )
            default_tools.append(self._web_iq_tool)
            logger.info("✅ Web IQ tool wired: %s", WEB_IQ_MCP_ENDPOINT)
        else:
            logger.warning("⚠️ WEB_IQ_API_KEY not set — Web IQ tool disabled")

        self._chat_client = FoundryChatClient(
            project_endpoint=PROJECT_ENDPOINT,
            model=MODEL_DEPLOYMENT_NAME,
            credential=self._service_credential,
        )
        self._agent = Agent(
            client=self._chat_client,
            name="NocAgent",
            instructions=NOC_AGENT_INSTRUCTIONS,
            tools=default_tools,
            default_options={"store": False},
        )
        logger.info("✅ NOC agent ready (%d default tools)", len(default_tools))

    async def cleanup(self) -> None:
        """Close any open HTTP clients."""
        for client in (self._foundry_iq_http_client, self._web_iq_http_client):
            if client is not None:
                await client.aclose()
        logger.info("🧹 Agent cleanup completed")

    # -------------------------------------------------------------------
    # PER-TURN, USER-SCOPED (OBO) TOOLS -- Fabric IQ + Work IQ
    # -------------------------------------------------------------------

    def _build_obo_tools(self, user_token: Optional[str]) -> tuple[list, list[httpx.AsyncClient]]:
        """Build Fabric IQ + Work IQ tools scoped to one user's OBO token for one turn.

        Returns (tools, http_clients_to_close) -- the caller must close the
        clients after the run() call completes, since MCPStreamableHTTPTool
        needs its auth attached at construction/session-init time, not applied
        later via a header_provider.
        """
        if not user_token:
            return [], []

        tools: list = []
        clients: list[httpx.AsyncClient] = []

        if FABRIC_DATA_AGENT_MCP_URL:
            # NB: Fabric routes MCP requests through a redirect layer -- the
            # client MUST set follow_redirects=True or every call fails with a
            # misleading 500 Internal Server Error.
            fabric_http_client = httpx.AsyncClient(
                auth=_BearerTokenAuth(user_token), timeout=120.0, follow_redirects=True
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
        else:
            logger.warning("⚠️ FABRIC_DATA_AGENT_MCP_URL not set — Fabric IQ tool disabled this turn")

        toolbox_endpoint = f"{PROJECT_ENDPOINT.rstrip('/')}/toolboxes/{WORKIQ_TOOLBOX_NAME}/mcp?api-version=v1"
        tools.append(
            FoundryToolbox(
                credential=_StaticTokenCredential(user_token),
                url=toolbox_endpoint,
                name="work_iq_toolbox",
                load_prompts=False,
            )
        )

        return tools, clients

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
        """Run one turn of the MAF NOC agent, adding OBO-scoped tools for this user."""
        from_prop = context.activity.from_property
        user_id = getattr(from_prop, "id", "default") if from_prop else "default"
        display_name = getattr(from_prop, "name", None) or "unknown"
        logger.info("📨 Message from %s (%s): %s...", display_name, user_id, message[:80])

        user_token = await self._exchange_user_token(auth, auth_handler_name, context)
        obo_tools, obo_clients = self._build_obo_tools(user_token)

        try:
            history: list[Message] = self._conversations.get(user_id, [])
            history.append(Message("user", [message]))

            response = await self._agent.run(history, tools=obo_tools)

            self._conversations[user_id] = history + [Message("assistant", [response.text])]
            return response.text or "I processed your request but couldn't generate a response."
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
        finally:
            for client in obo_clients:
                await client.aclose()

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
        self, auth: Authorization, auth_handler_name: Optional[str], context: TurnContext
    ) -> Optional[str]:
        """Get a user-delegated token via the AgenticUserAuthorization handler.

        The A365 platform (with inheritable permissions configured on the
        blueprint) provides user-delegated tokens through this exchange. This
        token allows Fabric Data Agent and Work IQ to act on behalf of the
        Teams user rather than a service identity.
        """
        scopes = [s.strip() for s in FOUNDRY_USER_TOKEN_SCOPES.split(",") if s.strip()]
        if not auth_handler_name:
            logger.warning("⚠️ No auth handler configured — Fabric IQ/Work IQ will be unavailable this turn")
            return None

        try:
            token_response = await auth.exchange_token(
                context, scopes=scopes, auth_handler_id=auth_handler_name
            )
            if token_response and token_response.token:
                logger.info("✅ User OBO token acquired (len=%d)", len(token_response.token))
                return token_response.token
            logger.warning("⚠️ Token exchange returned empty response")
        except Exception as exc:  # noqa: BLE001
            logger.warning("⚠️ OBO token exchange failed: %s", exc, exc_info=True)
        return None
