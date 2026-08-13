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
import json
import logging
import os
from typing import Optional

from agent_framework import Agent, MCPStreamableHTTPTool, Message
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

# ponytail: a native Foundry tool call still round-trips over the network
# server-side, so agent.run() keeps its own wall-clock cap rather than being
# able to hang the turn forever if Foundry's own tool-call plumbing stalls.
AGENT_RUN_TIMEOUT_SECONDS = float(os.getenv("AGENT_RUN_TIMEOUT_SECONDS", "90"))

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

        The Toolbox itself resolves each bundled connection's own auth
        (CustomKeys for Web IQ, service identity for Foundry IQ). Fabric
        IQ/Work IQ's UserEntraToken connections instead forward whatever
        identity authenticated *this HTTP call to the toolbox* -- so the
        calling Teams user's OBO token is injected here as the Authorization
        header when available; otherwise the toolbox call (and therefore
        Fabric IQ/Work IQ) falls back to the service identity, in which case
        those two tools will simply return "no access"/empty results rather
        than another user's data (graceful degradation, same contract as
        before).
        """
        if not self._toolbox_mcp_url:
            logger.error("❌ No toolbox MCP URL available -- this turn will have no tools")
            return None

        if foundry_user_token:
            bearer_token = foundry_user_token
        else:
            logger.warning(
                "⚠️ No user OBO token this turn — Fabric IQ/Work IQ (identity passthrough) "
                "will fall back to the service identity and likely return no data"
            )
            bearer_token = self._service_credential.get_token(FOUNDRY_USER_TOKEN_SCOPES).token

        def _header_provider(_kwargs: dict) -> dict[str, str]:
            return {"Authorization": f"Bearer {bearer_token}"}

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
            auth, auth_handler_name, context, FOUNDRY_USER_TOKEN_SCOPES
        )
        history: list[Message] = self._conversations.get(user_id, [])
        history.append(Message("user", [message]))

        turn_tool = self._build_turn_tool(foundry_user_token)
        turn_tools = [turn_tool] if turn_tool else []

        run_task = asyncio.ensure_future(self._agent.run(history, tools=turn_tools))
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
        finally:
            if turn_tool is not None:
                try:
                    await turn_tool.close()
                except Exception:  # noqa: BLE001
                    logger.debug("Toolbox tool close() raised (non-fatal)", exc_info=True)

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
        blueprint) provides a user-delegated token through this exchange,
        scoped to `https://ai.azure.com/.default`. This single token is used
        to build the whole per-turn FoundryChatClient/Agent as the calling
        Teams user; Foundry's own service then performs its own server-side
        OBO exchange from this identity to each UserEntraToken-typed tool
        connection's real audience (Fabric IQ -> api.fabric.microsoft.com,
        Work IQ -> its own audience) -- so only one token exchange is needed
        here, unlike the old local-MCP-client design which needed a separate
        per-tool-audience token (see docs/TROUBLESHOOTING.md).
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
