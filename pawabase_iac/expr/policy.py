"""Access policies as Python expressions.

    from pawabase_iac import P, Policy, all_of, any_of

    Policy("owner_or_admin", any_of(P.role("admin"), P.record.owner_id == P.auth.user_id))
    Policy("paid_members", P.authenticated() & (P.auth.plan != "free") & ~P.auth.suspended.truthy())

``P.auth`` / ``P.record`` / ``P.input`` / ``P.request`` / ``P.env`` / ``P.credential`` are paths into what a policy can see.
Comparing a path builds a condition; ``&``, ``|`` and ``~`` combine conditions. ``condition.json()`` is the stored form.
"""

from __future__ import annotations

from typing import Any

BINARY = ("eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "starts_with", "ends_with", "matches")


def operand(value: Any) -> Any:
    """A path becomes ``"$path"``; a string that starts with ``$`` is escaped to stay a literal; anything else is itself."""
    if isinstance(value, Path):
        return "$" + value._path
    if isinstance(value, str) and value.startswith("$"):
        return "$" + value
    return value


class Condition:
    """A policy condition. Build them from paths and the helpers below, combine with ``&``, ``|`` and ``~``."""

    def __init__(self, data: Any) -> None:
        self.data = data

    def json(self) -> Any:
        return self.data

    def __and__(self, other: Condition | bool) -> Condition:
        return all_of(self, other)

    def __or__(self, other: Condition | bool) -> Condition:
        return any_of(self, other)

    def __invert__(self) -> Condition:
        return Condition({"not": self.data})

    def __bool__(self) -> bool:  # `a and b` / `if cond:` would silently drop half a policy
        raise TypeError("a policy condition has no truth value: combine with & | ~ instead of and / or / not")

    def __repr__(self) -> str:
        return f"Condition({self.data!r})"


def _data(value: Condition | bool | dict) -> Any:
    return value.data if isinstance(value, Condition) else value


def _flatten(op: str, parts: tuple[Any, ...]) -> list[Any]:
    out: list[Any] = []
    for part in parts:
        data = _data(part)
        if isinstance(data, dict) and list(data) == [op]:
            out += data[op]
        else:
            out.append(data)
    return out


def all_of(*conditions: Condition | bool) -> Condition:
    return Condition({"all": _flatten("all", conditions)})


def any_of(*conditions: Condition | bool) -> Condition:
    return Condition({"any": _flatten("any", conditions)})


def not_(condition: Condition | bool) -> Condition:
    return Condition({"not": _data(condition)})


ALLOW = Condition(True)
DENY = Condition(False)


class Path:
    """A place in what a policy can see: ``P.auth.user_id``, ``P.record.owner_id``, ``P.input.amount``."""

    def __init__(self, path: str) -> None:
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name: str) -> Path:
        if name.startswith("__"):
            raise AttributeError(name)
        return Path(f"{self._path}.{name}")

    def __getitem__(self, key: str | int) -> Path:
        return Path(f"{self._path}.{key}")

    def _cmp(self, op: str, other: Any) -> Condition:
        return Condition({op: [operand(self), operand(other)]})

    def __eq__(self, other: Any) -> Condition:  # type: ignore[override]
        return self._cmp("eq", other)

    def __ne__(self, other: Any) -> Condition:  # type: ignore[override]
        return self._cmp("ne", other)

    def __gt__(self, other: Any) -> Condition:
        return self._cmp("gt", other)

    def __ge__(self, other: Any) -> Condition:
        return self._cmp("gte", other)

    def __lt__(self, other: Any) -> Condition:
        return self._cmp("lt", other)

    def __le__(self, other: Any) -> Condition:
        return self._cmp("lte", other)

    __hash__ = object.__hash__

    def in_(self, values: Any) -> Condition:
        return self._cmp("in", values)

    def not_in(self, values: Any) -> Condition:
        return self._cmp("not_in", values)

    def contains(self, item: Any) -> Condition:
        return self._cmp("contains", item)

    def startswith(self, prefix: Any) -> Condition:
        return self._cmp("starts_with", prefix)

    def endswith(self, suffix: Any) -> Condition:
        return self._cmp("ends_with", suffix)

    def matches(self, pattern: str) -> Condition:
        return self._cmp("matches", pattern)

    def exists(self) -> Condition:
        return Condition({"exists": operand(self)})

    def truthy(self) -> Condition:
        return Condition({"truthy": operand(self)})

    def empty(self) -> Condition:
        return Condition({"empty": operand(self)})

    def __repr__(self) -> str:
        return f"P.{self._path}"


class _Root:
    """``P``: the paths a policy reads, and the built-in checks."""

    auth = Path("auth")
    record = Path("record")
    input = Path("input")
    request = Path("request")
    env = Path("env")
    credential = Path("credential")
    now = Path("now")

    def __getattr__(self, name: str) -> Path:
        # In a flow's `control.if` / `control.while`, conditions read the run: P.steps.load.output.total, P.vars.retries, P.item.id.
        if name.startswith("_"):
            raise AttributeError(name)
        return Path(name)

    @staticmethod
    def authenticated() -> Condition:
        return Condition({"authenticated": True})

    @staticmethod
    def anonymous() -> Condition:
        return Condition({"authenticated": False})

    @staticmethod
    def role(name: str) -> Condition:
        return Condition({"role": name})

    @staticmethod
    def permission(name: str) -> Condition:
        return Condition({"permission": name})

    @staticmethod
    def owner(column: str = "owner_id") -> Condition:
        """The signed-in user owns the record: ``record.<column> == auth.user_id``."""
        return Condition({"owner": column})

    @staticmethod
    def service() -> Condition:
        return Condition({"service": True})

    @staticmethod
    def kind(name: str) -> Condition:
        return Condition({"kind": name})

    @staticmethod
    def scope(name: str) -> Condition:
        return Condition({"scope": name})

    @staticmethod
    def aal(level: str) -> Condition:
        """Authenticator assurance: ``P.aal("aal2")`` requires a second factor."""
        return Condition({"aal": level})


P = _Root()


def condition_json(value: Any) -> Any:
    """A condition, a bool, a plain dict or a policy name, in the form that is stored."""
    return value.json() if isinstance(value, Condition) else value


def reference(value: Any) -> Any:
    """A policy reference as stored: a name (``"owner"``, ``"role:admin"``), an inline condition, or ``None``."""
    return condition_json(value)
