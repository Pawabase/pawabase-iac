"""What an agent can use, as the settings the server takes. Each returns one entry for ``Agent(tools=[...])``.

    from pawabase_iac import Agent, tools

    Agent("support", model="chat", tools=[
        tools.table(orders, actions=["list", "get"]),
        tools.flow(refund, description="Refund an order", writes=True),
        tools.web_search(),
        tools.mcp(github),
    ])

Tables, flows, connections and other agents may be passed as the definitions themselves or by name. Anything that changes data
waits for a person unless ``approval="auto"`` says otherwise.
"""

from __future__ import annotations

from typing import Any, Literal

from ..core.base import ref_name

Approval = Literal["auto", "ask"]
TABLE_ACTIONS = ("list", "get", "create", "update", "delete")
NOTION_ACTIONS = ("search", "read", "create", "append")
KINDS = ("table", "flow", "web_fetch", "web_search", "notion", "mcp", "agent", "code", "image", "x_search", "tool_search")


def _clean(spec: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in spec.items() if v is not None}


def table(table: Any, actions: list[str] | tuple[str, ...] = ("list", "get"), *, approval: Approval | None = None, policy: Any = None, description: str | None = None) -> dict[str, Any]:
    """Find, open, add, change or delete a table's records, under the table's own policies when the agent runs as its caller."""
    return _clean({"kind": "table", "resource": ref_name(table), "actions": list(actions), "approval": approval, "policy": policy, "description": description})


def flow(flow: Any, *, description: str | None = None, name: str | None = None, input: dict[str, Any] | None = None, writes: bool = True, untrusted: bool = False, approval: Approval | None = None, policy: Any = None) -> dict[str, Any]:
    """Run one of your flows. ``input`` is a JSON schema for what the flow takes; ``writes=False`` says it only reads."""
    return _clean({"kind": "flow", "flow": ref_name(flow), "name": name, "description": description, "input": input, "writes": writes, "untrusted": untrusted or None, "approval": approval, "policy": policy})


def web_fetch(*, allow_hosts: list[str] | None = None, approval: Approval | None = None) -> dict[str, Any]:
    """Open an address and read it. Private addresses are always refused. ``allow_hosts`` limits it to those sites."""
    return _clean({"kind": "web_fetch", "allow_hosts": list(allow_hosts or []), "approval": approval})


def web_search(connection: Any = None, *, provider: Literal["duckduckgo", "model"] | None = None, approval: Approval | None = None) -> dict[str, Any]:
    """Search the web: with a Tavily or Exa connection, or with no key through DuckDuckGo (the default) or the model's own search."""
    if connection is not None:
        return _clean({"kind": "web_search", "connection": ref_name(connection), "approval": approval})
    return _clean({"kind": "web_search", "provider": provider or "duckduckgo", "approval": approval})


def notion(connection: Any, actions: list[str] | tuple[str, ...] = ("search", "read"), *, approval: Approval | None = None) -> dict[str, Any]:
    """Find, read, create and add to Notion pages through a Notion connection."""
    return _clean({"kind": "notion", "connection": ref_name(connection), "actions": list(actions), "approval": approval})


def mcp(connection: Any, *, only: list[str] | None = None, approval: Approval | None = None) -> dict[str, Any]:
    """Every tool of an MCP server (GitHub, Linear, Stripe, Zapier, Neon…), or just those in ``only``. A tool the server doesn't mark as read-only waits for a person."""
    return _clean({"kind": "mcp", "connection": ref_name(connection), "tools": list(only or []), "approval": approval})


def agent(agent: Any, *, description: str | None = None, name: str | None = None, writes: bool = True, approval: Approval | None = None) -> dict[str, Any]:
    """Hand part of the work to another agent."""
    return _clean({"kind": "agent", "agent": ref_name(agent), "name": name, "description": description, "writes": writes, "approval": approval})


def code() -> dict[str, Any]:
    """Run code in the model provider's own sandbox. Needs an Anthropic or Google model."""
    return {"kind": "code"}


def image(provider: str, model: str, *, description: str | None = None) -> dict[str, Any]:
    """Make images with an OpenAI or Google provider's image model; they are kept in the environment's storage and the agent gets their links."""
    return _clean({"kind": "image", "provider": provider, "model": model, "description": description})


def x_search(model: str, *, handles: list[str] | None = None) -> dict[str, Any]:
    """Search X through an xAI model of the environment (the agent itself may use any model). ``handles`` limits it to up to 20 accounts."""
    return _clean({"kind": "x_search", "model": model, "handles": list(handles or [])})


def tool_search() -> dict[str, Any]:
    """Keep apps' tools out of sight until the agent looks for one, so a big app doesn't crowd every request."""
    return {"kind": "tool_search"}


def problems(spec: Any, where: str) -> list[str]:
    """What the server's validator would say about one tool entry, judged without asking it."""
    if not isinstance(spec, dict):
        return [f"{where}: build tools with tools.table(...), tools.flow(...) and the others"]
    kind = spec.get("kind")
    out: list[str] = []
    if kind not in KINDS:
        return [f"{where}: unknown tool kind {kind!r} (one of {', '.join(KINDS)})"]
    if spec.get("approval") not in (None, "auto", "ask"):
        out.append(f"{where}: approval is auto or ask")
    if kind == "table":
        if not spec.get("resource"):
            out.append(f"{where}: name a table")
        bad = sorted(set(spec.get("actions") or []) - set(TABLE_ACTIONS))
        if bad:
            out.append(f"{where}: a table tool can't {', '.join(bad)} (it can {', '.join(TABLE_ACTIONS)})")
        if not spec.get("actions"):
            out.append(f"{where}: choose at least one action")
    elif kind == "flow" and not spec.get("flow"):
        out.append(f"{where}: name a flow")
    elif kind == "notion":
        if not spec.get("connection"):
            out.append(f"{where}: name a Notion connection")
        bad = sorted(set(spec.get("actions") or []) - set(NOTION_ACTIONS))
        if bad:
            out.append(f"{where}: Notion can't {', '.join(bad)} (it can {', '.join(NOTION_ACTIONS)})")
    elif kind == "mcp" and not spec.get("connection"):
        out.append(f"{where}: name an MCP connection")
    elif kind == "web_search" and not spec.get("connection") and spec.get("provider") not in ("duckduckgo", "model"):
        out.append(f"{where}: search with a connection, or provider duckduckgo or model")
    elif kind == "agent" and not spec.get("agent"):
        out.append(f"{where}: name an agent")
    elif kind == "image" and (not spec.get("provider") or not str(spec.get("model") or "").strip()):
        out.append(f"{where}: name the provider and its image model")
    elif kind == "x_search":
        if not spec.get("model"):
            out.append(f"{where}: name an xAI model of the environment")
        if len(spec.get("handles") or []) > 20:
            out.append(f"{where}: X search can be limited to at most 20 accounts")
    return out
