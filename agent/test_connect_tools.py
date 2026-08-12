# Copyright (c) Microsoft. All rights reserved.

"""Self-check for the _connect_tools() hang + shared-stack-corruption fixes
(see docs/TROUBLESHOOTING.md, "Teams turn produces zero reply at all").

Two regressions reproduced here:
1. A tool whose __aenter__ swallows cancellation and never actually stops.
   Plain `asyncio.wait_for(coro, t)` hangs forever in that case (it awaits
   the cancelled coroutine to finish before raising TimeoutError).
   `_connect_tools()`'s shield-based rewrite must still return, dropping
   only the misbehaving tool, within a bounded time.
2. Connecting tools concurrently while every task registers onto the SAME
   shared `AsyncExitStack` corrupts its callback bookkeeping. Every healthy
   tool must still connect and later close cleanly.

Run directly: python agent/test_connect_tools.py
"""

import asyncio
import os
import sys
import time
import types

# _connect_tools() doesn't touch these, but importing agent.py requires them.
os.environ.setdefault("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid/api/projects/dummy")
os.environ.setdefault("AZURE_AI_MODEL_DEPLOYMENT_NAME", "dummy-model")
os.environ.setdefault("AZURE_AI_SEARCH_SERVICE_ENDPOINT", "https://example.invalid")
os.environ.setdefault("TOOL_CONNECT_TIMEOUT_SECONDS", "1")  # keep the test fast


def _stub_module(name: str, **attrs):
    """Install a minimal stub so agent.py's heavy SDK imports resolve without
    the real (version-pinned, network-touching) packages installed -- this
    test only exercises _connect_tools()'s pure-asyncio control flow."""
    mod = types.ModuleType(name)
    for attr_name, value in attrs.items():
        setattr(mod, attr_name, value)
    sys.modules[name] = mod
    return mod


class _Dummy:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, item):
        return _Dummy()

    def __call__(self, *a, **k):
        return _Dummy()


_stub_module("agent_framework", Agent=_Dummy, MCPStreamableHTTPTool=_Dummy, Message=_Dummy)
_stub_module("agent_framework.foundry", FoundryChatClient=_Dummy)
_stub_module("agent_framework_foundry_hosting", FoundryToolbox=_Dummy)
_stub_module("microsoft_agents_a365")
_stub_module("microsoft_agents_a365.notifications")
_stub_module("microsoft_agents_a365.notifications.agent_notification", NotificationTypes=_Dummy)

sys.path.insert(0, os.path.dirname(__file__))
from agent import NocAgent, TOOL_CONNECT_TIMEOUT_SECONDS, TOOLS_CONNECT_TOTAL_TIMEOUT_SECONDS  # noqa: E402


class _HealthyTool:
    """Connects instantly -- should end up in the healthy list."""

    def __init__(self, name: str = "healthy_tool"):
        self.name = name
        self.exited = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        self.exited = True
        return False


class _HangingTool:
    """Simulates the observed anyio hazard: __aenter__ swallows the
    CancelledError sent by wait_for's internal timeout cancellation and just
    keeps running forever instead of unwinding. This is what made the old
    plain `asyncio.wait_for(coro, timeout)` call hang indefinitely."""

    name = "hanging_tool"

    async def __aenter__(self):
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                continue  # swallow cancellation -- never actually stops

    async def __aexit__(self, *exc_info):
        return False


async def check_hang_is_contained() -> None:
    agent = NocAgent()  # __init__ does no I/O, safe without real credentials

    start = time.monotonic()
    healthy, stack = await asyncio.wait_for(
        agent._connect_tools([_HealthyTool(), _HangingTool()]),
        # Generous outer bound: proves _connect_tools() itself returns
        # (via its own internal watchdog) rather than hanging forever.
        timeout=TOOLS_CONNECT_TOTAL_TIMEOUT_SECONDS + 5,
    )
    elapsed = time.monotonic() - start

    assert [t.name for t in healthy] == ["healthy_tool"], (
        f"expected only the healthy tool to survive, got {[getattr(t, 'name', t) for t in healthy]}"
    )
    assert elapsed < TOOLS_CONNECT_TOTAL_TIMEOUT_SECONDS + 5, f"_connect_tools() did not return in time ({elapsed:.1f}s)"
    print(f"OK: _connect_tools() returned in {elapsed:.1f}s with only the healthy tool, hang was contained")

    await asyncio.wait_for(stack.aclose(), timeout=5)
    print("OK: stack.aclose() for the surviving tool returned promptly")


async def check_concurrent_connects_dont_corrupt_shared_stack() -> None:
    """Regression test for the SECOND bug this fix uncovered: connecting
    tools concurrently via asyncio.gather() while every task called
    `stack.enter_async_context()` on the SAME shared AsyncExitStack
    corrupted its callback bookkeeping (observed live as "Could not cleanly
    close MCP exit stack ... unhandled errors in a TaskGroup", and an
    exception that escaped _connect_tools()'s own try/except entirely,
    silently killing the whole turn with nothing logged). Every healthy
    tool here must connect AND, later, have __aexit__ actually invoked
    exactly once via stack.aclose() -- proving the shared stack survives
    genuine concurrent registration intact."""
    agent = NocAgent()
    tools = [_HealthyTool(f"tool_{i}") for i in range(5)] + [_HangingTool()]

    healthy, stack = await asyncio.wait_for(
        agent._connect_tools(tools), timeout=TOOLS_CONNECT_TOTAL_TIMEOUT_SECONDS + 5
    )
    assert len(healthy) == 5, f"expected all 5 healthy tools to survive concurrent connect, got {len(healthy)}"

    await asyncio.wait_for(stack.aclose(), timeout=5)
    assert all(t.exited for t in tools if isinstance(t, _HealthyTool)), (
        "not every healthy tool's __aexit__ ran -- shared AsyncExitStack was corrupted by concurrent registration"
    )
    print("OK: 5 concurrently-connected tools all registered and closed cleanly on the shared stack")


async def main() -> None:
    await check_hang_is_contained()
    await check_concurrent_connects_dont_corrupt_shared_stack()

    # ponytail: _HangingTool's __aenter__ deliberately never honors
    # cancellation (that's the whole point -- it's what a broken MCP
    # transport would look like). Its fire-and-forget cancelled Task is
    # intentionally leaked, exactly as it would be in the live app (which
    # keeps running with the leaked task in the background, harmlessly,
    # since nothing ever awaits it again). asyncio.run()'s normal shutdown
    # would instead try to cancel-and-await every outstanding task to
    # completion, which would hang on this one forever -- so exit the
    # process directly once the assertions above have already proven the
    # fix, instead of going through that irrelevant cleanup path.
    sys.stdout.flush()
    os._exit(0)



if __name__ == "__main__":
    asyncio.run(main())
