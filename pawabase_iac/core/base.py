"""What every definition shares: a kind, a key, a request body, a way to say what is wrong with it, and a registry that collects them."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Any, ClassVar, Iterator

from ..expr.flow import Expr
from ..expr.policy import Condition, Path, condition_json

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,62}$")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

#: Kinds in the order they must exist: a definition may refer to the ones before it.
ORDER = (
    "roles", "schemas", "transformers", "policies", "resources", "flows", "buckets", "mail-templates",
    "routes", "subscriptions", "webhooks", "inbound-hooks", "schedules",
)  # fmt: skip


class Env:
    """A value read from the environment when you deploy, so a secret never sits in your code: ``secret=env("ORDERS_HOOK_SECRET")``."""

    def __init__(self, name: str) -> None:
        self.name = name

    def resolve(self) -> str:
        value = os.environ.get(self.name)
        if not value:
            raise LookupError(f"environment variable {self.name} is not set")
        return value

    def __repr__(self) -> str:
        return f"env({self.name!r})"


def env(name: str) -> Env:
    return Env(name)


class Registry:
    """Everything defined while a project is being imported."""

    def __init__(self) -> None:
        self.items: list[Definition] = []

    def add(self, item: Definition) -> None:
        self.items.append(item)


_active: list[Registry] = [Registry()]


@contextmanager
def collecting() -> Iterator[Registry]:
    """Collect the definitions made inside the block into a fresh registry (what the CLI does while it imports your project)."""
    registry = Registry()
    _active.append(registry)
    try:
        yield registry
    finally:
        _active.pop()


class Definition:
    """Base of every definition."""

    kind: ClassVar[str] = ""
    #: The attribute that names it (``name``, or ``slug`` for inbound hooks).
    key_field: ClassVar[str] = "name"
    #: Fields the server stores but never returns: they are sent, never compared.
    write_only: ClassVar[tuple[str, ...]] = ()
    #: Fields the server fills in when you leave them unset (``table`` defaults to the name): not comparing an unset one avoids a change on every plan.
    derived: ClassVar[tuple[str, ...]] = ()

    def __post_init__(self) -> None:
        self._register()

    def _register(self) -> None:
        _active[-1].add(self)

    @property
    def key(self) -> str:
        return str(getattr(self, self.key_field))

    @property
    def label(self) -> str:
        return f"{self.kind}/{self.key}"

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        """The request body. ``resolve=False`` leaves ``env(...)`` values unread (for printing and diffing)."""
        from dataclasses import fields

        return {f.name: plain(getattr(self, f.name), resolve=resolve) for f in fields(self)}  # type: ignore[arg-type]

    def problems(self) -> list[str]:
        raise NotImplementedError


def plain(value: Any, *, resolve: bool = True) -> Any:
    """The stored form of a value: conditions as JSON, definitions by name, expressions as templates, ``env()`` read."""
    if isinstance(value, Condition):
        return condition_json(value)
    if isinstance(value, Path):
        return "$" + value._path
    if isinstance(value, Expr):
        return value.template()
    if isinstance(value, Env):
        return value.resolve() if resolve else None
    if isinstance(value, Definition):
        return value.key
    if isinstance(value, dict):
        return {k: plain(v, resolve=resolve) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v, resolve=resolve) for v in value]
    return value


def ref_name(value: Any) -> str:
    """The name a reference stands for: a definition, or the string itself."""
    return value.key if isinstance(value, Definition) else str(value or "")


def check_name(value: Any, label: str, pattern: re.Pattern[str] = NAME) -> list[str]:
    if not isinstance(value, str) or not pattern.match(value):
        return [f"{label} {value!r} is not a valid name (letters, digits, _ and -, starting with a letter)"]
    return []
