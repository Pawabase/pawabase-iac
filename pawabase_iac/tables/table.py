from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from ..core.base import Definition, check_name, plain
from ..policies.check import reference_problems
from .check import OPERATIONS, RESERVED_TABLE_NAMES, TABLE_NAME, field_problems, index_problems


@dataclass
class Table(Definition):
    """A database table with a generated REST API. ``operations`` turns on list, get, create, update and delete, each under a policy.

        Table("orders",
              fields=[Number("total", required=True, minimum=0), String("status", enum=["new", "paid", "shipped"], default="new")],
              operations=crud("authenticated", delete=Allow(P.role("admin"))),
              relations=[BelongsTo("customer", "customers", "customer_id")],
              owner_field="customer_id",
              indexes=[Index("status", "created_at")],
              realtime=True)

    Also importable as ``Resource``, the name the Platform API uses.
    """

    kind: ClassVar[str] = "resources"
    derived: ClassVar[tuple[str, ...]] = ("table",)
    name: str
    fields: list[dict[str, Any]] = field(default_factory=list)
    operations: dict[str, dict[str, Any]] = field(default_factory=dict)
    description: str = ""
    table: str | None = None
    primary_key: str = "id"
    id_type: Literal["ulid", "uuid", "integer"] = "ulid"
    relations: list[dict[str, Any]] = field(default_factory=list)
    transformer: Any = None
    cache_ttl: int = 0
    rate_limit: dict[str, int] = field(default_factory=dict)
    events: bool = True
    realtime: bool = False
    capture: bool = False
    timestamps: bool = True
    owner_field: str | None = None
    indexes: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def problems(self) -> list[str]:
        out = check_name(self.name, "table", TABLE_NAME)
        if self.name in RESERVED_TABLE_NAMES:
            out.append(f"{self.name!r} is reserved")
        out += field_problems(self.fields)
        if self.id_type not in ("ulid", "uuid", "integer"):
            out.append("id_type is ulid, uuid or integer")
        for operation, settings in self.operations.items():
            if operation not in OPERATIONS:
                out.append(f"operations.{operation}: one of {', '.join(OPERATIONS)}")
            elif not isinstance(settings, dict):
                out.append(f"operations.{operation}: use Allow(policy) or Deny()")
            else:
                out += reference_problems(plain(settings.get("policy"), resolve=False), f"operations.{operation}.policy")
        for index, relation in enumerate(self.relations):
            if not {"name", "resource", "field"} <= set(relation):
                out.append(f"relations[{index}] needs name, resource and field")
            elif relation.get("type", "belongs_to") not in ("belongs_to", "has_many"):
                out.append(f"relations[{index}].type is belongs_to or has_many")
        if self.rate_limit and not self.rate_limit.get("limit"):
            out.append("rate_limit needs a limit")
        if not 0 <= self.cache_ttl <= 86400:
            out.append("cache_ttl is between 0 and 86400 seconds")
        known = {f.get("name") for f in self.fields if isinstance(f, dict)} | {self.primary_key}
        if self.timestamps:
            known |= {"created_at", "updated_at"}
        if self.owner_field:
            known.add(self.owner_field)
        out += index_problems(self.indexes, known)
        for relation in self.relations:
            if relation.get("type", "belongs_to") == "belongs_to" and relation.get("field") and relation["field"] not in known:
                out.append(f"relation {relation.get('name')!r}: this table has no field {relation['field']!r}")
        if self.owner_field and not any(f.get("name") == self.owner_field for f in self.fields if isinstance(f, dict)):
            out.append(f"owner_field {self.owner_field!r} is not one of the table's fields")
        if self.capture and not self.events:
            out.append("capture announces changes as events, so it needs events=True")
        return out


Resource = Table
