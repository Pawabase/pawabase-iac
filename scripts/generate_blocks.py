"""Regenerate pawabase_iac/flows/blocks/*.py and flows/catalogue.py from the flow blocks a Pawabase server knows.

    cd ../../pawabase && uv run --no-sync python ../_split/python-iac/scripts/generate_blocks.py

One module per block family (``blocks.resource``, ``blocks.control``, ``blocks.trigger``…), one function per block, every option
typed and documented with its default, limits and allowed values. Run it again when the server gains blocks.
"""

from __future__ import annotations

import keyword
import pprint
import sys
from pathlib import Path

from pawabase_server.flows.registry import default_registry

OUT = Path(__file__).resolve().parent.parent / "pawabase_iac" / "flows"
PY = {"string": "str", "text": "str", "url": "str", "integer": "int", "number": "float", "boolean": "bool", "json": "Any", "array": "list[Any]"}
FAMILY_DOC = {
    "auth": "Who is calling: require a role, load a user.",
    "cache": "Read, write and invalidate the environment's cache.",
    "control": "Branch, loop, wait, retry, stop: the flow's control structures.",
    "crypto": "Hashing and signing.",
    "db": "Raw SQL and transactions.",
    "error": "Fail the run with a status and a message.",
    "event": "Raise an event others subscribe to.",
    "flow": "Call another flow and wait for it.",
    "http": "Call an external HTTP API.",
    "json": "Parse and write JSON text.",
    "log": "Write to the environment's log.",
    "mail": "Send an email.",
    "math": "Arithmetic.",
    "metric": "Count things.",
    "policy": "Evaluate a policy inside a flow.",
    "queue": "Run a flow later, in the background.",
    "realtime": "Publish to a realtime channel.",
    "resource": "Create, read, change, list and delete rows of a table.",
    "response": "End the run with a response.",
    "secret": "Read an environment secret.",
    "storage": "Put, read, delete and sign objects in a bucket.",
    "time": "The current time.",
    "transform": "Reshape, filter, group, sort and summarise data.",
    "trigger": "What starts a flow: a request, an event, a schedule, a row change…",
    "util": "Small helpers.",
    "validate": "Check data against a schema.",
    "webhook": "Send an outbound webhook.",
}


def ident(name: str) -> str:
    return name + "_" if keyword.iskeyword(name) else name


def func(key: str) -> str:
    return ident(key.split(".", 1)[1])


def annotation(spec: dict) -> str:
    if spec.get("enum"):
        return "Literal[" + ", ".join(repr(v) for v in spec["enum"]) + "]"
    return PY.get(spec.get("type", "json"), "Any")


def describe(spec: dict) -> str:
    bits = []
    if spec.get("description"):
        bits.append(spec["description"].rstrip("."))
    if spec.get("enum"):
        bits.append("one of " + ", ".join(repr(v) for v in spec["enum"]))
    if "minimum" in spec or "maximum" in spec:
        low, high = spec.get("minimum"), spec.get("maximum")
        bits.append(f"{low if low is not None else '…'} to {high if high is not None else '…'}")
    if "default" in spec:
        bits.append(f"default {spec['default']!r}")
    if spec.get("widget"):
        bits.append(f"{spec['widget']} in Studio")
    return "; ".join(bits)


def function(block: dict) -> str:
    required = [c for c in block["config"] if c.get("required")]
    optional = [c for c in block["config"] if not c.get("required")]
    args = [f"{ident(c['name'])}: {annotation(c)} | Expr" if annotation(c) != "Any" else f"{ident(c['name'])}: Any" for c in required]
    star = ["*"] if optional and required else []
    if optional and not required:
        star = ["*"]
    args += star
    args += [f"{ident(c['name'])}: {annotation(c)} | Expr | None = None" if annotation(c) != "Any" else f"{ident(c['name'])}: Any = None" for c in optional]
    lines = [f"def {func(block['key'])}({', '.join(args)}) -> Block:"]
    doc = [block["description"] or block["title"]]
    if block["trigger"]:
        doc += ["", "A trigger: a flow starts here."]
    if block["handles"]:
        doc += ["", "Handles: " + ", ".join(block["handles"]) + ". Connect with ``node.on(\"handle\") >> other`` or ``node.<handle> >> other``."]
    else:
        doc += ["", "Ends the run: nothing follows it."]
    if block["config"]:
        doc += ["", "Args:"]
        for c in block["config"]:
            detail = describe(c)
            doc.append(f"    {ident(c['name'])}: {c.get('type', 'json')}{', required' if c.get('required') else ''}" + (f". {detail}." if detail else "."))
    lines.append('    """' + doc[0])
    lines += [(("    " + d) if d else "") for d in doc[1:]]
    lines.append('    """')
    pairs = ", ".join(f"{c['name']!r}: {ident(c['name'])}" for c in block["config"])
    lines.append(f"    return Block({block['key']!r}, {{{pairs}}})")
    return "\n".join(lines)


def main() -> int:
    catalogue = default_registry().catalogue()
    families: dict[str, list[dict]] = {}
    for block in catalogue:
        families.setdefault(block["key"].split(".", 1)[0], []).append(block)
    blocks_dir = OUT / "blocks"
    blocks_dir.mkdir(parents=True, exist_ok=True)
    for old in blocks_dir.glob("*.py"):
        old.unlink()
    for family, blocks in sorted(families.items()):
        body = [
            f'"""{FAMILY_DOC.get(family, family)} GENERATED by scripts/generate_blocks.py: do not edit by hand."""',
            "",
            "from __future__ import annotations",
            "",
            "from typing import Any, Literal",
            "",
            "from ...expr.flow import Expr",
            "from ..block import Block",
            "",
            "",
        ]
        for block in blocks:
            body += [function(block), "", ""]
        body.append("__all__ = " + repr(sorted(func(b["key"]) for b in blocks)))
        (blocks_dir / f"{family}.py").write_text("\n".join(body).rstrip() + "\n")
    names = sorted(families)
    (blocks_dir / "__init__.py").write_text(
        '"""Every flow block, by family: ``blocks.resource.create(...)``, ``blocks.control.if_(...)``, ``blocks.trigger.http(...)``.\n\n'
        'GENERATED by scripts/generate_blocks.py: do not edit by hand.\n"""\n\n'
        + "".join(f"from . import {n}\n" for n in names)
        + "\n__all__ = "
        + repr(names)
        + "\n"
    )
    meta = {
        b["key"]: {
            "title": b["title"],
            "category": b["category"],
            "description": b["description"],
            "trigger": b["trigger"],
            "handles": b["handles"],
            "config": {c["name"]: {k: v for k, v in c.items() if k != "name"} for c in b["config"]},
        }
        for b in catalogue
    }
    (OUT / "catalogue.py").write_text('"""Everything the server says about each flow block. GENERATED by scripts/generate_blocks.py."""\n\nBLOCKS = ' + pprint.pformat(meta, width=118, sort_dicts=False) + "\n")
    print(f"{len(catalogue)} blocks in {len(families)} families", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
