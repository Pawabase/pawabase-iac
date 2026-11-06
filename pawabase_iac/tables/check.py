from __future__ import annotations

import re
from typing import Any

from ..core.base import IDENT

FIELD_TYPES = (
    "string", "text", "integer", "number", "boolean", "datetime", "date", "uuid", "ulid",
    "email", "url", "json", "array", "object", "ref", "vector",
)  # fmt: skip
#: pgvector stores up to 16,000 dimensions in a column.
MAX_VECTOR_DIMENSIONS = 16000
OPERATIONS = ("list", "get", "create", "update", "delete")
RESERVED_TABLE_NAMES = frozenset({"auth", "storage", "rest", "platform", "health", "realtime"})
TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def field_problems(specs: list[dict[str, Any]], path: str = "fields") -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for index, spec in enumerate(specs):
        where = f"{path}[{index}]"
        if not isinstance(spec, dict):
            out.append(f"{where}: use String(...), Integer(...) and the other field builders")
            continue
        name = spec.get("name")
        if not isinstance(name, str) or not IDENT.match(name):
            out.append(f"{where}: name must be letters, digits and underscores, starting with a letter or _")
            continue
        if name in seen:
            out.append(f"{where}: duplicate field {name!r}")
        seen.add(name)
        kind = spec.get("type", "string")
        if kind not in FIELD_TYPES:
            out.append(f"{where} ({name}): unknown type {kind!r} (one of {', '.join(FIELD_TYPES)})")
        if kind == "ref" and not spec.get("schema"):
            out.append(f"{where} ({name}): a ref field names a schema")
        if kind == "vector":
            dimensions = spec.get("dimensions")
            if not isinstance(dimensions, int) or isinstance(dimensions, bool) or not 1 <= dimensions <= MAX_VECTOR_DIMENSIONS:
                out.append(f"{where} ({name}): a vector field needs dimensions, a whole number from 1 to {MAX_VECTOR_DIMENSIONS}")
            embed = spec.get("embed")
            if embed is not None:
                sources = embed.get("from") if isinstance(embed, dict) else None
                if not isinstance(embed, dict) or not embed.get("model"):
                    out.append(f"{where} ({name}): embed names a model: Embed(\"embed\", \"title\")")
                elif not isinstance(sources, list) or not sources:
                    out.append(f"{where} ({name}): embed lists the fields to read, such as Embed(\"embed\", \"title\")")
                else:
                    text_fields = {s.get("name") for s in specs if isinstance(s, dict) and s.get("type", "string") in ("string", "text")}
                    for source in sources:
                        if source not in text_fields:
                            out.append(f"{where} ({name}): embed reads {source!r}, which is not a string or text field of this table")
        if kind == "array" and "items" in spec:
            out += field_problems([{**spec["items"], "name": "item"}], f"{where}.items")
        if kind == "object":
            out += field_problems(spec.get("fields", []), f"{where}.fields")
        if "pattern" in spec:
            try:
                re.compile(spec["pattern"])
            except re.error as exc:
                out.append(f"{where} ({name}): invalid pattern: {exc}")
        for low, high in (("min_length", "max_length"), ("minimum", "maximum")):
            if low in spec and high in spec and spec[low] > spec[high]:
                out.append(f"{where} ({name}): {low} is above {high}")
        if "enum" in spec and not spec["enum"]:
            out.append(f"{where} ({name}): enum cannot be empty")
        if spec.get("required") and spec.get("nullable"):
            out.append(f"{where} ({name}): a field cannot be both required and nullable")
    return out


INDEX_NAME = re.compile(r"^[a-z][a-z0-9_]{0,29}$")
INDEX_OPERATORS = ("=", "!=", "<", "<=", ">", ">=")
NULL_OPERATORS = ("is_null", "not_null")


def index_problems(indexes: list[dict[str, Any]], known: set[str]) -> list[str]:
    """What the server's index validator would say about declared indexes."""
    out: list[str] = []
    if len(indexes) > 16:
        out.append("a table may declare at most 16 indexes")
    names: set[str] = set()
    for position, spec in enumerate(indexes):
        where = f"indexes[{position}]"
        if not isinstance(spec, dict):
            out.append(f"{where} must come from Index(...)")
            continue
        name = spec.get("name")
        if not isinstance(name, str) or not INDEX_NAME.match(name):
            out.append(f"{where}.name must be lowercase letters, digits and underscores, starting with a letter, at most 30 characters")
            continue
        if name in names:
            out.append(f"index {name} appears twice")
        names.add(name)
        columns = [c.get("name") if isinstance(c, dict) else c for c in spec.get("columns", [])]
        if not columns:
            out.append(f"index {name} needs at least one column")
        if len(columns) > 8:
            out.append(f"index {name} may cover at most 8 columns")
        for column in columns:
            if column not in known:
                out.append(f"index {name}: {column!r} is not a column of this table")
        if len(set(columns)) != len(columns):
            out.append(f"index {name}: a column is listed twice")
        method = spec.get("method", "btree")
        if method not in ("btree", "hash", "brin", "hnsw", "ivfflat"):
            out.append(f"index {name}: method is btree, hash, brin, hnsw or ivfflat")
        if method in ("hnsw", "ivfflat"):
            if len(columns) != 1:
                out.append(f"index {name}: a {method} index covers one vector column")
            if spec.get("metric", "cosine") not in ("cosine", "l2", "ip"):
                out.append(f"index {name}: metric is cosine, l2 or ip")
        if method != "btree" and spec.get("unique"):
            out.append(f"index {name}: only a btree index can be unique")
        if method == "hash" and len(columns) > 1:
            out.append(f"index {name}: a hash index covers one column")
        conditions = spec.get("where") or []
        if len(conditions) > 4:
            out.append(f"index {name} may have at most 4 conditions")
        for condition in conditions:
            op = condition.get("op")
            if condition.get("column") not in known:
                out.append(f"index {name}: condition on unknown column {condition.get('column')!r}")
            elif op not in INDEX_OPERATORS + NULL_OPERATORS:
                out.append(f"index {name}: condition op is one of {', '.join(INDEX_OPERATORS + NULL_OPERATORS)}")
            elif op in INDEX_OPERATORS and (condition.get("value") is None or isinstance(condition.get("value"), (dict, list))):
                out.append(f"index {name}: a {op} condition needs a plain value")
    return out
