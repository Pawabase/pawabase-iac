"""Flows as code: add blocks, connect their handles, and get the node/edge document Studio edits.

    from pawabase_iac import Flow, blocks, ctx

    f = Flow("welcome", description="Greets a new user")
    start = f.add(blocks.trigger.event(event="auth.user.created"))
    mail = f.add(blocks.mail.send(to=ctx.input.email, template="welcome", data={"name": ctx.input.name}), id="mail")
    failed = f.add(blocks.log.write(message=ctx.text("welcome mail failed: ", ctx.error.message), level="error"))
    start >> mail
    mail.error >> failed

``a >> b`` follows the ``next`` handle; ``a.on("true") >> b`` (or ``a.true >> b``) follows a named one. ``a >> b >> c`` chains.
"""

from __future__ import annotations

import copy
from typing import Any

from ..core.base import NAME, Definition, plain
from .block import Block, Node
from .catalogue import BLOCKS
from .graph import graph_problems, layout


class Flow(Definition):
    """A named graph of blocks. Build it with :meth:`add` and ``>>``, or pass a finished ``definition`` dict."""

    kind = "flows"
    key_field = "name"

    def __init__(
        self,
        name: str,
        *,
        description: str = "",
        enabled: bool = True,
        timeout: float = 60.0,
        record_runs: bool = True,
        definition: dict[str, Any] | None = None,
    ) -> None:
        self.name, self.description, self.enabled = name, description, enabled
        self.timeout, self.record_runs = timeout, record_runs
        self.nodes: dict[str, Node] = {}
        self.edges: list[tuple[str, str, str]] = []
        self._raw = copy.deepcopy(definition) if definition is not None else None
        self._register()

    # ── building ────────────────────────────────────────────────────────

    def add(self, block: Block, id: str | None = None) -> Node:
        if self._raw is not None:
            raise ValueError(f"flow {self.name!r} was given a finished definition; it cannot also be built with add()")
        node_id = id or block.node_id or self._free_id(block.key)
        if node_id in self.nodes:
            raise ValueError(f"flow {self.name!r} already has a node {node_id!r}")
        node = self.nodes[node_id] = Node(self, node_id, block)
        return node

    def _free_id(self, key: str) -> str:
        base = key.replace(".", "_")
        if base not in self.nodes:
            return base
        number = 2
        while f"{base}_{number}" in self.nodes:
            number += 1
        return f"{base}_{number}"

    def __getitem__(self, node_id: str) -> Node:
        """A node by its id: ``flow["student"].missing >> not_found``."""
        try:
            return self.nodes[node_id]
        except KeyError:
            raise KeyError(f"flow {self.name!r} has no node {node_id!r} (nodes: {', '.join(self.nodes) or 'none'})") from None

    def connect(self, source: Node, target: Node, handle: str = "next") -> None:
        if source.flow is not self or target.flow is not self:
            raise ValueError("both nodes must belong to this flow")
        edge = (source.id, target.id, handle)
        if edge not in self.edges:
            self.edges.append(edge)

    def chain(self, *blocks: Block) -> list[Node]:
        """Add blocks one after another, each following the previous one's ``next`` handle."""
        nodes = [self.add(b) for b in blocks]
        for left, right in zip(nodes, nodes[1:], strict=False):
            left >> right
        return nodes

    # ── the stored document ─────────────────────────────────────────────

    def graph(self) -> dict[str, Any]:
        if self._raw is not None:
            return copy.deepcopy(self._raw)
        triggers = [n.id for n in self.nodes.values() if BLOCKS.get(n.block.key, {}).get("trigger")]
        positions = layout(list(self.nodes), self.edges, triggers)
        return {
            "nodes": [
                {
                    "id": node.id,
                    "type": "block",
                    "position": positions[node.id],
                    "data": {"block": node.block.key, "config": plain(copy.deepcopy(node.block.config), resolve=False)},
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {"id": f"{s}-{h}-{t}", "source": s, "target": t, **({"sourceHandle": h} if h != "next" else {})}
                for s, t, h in self.edges
            ],
        }

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "definition": self.graph(),
            "enabled": self.enabled,
            "timeout": self.timeout,
            "record_runs": self.record_runs,
        }

    def problems(self) -> list[str]:
        out: list[str] = []
        if not isinstance(self.name, str) or not NAME.match(self.name):
            out.append(f"flow name {self.name!r} is not a valid name")
        if not 0 < self.timeout <= 900:
            out.append("timeout is above 0 and at most 900 seconds")
        return out + graph_problems(self.graph())

    def __repr__(self) -> str:
        return f"Flow({self.name!r}, {len(self.nodes)} blocks)"
