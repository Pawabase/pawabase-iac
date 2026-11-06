from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from ..core.base import Definition, check_name, plain
from ..policies.check import reference_problems
from . import tools as _tools

LIMITS = ("max_steps", "max_seconds", "max_tokens", "max_cost", "guard_untrusted")


@dataclass
class Agent(Definition):
    """AI that uses your tables, flows, documents and apps to get things done, within limits you set.

        support = Agent(
            "support", model="chat", policy="authenticated",
            instructions="You help customers with their orders. Be brief.",
            tools=[tools.table(orders, ["list", "get"]), tools.flow(refund, description="Refund an order")],
            knowledge=[help_articles],
            limits={"max_steps": 8, "max_cost": 0.5},
        )

    ``model`` is a chat model of the environment. With ``run_as="caller"`` (the default) its tools answer to the rules of whoever asked,
    so it can never show someone a row they couldn't read themselves. Changes wait for a person unless a tool says ``approval="auto"``.
    """

    kind: ClassVar[str] = "agents"
    name: str
    model: str = ""
    instructions: str = ""
    description: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    knowledge: list[Any] = field(default_factory=list)
    #: Who may run it.
    policy: Any = "service"
    run_as: Literal["caller", "service"] = "caller"
    #: Who may approve its calls, besides whoever started the run.
    approval_policy: Any = None
    #: ``max_steps``, ``max_seconds``, ``max_tokens``, ``max_cost`` and ``guard_untrusted``.
    limits: dict[str, Any] = field(default_factory=dict)
    #: Model settings such as ``temperature``.
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def problems(self) -> list[str]:
        out = check_name(self.name, "agent")
        if not self.model:
            out.append("model names a chat model of the environment")
        if len(self.instructions) > 50_000:
            out.append("instructions are at most 50,000 characters")
        if len(self.tools) > 50:
            out.append("an agent can have at most 50 tools")
        if self.run_as not in ("caller", "service"):
            out.append("run_as is caller or service")
        for index, spec in enumerate(self.tools):
            out += _tools.problems(spec, f"tools[{index}]")
        for key, value in self.limits.items():
            if key not in LIMITS:
                out.append(f"limits: unknown limit {key!r} (one of {', '.join(LIMITS)})")
            elif key in ("max_steps", "max_seconds", "max_tokens") and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
                out.append(f"limits.{key} must be a whole number above zero")
            elif key == "max_cost" and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
                out.append("limits.max_cost must be above zero")
        for key in ("policy", "approval_policy"):
            out += reference_problems(plain(getattr(self, key), resolve=False), key)
        return out
