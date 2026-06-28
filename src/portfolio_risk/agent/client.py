"""Portfolio-risk agent entrypoint.

Dispatches to either:
- the deterministic **mock agent** (default when no ANTHROPIC_API_KEY), or
- **real Claude** (claude-opus-4-8) driving the MCP server over stdio via the
  Anthropic local-MCP helpers + tool_runner.

CLI:  python -m portfolio_risk.agent.client "What is the 95% VaR of 60% AAPL / 40% MSFT?"
"""

from __future__ import annotations

import hashlib
import json
import sys

from .. import config
from ..cache import cache_get_json, cache_set_json
from .base import AgentResult
from .prompts import SYSTEM_PROMPT

# Prompt caching: render order is tools -> system -> messages, so a single
# cache_control breakpoint on the system block caches the whole stable prefix
# (the 22 tool schemas + this system prompt). The tool_runner re-sends that
# prefix on every iteration of the agentic loop and on every question, so it is
# written once (~1.25x) and then read at ~0.1x for the 5-minute TTL. Built once,
# byte-for-byte identical at both call sites — any drift would split the cache.
_SYSTEM_BLOCKS = [
    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
]


def _parse_tool_result_content(content) -> object:
    """Turn a tool_result's content (str or list of text blocks) into a Python
    object — JSON-decoded when possible, else the raw text."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        text = "".join(parts)
    else:
        return content
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return text


def _backfill_tool_outputs(runner, tool_calls: list[dict]) -> None:
    """Best-effort: copy each tool's result into ``tool_calls[i]['output']``.

    The runner keeps the full conversation (incl. the tool_result messages it
    generates) in its params; we match tool_result blocks to our recorded
    tool_use ids. Never raises — retrieval is deterministic, so the eval's
    groundedness checker can re-derive the evidence if this can't.
    """
    try:
        messages = runner._params.get("messages", [])  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return
    by_id = {c["_id"]: c for c in tool_calls if c.get("_id")}
    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if not isinstance(content, list):
            continue
        for block in content:
            btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if btype != "tool_result":
                continue
            tuid = block.get("tool_use_id") if isinstance(block, dict) else getattr(block, "tool_use_id", None)
            call = by_id.get(tuid)
            if call is not None:
                raw = block.get("content") if isinstance(block, dict) else getattr(block, "content", None)
                call["output"] = _parse_tool_result_content(raw)

# Cost-saving cache for real-Claude answers (shared via Redis when configured,
# else in-process). Repeated identical questions are served free (no API call).
_RESPONSE_TTL_SEC = 900.0  # 15 minutes


def _ans_key(question: str) -> str:
    norm = " ".join(question.split()).lower()
    return "ans:v1:" + hashlib.sha1(norm.encode()).hexdigest()


def run_agent(question: str) -> AgentResult:
    """Synchronous entry point. Chooses mock vs. real Claude automatically."""
    if config.use_mock_llm():
        from . import mock_agent

        return mock_agent.run(question)

    import asyncio

    key = _ans_key(question)
    hit = cache_get_json(key)
    if hit:
        return AgentResult(
            answer=hit.get("answer", ""),
            tool_calls=[{"name": n, "input": {}, "output": None} for n in hit.get("tools", [])],
        )

    result = asyncio.run(_run_claude(question))
    if result.answer:
        cache_set_json(key, {"answer": result.answer, "tools": result.tool_names()}, _RESPONSE_TTL_SEC)
    return result


async def _run_claude(question: str) -> AgentResult:
    """Real Claude path: stdio MCP -> tool_runner -> final answer."""
    import anthropic
    from anthropic.lib.tools.mcp import async_mcp_tool
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "portfolio_risk.server.mcp_server"],
    )

    tool_calls: list[dict] = []
    final_text = ""

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = [async_mcp_tool(t, session) for t in listed.tools]

            runner = client.beta.messages.tool_runner(
                model=config.MODEL,
                max_tokens=config.MAX_TOKENS,
                thinking={"type": "adaptive"},
                output_config={"effort": config.EFFORT},
                system=_SYSTEM_BLOCKS,
                messages=[{"role": "user", "content": question}],
                tools=tools,
            )

            async for message in runner:
                for block in message.content:
                    btype = getattr(block, "type", None)
                    if btype == "tool_use":
                        tool_calls.append(
                            {
                                "name": block.name,
                                "input": dict(block.input),
                                "output": None,
                                "_id": block.id,
                            }
                        )
                    elif btype == "text":
                        final_text = block.text

            _backfill_tool_outputs(runner, tool_calls)

    for call in tool_calls:
        call.pop("_id", None)
    return AgentResult(answer=final_text, tool_calls=tool_calls)


def stream_agent_events(question: str):
    """Yield progress events for a question as plain dicts (for SSE).

    Event shapes:
      {"type": "tool", "name": str}      — a tool was invoked
      {"type": "text", "text": str}      — a chunk of answer text
      {"type": "done", "tools": [str]}   — finished
      {"type": "error", "error": str}    — failure

    The mock agent yields its tools then its full answer in one shot. The real
    Claude path streams tool-use + text blocks as the agentic loop runs, via a
    background thread + queue so the MCP subprocess gets its own event loop
    (mirrors the proven run_agent threading model).
    """
    if config.use_mock_llm():
        from . import mock_agent

        result = mock_agent.run(question)
        for call in result.tool_calls:
            yield {"type": "tool", "name": call["name"]}
        yield {"type": "text", "text": result.answer}
        yield {"type": "done", "tools": result.tool_names()}
        return

    import asyncio
    import queue
    import threading

    # Serve repeated identical questions from cache — instant, no API spend.
    key = _ans_key(question)
    hit = cache_get_json(key)
    if hit:
        tools = hit.get("tools", [])
        for name in tools:
            yield {"type": "tool", "name": name}
        if hit.get("answer"):
            yield {"type": "text", "text": hit["answer"]}
        yield {"type": "done", "tools": tools, "cached": True}
        return

    q: "queue.Queue" = queue.Queue()

    def worker() -> None:
        try:
            asyncio.run(_run_claude_stream(question, q))
        except Exception as exc:  # noqa: BLE001
            q.put({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            q.put(None)  # sentinel

    threading.Thread(target=worker, daemon=True).start()

    text_parts: list[str] = []
    tools_used: list[str] = []
    errored = False
    while True:
        item = q.get()
        if item is None:
            break
        kind = item.get("type")
        if kind == "tool":
            tools_used.append(item["name"])
        elif kind == "text":
            text_parts.append(item["text"])
        elif kind == "error":
            errored = True
        yield item

    # Cache the full answer (blocks joined with blank lines, so markdown headings
    # render correctly) for next time.
    if not errored and text_parts:
        cache_set_json(
            key, {"answer": "\n\n".join(text_parts), "tools": tools_used}, _RESPONSE_TTL_SEC
        )


async def _run_claude_stream(question: str, q) -> None:
    """Real Claude agentic loop that pushes progress events onto ``q``."""
    import anthropic
    from anthropic.lib.tools.mcp import async_mcp_tool
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    client = anthropic.AsyncAnthropic()
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "portfolio_risk.server.mcp_server"],
    )
    tools_used: list[str] = []

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = [async_mcp_tool(t, session) for t in listed.tools]

            runner = client.beta.messages.tool_runner(
                model=config.MODEL,
                max_tokens=config.MAX_TOKENS,
                thinking={"type": "adaptive"},
                output_config={"effort": config.EFFORT},
                system=_SYSTEM_BLOCKS,
                messages=[{"role": "user", "content": question}],
                tools=tools,
            )

            async for message in runner:
                for block in message.content:
                    btype = getattr(block, "type", None)
                    if btype == "tool_use":
                        tools_used.append(block.name)
                        q.put({"type": "tool", "name": block.name})
                    elif btype == "text" and block.text:
                        q.put({"type": "text", "text": block.text})

    q.put({"type": "done", "tools": tools_used})


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python -m portfolio_risk.agent.client "your question"')
        raise SystemExit(2)

    question = " ".join(sys.argv[1:])
    mode = "mock agent (no API key)" if config.use_mock_llm() else f"Claude ({config.MODEL})"
    print(f"[mode: {mode}]\n")
    result = run_agent(question)
    if result.tool_calls:
        print("Tools used: " + ", ".join(result.tool_names()) + "\n")
    print(result.answer)


if __name__ == "__main__":
    main()
