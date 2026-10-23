from __future__ import annotations

from typing import Any, Literal

from ..core.base import Definition, check_name, plain, ref_name


def every(*, seconds: int = 0, minutes: int = 0, hours: int = 0, days: int = 0) -> int:
    """An interval in seconds: ``Schedule("sweep", run=f, interval=every(minutes=15))``."""
    return seconds + 60 * minutes + 3600 * hours + 86400 * days


class Schedule(Definition):
    """Runs a flow, or raises an event, on a cron expression or an interval.

        Schedule("nightly_report", run=report_flow, cron="0 3 * * *", timezone="Africa/Lagos", overlap="skip")
        Schedule("heartbeat", event="app.heartbeat", interval=every(minutes=5), payload={"source": "iac"})
    """

    kind = "schedules"
    key_field = "name"

    def __init__(
        self,
        name: str,
        *,
        run: Any = None,
        event: str | None = None,
        cron: str | None = None,
        interval: int | None = None,
        payload: Any = None,
        timezone: str | None = None,
        overlap: Literal["allow", "skip"] = "allow",
        catch_up: bool = False,
        enabled: bool = True,
        description: str = "",
    ) -> None:
        if (run is None) == (event is None):
            raise ValueError("a schedule either runs a flow (run=) or raises an event (event=), not both")
        self.name, self.cron, self.interval_seconds, self.payload = name, cron, interval, payload
        self.timezone, self.overlap, self.catch_up, self.enabled, self.description = timezone, overlap, catch_up, enabled, description
        self.target_type = "flow" if run is not None else "event"
        self.target = ref_name(run) if run is not None else event
        self._register()

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        return {
            "name": self.name, "description": self.description, "cron": self.cron, "interval_seconds": self.interval_seconds,
            "target_type": self.target_type, "target": self.target, "payload": plain(self.payload, resolve=resolve),
            "enabled": self.enabled, "timezone": self.timezone, "overlap": self.overlap, "catch_up": self.catch_up,
        }  # fmt: skip

    def problems(self) -> list[str]:
        out = check_name(self.name, "schedule")
        if (self.cron is None) == (self.interval_seconds is None):
            out.append("set exactly one of cron= and interval=")
        if self.cron is not None and len(self.cron.split()) not in (5, 6):
            out.append("cron has 5 fields (minute hour day month weekday)")
        if self.interval_seconds is not None and self.interval_seconds < 10:
            out.append("interval is at least 10 seconds")
        if self.overlap not in ("allow", "skip"):
            out.append("overlap is allow or skip")
        if self.timezone is not None:
            try:
                from zoneinfo import ZoneInfo

                ZoneInfo(self.timezone)
            except Exception:
                out.append(f"unknown timezone {self.timezone!r}")
        return out
