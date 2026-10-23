"""Template expressions for flow blocks.

    from pawabase_iac import ctx

    blocks.resource.create(resource="orders", data={"total": ctx.input.total, "owner": ctx.auth.user_id})
    ctx.steps.load.output.email                  ->  "{{ steps.load.output.email }}"
    ctx.input.name.default("guest")              ->  "{{ input.name | default:\"guest\" }}"
    ctx.steps.list.output.data.length()          ->  "{{ steps.list.output.data | length }}"

A flow template is a *lookup*, not a language: a path (``steps.load.output.id``, ``input.items.0``) and a few filters. There is no
arithmetic and no comparison inside ``{{ }}``; do those with ``blocks.math.calculate`` and ``blocks.control.if_`` (whose condition is
written with ``P``). A value that is exactly one template keeps its type (a list stays a list); inside longer text it becomes text.
"""

from __future__ import annotations

import json
from typing import Any

from .policy import Condition, Path, condition_json

#: The filters the server's template engine knows.
FILTERS = ("default", "upper", "lower", "json", "length", "int", "float", "str", "bool", "first", "last", "keys")


class Expr:
    """A value read from the running flow."""

    def __init__(self, source: str) -> None:
        self._source = source

    def __getattr__(self, name: str) -> Expr:
        if name.startswith("__"):
            raise AttributeError(name)
        return Expr(f"{self._source}.{name}")

    def __getitem__(self, key: str | int) -> Expr:
        return Expr(f"{self._source}.{key}")

    def filter(self, name: str, argument: Any = None) -> Expr:
        """Apply a filter: ``ctx.input.name.filter("default", "guest")``. The filters are listed in :data:`FILTERS`."""
        if name not in FILTERS:
            raise ValueError(f"unknown template filter {name!r}; the server knows: {', '.join(FILTERS)}")
        return Expr(f"{self._source} | {name}" + (f":{json.dumps(argument)}" if argument is not None else ""))

    def default(self, value: Any) -> Expr:
        """Use *value* when this is missing or empty."""
        return self.filter("default", value)

    def upper(self) -> Expr:
        return self.filter("upper")

    def lower(self) -> Expr:
        return self.filter("lower")

    def length(self) -> Expr:
        """How many items a list has, or characters a text has."""
        return self.filter("length")

    def int(self) -> Expr:
        return self.filter("int")

    def float(self) -> Expr:
        return self.filter("float")

    def str(self) -> Expr:
        return self.filter("str")

    def bool(self) -> Expr:
        return self.filter("bool")

    def first(self) -> Expr:
        return self.filter("first")

    def last(self) -> Expr:
        return self.filter("last")

    def keys(self) -> Expr:
        return self.filter("keys")

    def json(self) -> Expr:
        """The value as JSON text."""
        return self.filter("json")

    def _no_operators(self, *_: Any) -> Any:
        raise TypeError(
            "a flow template cannot compare or calculate: write the check with P (blocks.control.if_(P.steps.x.output.n > 3)) "
            "or compute with blocks.math.calculate"
        )

    __eq__ = __ne__ = __gt__ = __ge__ = __lt__ = __le__ = _no_operators  # type: ignore[assignment]
    __add__ = __sub__ = __mul__ = __truediv__ = _no_operators
    __hash__ = object.__hash__

    def __bool__(self) -> bool:
        raise TypeError("a flow expression has no truth value in Python: it is evaluated when the flow runs")

    def template(self) -> str:
        return "{{ " + self._source + " }}"

    def __str__(self) -> str:
        return self.template()

    def __repr__(self) -> str:
        return f"ctx.{self._source}"


class _Ctx:
    """``ctx``: input, auth, env, vars, steps (and item, index and error inside loops and error branches)."""

    input = Expr("input")
    auth = Expr("auth")
    env = Expr("env")
    vars = Expr("vars")
    steps = Expr("steps")
    item = Expr("item")
    index = Expr("index")
    error = Expr("error")
    run = Expr("run")

    @staticmethod
    def expr(source: str) -> Expr:
        """Any template expression, written as the flow engine reads it: ``ctx.expr("input.name | upper")``."""
        return Expr(source)

    @staticmethod
    def text(*parts: Any) -> str:
        """Join literal text and expressions into one template string (the result is always text)."""
        return "".join(p.template() if isinstance(p, Expr) else str(p) for p in parts)


ctx = _Ctx()


def render_value(value: Any) -> Any:
    """Turn expressions anywhere inside *value* into template strings, leaving the rest as it is."""
    if isinstance(value, Expr):
        return value.template()
    if isinstance(value, Condition):
        return condition_json(value)
    if isinstance(value, Path):
        return "$" + value._path
    if isinstance(value, dict):
        return {k: render_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [render_value(v) for v in value]
    return value
