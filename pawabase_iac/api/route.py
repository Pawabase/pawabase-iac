from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from ..core.base import Definition, plain, ref_name
from ..policies.check import reference_problems


@dataclass
class Route(Definition):
    """A custom HTTP endpoint that runs a flow (pass the Flow itself or its name). Identified by its method and path.

        Route("/orders/{id}/refund", handler=refund_flow, method="POST", policy=P.role("admin"),
              input_schema=refund_input, response_schema=refund_result, rate_limit=RateLimit(10, 60))
    """

    kind: ClassVar[str] = "routes"
    path: str
    handler: Any
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    name: str = ""
    description: str = ""
    policy: Any = None
    input_fields: list[dict[str, Any]] | None = None
    input_schema: Any = None
    response_schema: Any = None
    transformer: Any = None
    handler_type: Literal["flow", "function"] = "flow"
    rate_limit: dict[str, int] = field(default_factory=dict)
    cache_ttl: int = 0
    tags: list[str] = field(default_factory=list)
    enabled: bool = True

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        body = super().body(resolve=resolve)
        body["handler"] = ref_name(self.handler)
        return body

    def problems(self) -> list[str]:
        out = []
        if not self.path.startswith("/"):
            out.append("path starts with /")
        if self.method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            out.append("method is GET, POST, PUT, PATCH or DELETE")
        if not ref_name(self.handler):
            out.append("handler names the flow to run")
        if self.handler_type == "function":
            out.append("handler_type 'function' is not available: functions were removed, use a flow")
        if not 0 <= self.cache_ttl <= 86400:
            out.append("cache_ttl is between 0 and 86400 seconds")
        if self.rate_limit and not self.rate_limit.get("limit"):
            out.append("rate_limit needs a limit")
        out += reference_problems(plain(self.policy, resolve=False), "policy")
        return out
