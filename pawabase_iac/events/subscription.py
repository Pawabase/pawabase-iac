from __future__ import annotations

from typing import Any

from ..core.base import Definition, check_name, plain, ref_name
from ..policies.check import condition_problems


class Subscription(Definition):
    """Runs a flow, or publishes to a realtime channel, when an event happens.

        Subscription("welcome_new_users", on="user.created", run=welcome_flow)
        Subscription("big_orders", on="orders.created", run=review_flow, condition=P.event.payload.record.total > 1000)
        Subscription("order_feed", on="orders.created", publish_to="orders")

    A table raises ``<table>.created`` / ``.updated`` / ``.deleted`` with the row at ``event.payload.record``; accounts raise ``user.created``
    and the like; flows raise their own with ``blocks.event.emit``. A flow started this way receives ``{"event": {...}}`` as its input
    (``ctx.input.event.payload.record.total``), and the ``condition`` reads the same event (``P.event.payload...``).
    """

    kind = "subscriptions"
    key_field = "name"

    def __init__(
        self,
        name: str,
        *,
        on: str,
        run: Any = None,
        publish_to: str | None = None,
        condition: Any = None,
        description: str = "",
        enabled: bool = True,
    ) -> None:
        if (run is None) == (publish_to is None):
            raise ValueError("a subscription either runs a flow (run=) or publishes to a channel (publish_to=), not both")
        self.name, self.event, self.description, self.enabled, self.condition = name, on, description, enabled, condition
        self.target_type = "flow" if run is not None else "realtime"
        self.target = ref_name(run) if run is not None else publish_to
        self._register()

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        return {
            "name": self.name, "description": self.description, "event": self.event, "target_type": self.target_type,
            "target": self.target, "condition": plain(self.condition, resolve=resolve), "enabled": self.enabled,
        }  # fmt: skip

    def problems(self) -> list[str]:
        out = check_name(self.name, "subscription")
        if not self.event or len(self.event) > 128:
            out.append("on= names the event (at most 128 characters)")
        condition = plain(self.condition, resolve=False)
        if condition is not None:
            out += condition_problems(condition, "condition")
        return out
