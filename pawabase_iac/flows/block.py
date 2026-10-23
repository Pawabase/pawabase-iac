"""A configured block, and the node it becomes inside a flow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .catalogue import BLOCKS

if TYPE_CHECKING:
    from .flow import Flow


class Block:
    """A block with its settings, before it belongs to a flow. Made by the functions in ``blocks.<family>``."""

    def __init__(self, key: str, config: dict[str, Any] | None = None) -> None:
        self.key = key
        self.config = {k: v for k, v in (config or {}).items() if v is not None}
        self.node_id: str | None = None

    def named(self, node_id: str) -> Block:
        """Give the node this block becomes a readable id (used in ``ctx.steps.<id>.output``): ``blocks.resource.get(...).named("student")``."""
        self.node_id = node_id
        return self

    @property
    def handles(self) -> list[str]:
        return list(BLOCKS.get(self.key, {}).get("handles", []))

    def __repr__(self) -> str:
        return f"Block({self.key!r}, {self.config!r})"


class Node:
    """A block placed in a flow. ``a >> b`` follows ``next``; ``a.on("true") >> b`` or ``a.true >> b`` follows another handle."""

    def __init__(self, flow: Flow, id: str, block: Block) -> None:
        self.flow, self.id, self.block = flow, id, block

    def on(self, handle: str) -> Port:
        known = self.block.handles
        if known and "*" not in known and handle not in known and handle != "error":
            raise ValueError(f"{self.block.key} has no {handle!r} handle (it has: {', '.join(known)}; every block also has 'error')")
        return Port(self, handle)

    def __getattr__(self, name: str) -> Port:
        # `node.true`, `node.missing`, `node.done`…: the block's own handles as attributes.
        if name.startswith("_") or name in ("flow", "id", "block"):
            raise AttributeError(name)
        if name in self.block.handles or name == "error":
            return Port(self, name)
        raise AttributeError(f"{self.block.key} has no handle {name!r} (handles: {', '.join(self.block.handles) or 'none'})")

    def __rshift__(self, target: Node | Block) -> Node:
        return Port(self, "next") >> target

    def __repr__(self) -> str:
        return f"Node({self.id!r}, {self.block.key})"


class Port:
    """One outgoing handle of a node."""

    def __init__(self, node: Node, handle: str) -> None:
        self.node, self.handle = node, handle

    def __rshift__(self, target: Node | Block) -> Node:
        if isinstance(target, Block):
            target = self.node.flow.add(target)
        self.node.flow.connect(self.node, target, self.handle)
        return target
