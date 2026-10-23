"""Checking a flow's graph against what the server says each block takes, and laying it out for Studio."""

from __future__ import annotations

import re
from collections import deque
from typing import Any

from ..expr.flow import FILTERS
from ..policies.check import condition_problems
from .catalogue import BLOCKS

#: Handles every block may follow, whatever it declares.
UNIVERSAL_HANDLES = frozenset({"error"})
_TEMPLATE = re.compile(r"\{\{|\{%")


def templated(value: Any) -> bool:
    """Whether a value is (or contains) a ``{{ }}`` template, which is only known when the flow runs."""
    if isinstance(value, str):
        return bool(_TEMPLATE.search(value))
    if isinstance(value, dict):
        return any(templated(v) for v in value.values())
    if isinstance(value, list):
        return any(templated(v) for v in value)
    return False


_TEMPLATE_PART = re.compile(r"\{\{\s*(.+?)\s*\}\}")
_LOOKUP = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)*$")


def template_problems(value: Any) -> list[str]:
    """What is wrong with the ``{{ }}`` templates inside *value*: the server's templates are a path and filters, nothing more."""
    out: list[str] = []
    if isinstance(value, str):
        for expression in _TEMPLATE_PART.findall(value):
            parts = [p.strip() for p in expression.split("|")]
            if not _LOOKUP.match(parts[0]):
                out.append(f"template {{{{ {expression} }}}}: only a path like steps.load.output.id is allowed before the filters (no operators, calls or brackets)")
            for spec in parts[1:]:
                name = spec.partition(":")[0].strip()
                if name not in FILTERS:
                    out.append(f"template {{{{ {expression} }}}}: unknown filter {name!r} (filters: {', '.join(FILTERS)})")
    elif isinstance(value, dict):
        for item in value.values():
            out += template_problems(item)
    elif isinstance(value, list):
        for item in value:
            out += template_problems(item)
    return out


def setting_problems(node: str, key: str, name: str, spec: dict[str, Any], value: Any) -> list[str]:
    """What is wrong with one setting's value, judged from the block's own description of it."""
    where = f"node {node!r} ({key}): {name}"
    if spec.get("widget") == "condition" and isinstance(value, (dict, bool)):
        return [f"{where}: {p}" for p in condition_problems(value, "condition")]
    if templated(value):
        return []
    kind = spec.get("type", "json")
    if kind in ("string", "text", "url") and not isinstance(value, str):
        return [f"{where} is text, not {type(value).__name__}"]
    if kind == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        return [f"{where} is a whole number, not {value!r}"]
    if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return [f"{where} is a number, not {value!r}"]
    if kind == "boolean" and not isinstance(value, bool):
        return [f"{where} is true or false, not {value!r}"]
    if kind == "array" and not isinstance(value, list):
        return [f"{where} is a list"]
    out: list[str] = []
    if spec.get("enum") and value not in spec["enum"]:
        out.append(f"{where} is one of {', '.join(map(str, spec['enum']))}, not {value!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            out.append(f"{where} is at least {spec['minimum']}, not {value}")
        if "maximum" in spec and value > spec["maximum"]:
            out.append(f"{where} is at most {spec['maximum']}, not {value}")
    if kind == "array" and isinstance(value, list) and spec.get("items", {}).get("type") == "string":
        out += [f"{where} holds text, but {item!r} is not" for item in value if not isinstance(item, str) and not templated(item)]
    return out


def graph_problems(graph: dict[str, Any]) -> list[str]:
    out: list[str] = []
    raw_nodes = graph.get("nodes", [])
    nodes = {n["id"]: n for n in raw_nodes if isinstance(n, dict) and "id" in n}
    if len(nodes) != len(raw_nodes):
        out.append("every node needs a unique id")
    if not nodes:
        return [*out, "the flow has no blocks"]
    triggers: list[str] = []
    for node_id, node in nodes.items():
        data = node.get("data") or {}
        key = data.get("block") or node.get("type")
        meta = BLOCKS.get(key)
        if meta is None:
            out.append(f"node {node_id!r}: unknown block {key!r}")
            continue
        config = data.get("config") or {}
        if meta["trigger"]:
            triggers.append(node_id)
        for name, spec in meta["config"].items():
            if spec.get("required") and name not in config:
                out.append(f"node {node_id!r} ({key}): missing required setting {name!r}")
        for name, value in config.items():
            if meta["config"].get(name, {}).get("widget") != "condition":
                out += [f"node {node_id!r} ({key}): {name}: {p}" for p in template_problems(value)]
            if name not in meta["config"]:
                out.append(f"node {node_id!r} ({key}): unknown setting {name!r} (known: {', '.join(meta['config']) or 'none'})")
            else:
                out += setting_problems(node_id, key, name, meta["config"][name], value)
        for referenced in sorted(set(re.findall(r"steps\.([A-Za-z_][A-Za-z0-9_-]*)", repr(config)))):
            if referenced not in nodes:
                out.append(f"node {node_id!r}: refers to steps.{referenced}, but there is no node {referenced!r}")
    if not triggers:
        out.append("the flow has no trigger (add a blocks.trigger.* node to start it)")
    adjacency: dict[str, list[str]] = {}
    for edge in graph.get("edges", []):
        source, target, handle = edge.get("source"), edge.get("target"), edge.get("sourceHandle") or "next"
        if source not in nodes or target not in nodes:
            out.append(f"edge {source!r} → {target!r} points at a node that does not exist")
            continue
        meta = BLOCKS.get((nodes[source].get("data") or {}).get("block") or "")
        if meta is not None and "*" not in meta["handles"] and handle not in meta["handles"] and handle not in UNIVERSAL_HANDLES:
            out.append(f"node {source!r}: {meta and (nodes[source].get('data') or {}).get('block')} has no {handle!r} handle (it has: {', '.join(meta['handles']) or 'none'})")
        adjacency.setdefault(source, []).append(target)
    reached = set(triggers)
    queue = deque(triggers)
    while queue:
        for target in adjacency.get(queue.popleft(), []):
            if target not in reached:
                reached.add(target)
                queue.append(target)
    if triggers:
        out += [f"node {node_id!r} can never run: nothing connects it to a trigger" for node_id in nodes if node_id not in reached]
    return out


def layout(order: list[str], edges: list[tuple[str, str, str]], trigger_ids: list[str]) -> dict[str, dict[str, int]]:
    """Columns by distance from a trigger, so the flow opens in Studio already readable."""
    depth = {t: 0 for t in trigger_ids}
    queue = deque(trigger_ids)
    while queue:
        current = queue.popleft()
        for source, target, _ in edges:
            if source == current and target not in depth:
                depth[target] = depth[current] + 1
                queue.append(target)
    for node_id in order:
        depth.setdefault(node_id, max(depth.values(), default=0) + 1)
    rows: dict[int, int] = {}
    out: dict[str, dict[str, int]] = {}
    for node_id in order:
        column = depth[node_id]
        out[node_id] = {"x": column * 300, "y": rows.get(column, 0) * 150}
        rows[column] = rows.get(column, 0) + 1
    return out
