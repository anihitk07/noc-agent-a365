# Copyright (c) Microsoft. All rights reserved.

"""Self-check for _connect_tools() (see docs/TROUBLESHOOTING.md, "Teams turn
produces zero reply at all").

Regressions reproduced here:
1. A tool whose __aenter__ swallows cancellation and never actually stops.
   Plain `asyncio.wait_for(coro, t)` hangs forever in that case (it awaits
   the cancelled coroutine to finish before raising TimeoutError).
   `_connect_tools()`'s shield-based rewrite must still return, dropping
   only the misbehaving tool, within a bounded time.
2. A tool whose __aenter__ raises a bare anyio `BaseExceptionGroup` wrapping
   a `CancelledError` (a `BaseException`, not an `Exception`) -- observed
   live from Fabric IQ's intermittent MCP-init flakiness. A plain
   `except Exception` misses this; `_connect_tools()` must catch
   `BaseException` to still drop just that tool instead of the whole turn
   raising uncaught.
3. Several healthy tools connected one after another must all register and
   later close cleanly on the shared `AsyncExitStack` (this is inherently
   safe now that connects are sequential, not concurrent -- an earlier,
   reverted version of this fix ran connects via asyncio.gather() and
   corrupted the shared stack under concurrent registration).

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


class _ExceptionGroupTool:
    """Simulates the observed live Fabric IQ flakiness: __aenter__ raises a
    bare anyio BaseExceptionGroup wrapping a CancelledError. CancelledError
    is a BaseException, not an Exception, since Python 3.8 -- so a
    BaseExceptionGroup containing one is itself NOT an Exception subclass
    and slips straight through a plain `except Exception`."""

    name = "exception_group_tool"

    async def __aenter__(self):
        raise BaseExceptionGroup("unhandled errors in a TaskGroup", [asyncio.CancelledError()])

    async def __aexit__(self, *exc_info):
        return False


async def check_hang_is_contained() -> None:
    agent = NocAgent()  # __init__ does no I/O, safe without real credentials

    start = time.monotonic()
    healthy, stack = await asyncio.wait_for(
        agent._connect_tools([_HealthyTool(), _HangingTool()]),
        # Generous outer bound: proves _connect_tools() itself returns
        # rather than hanging forever.
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


async def check_exception_group_is_caught() -> None:
    """Regression test: a tool whose __aenter__ raises a bare
    BaseExceptionGroup (observed live from Fabric IQ) must be dropped
    gracefully, not propagate out of _connect_tools() uncaught."""
    agent = NocAgent()
    healthy, stack = await asyncio.wait_for(
        agent._connect_tools([_HealthyTool(), _ExceptionGroupTool()]),
        timeout=TOOLS_CONNECT_TOTAL_TIMEOUT_SECONDS + 5,
    )
    assert [t.name for t in healthy] == ["healthy_tool"], (
        f"expected only the healthy tool to survive, got {[getattr(t, 'name', t) for t in healthy]}"
    )
    await asyncio.wait_for(stack.aclose(), timeout=5)
    print("OK: a tool raising a bare BaseExceptionGroup was dropped without killing the turn")


async def check_multiple_healthy_tools_connect_and_close_cleanly() -> None:
    """Several tools connected one after another (sequentially, by design --
    see _connect_tools()'s docstring for why concurrency was reverted) must
    all register onto the shared AsyncExitStack and later have __aexit__
    actually invoked exactly once via stack.aclose()."""
    agent = NocAgent()
    tools = [_HealthyTool(f"tool_{i}") for i in range(5)]

    healthy, stack = await asyncio.wait_for(
        agent._connect_tools(tools), timeout=TOOLS_CONNECT_TOTAL_TIMEOUT_SECONDS + 5
    )
    assert len(healthy) == 5, f"expected all 5 healthy tools to survive, got {len(healthy)}"

    await asyncio.wait_for(stack.aclose(), timeout=5)
    assert all(t.exited for t in tools), "not every healthy tool's __aexit__ ran"
    print("OK: 5 sequentially-connected tools all registered and closed cleanly on the shared stack")


async def main() -> None:
    await check_hang_is_contained()
    await check_exception_group_is_caught()
    await check_multiple_healthy_tools_connect_and_close_cleanly()

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
