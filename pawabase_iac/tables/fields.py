"""Typed fields for tables and schemas.

    from pawabase_iac import Table, String, Integer, Email, Array, Object, Ref, BelongsTo

    Table("customers", fields=[
        String("name", required=True, max_length=120),
        Email("email", required=True, unique=True),
        Integer("loyalty_points", minimum=0, default=0),
        Array("tags", of=String("tag")),
        Object("address", fields=[String("city"), String("postcode", pattern=r"^[A-Z0-9 ]+$")]),
    ])
"""

from __future__ import annotations

from typing import Any


def _field(kind: str, name: str, **options: Any) -> dict[str, Any]:
    """A field spec holding only what was set: absent, ``None`` and the unset flags are left out."""
    return {"name": name, "type": kind, **{k: v for k, v in options.items() if v is not None}}


def _make(kind: str):
    def build(
        name: str,
        *,
        required: bool = False,
        nullable: bool = False,
        default: Any = None,
        unique: bool = False,
        indexed: bool = False,
        description: str | None = None,
        read_only: bool = False,
        write_only: bool = False,
        enum: list[Any] | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        return _field(
            kind, name, required=required or None, nullable=nullable or None, default=default, unique=unique or None,
            indexed=indexed or None, description=description, read_only=read_only or None, write_only=write_only or None,
            enum=enum, **options,
        )  # fmt: skip

    build.__name__ = kind
    return build


_string = _make("string")
_text = _make("text")


def String(name: str, *, min_length: int | None = None, max_length: int | None = None, pattern: str | None = None, **common: Any):
    """Short text. ``enum=[...]`` limits it to a set of values."""
    return _string(name, min_length=min_length, max_length=max_length, pattern=pattern, **common)


def Text(name: str, *, min_length: int | None = None, max_length: int | None = None, **common: Any):
    """Long text."""
    return _text(name, min_length=min_length, max_length=max_length, **common)


def Integer(name: str, *, minimum: int | None = None, maximum: int | None = None, **common: Any):
    return _make("integer")(name, minimum=minimum, maximum=maximum, **common)


def Number(name: str, *, minimum: float | None = None, maximum: float | None = None, **common: Any):
    return _make("number")(name, minimum=minimum, maximum=maximum, **common)


Boolean = _make("boolean")
DateTime = _make("datetime")
Date = _make("date")
UUID = _make("uuid")
ULID = _make("ulid")
Email = _make("email")
URL = _make("url")
JSON = _make("json")


def Array(name: str, *, of: dict[str, Any] | None = None, **common: Any):
    """A list. ``of=String("item")`` types the items."""
    extra = {"items": {k: v for k, v in of.items() if k != "name"}} if of else {}
    return _make("array")(name, **extra, **common)


def Object(name: str, *, fields: list[dict[str, Any]] | None = None, **common: Any):
    """A nested object with its own fields."""
    return _make("object")(name, fields=fields or [], **common)


def Ref(name: str, *, schema: Any, **common: Any):
    """A value shaped by a :class:`~pawabase_iac.Schema` (pass the Schema or its name)."""
    return _make("ref")(name, schema=schema, **common)


# ── table parts ──────────────────────────────────────────────────────────


def Allow(policy: Any = None, **options: Any) -> dict[str, Any]:
    """Turn an operation on: ``Allow("authenticated")``, ``Allow(P.owner())``. No policy leaves the environment default."""
    return {"enabled": True, **({"policy": policy} if policy is not None else {}), **options}


def Deny() -> dict[str, Any]:
    return {"enabled": False}


def crud(policy: Any = None, **per_operation: Any) -> dict[str, dict[str, Any]]:
    """All five operations on under one policy, with overrides: ``crud("authenticated", delete=Allow("role:admin"))``."""
    ops = {name: Allow(policy) for name in ("list", "get", "create", "update", "delete")}
    for name, value in per_operation.items():
        ops[name] = Allow(value) if not isinstance(value, dict) else value
    return ops


def read_only(policy: Any = None) -> dict[str, dict[str, Any]]:
    return {"list": Allow(policy), "get": Allow(policy)}


def BelongsTo(name: str, resource: Any, field: str, **options: Any) -> dict[str, Any]:
    """This table's ``field`` holds the id of a row in ``resource``."""
    return {"name": name, "resource": resource, "field": field, "type": "belongs_to", **options}


def HasMany(name: str, resource: Any, field: str, **options: Any) -> dict[str, Any]:
    """Rows in ``resource`` hold this table's id in their ``field``."""
    return {"name": name, "resource": resource, "field": field, "type": "has_many", **options}


def Desc(column: str) -> dict[str, Any]:
    """A descending column in an index: ``Index("tenant_id", Desc("created_at"))``."""
    return {"name": column, "desc": True}


def Where(column: str, op: str, value: Any = None) -> dict[str, Any]:
    """One condition of a partial index. ``op`` is = != < <= > >= (with a value) or is_null / not_null: ``Where("deleted_at", "is_null")``."""
    return {"column": column, "op": op, **({"value": value} if op not in ("is_null", "not_null") else {})}


def Index(
    *columns: str | dict[str, Any],
    name: str | None = None,
    unique: bool = False,
    where: list[dict[str, Any]] | None = None,
    method: str = "btree",
    concurrent: bool = False,
    note: str = "",
) -> dict[str, Any]:
    """A database index on one or more columns, optionally unique, descending, partial (``where=[Where(...)]``) or hash/brin.

        Index("project_id", "done")
        Index("tenant_id", Desc("created_at"), where=[Where("deleted_at", "is_null")])
        Index("email", unique=True, name="uniq_email")
    """
    cols = [{"name": c} if isinstance(c, str) else dict(c) for c in columns]
    label = "_".join(c["name"] for c in cols)[:26]
    spec: dict[str, Any] = {"name": name or f"idx_{label}", "columns": cols, "unique": unique, "where": list(where or [])}
    if method != "btree":
        spec["method"] = method  # the server leaves the default out of what it returns
    if concurrent:
        spec["concurrent"] = True
    if note:
        spec["note"] = note
    return spec


def RateLimit(limit: int, window: int = 60) -> dict[str, int]:
    """At most ``limit`` calls per ``window`` seconds."""
    return {"limit": limit, "window": window}
