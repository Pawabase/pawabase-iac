import pytest

from pawabase_iac import Flow, InboundHook, P, Schedule, Subscription, Webhook, blocks, env, every
from pawabase_iac.validate import check


def make_flow():
    f = Flow("job")
    f.chain(blocks.trigger.manual(), blocks.control.noop())
    return f


def test_subscriptions_and_schedules_take_flows_or_names(project):
    job = make_flow()
    s = Subscription("on_order", on="orders.created", run=job, condition=P.event.payload.record.total > 5)
    assert s.body() == {"name": "on_order", "description": "", "event": "orders.created", "target_type": "flow",
                        "target": "job", "condition": {"gt": ["$event.payload.record.total", 5]}, "enabled": True}
    feed = Subscription("feed", on="x", publish_to="orders")
    assert (feed.body()["target_type"], feed.body()["target"]) == ("realtime", "orders")
    sched = Schedule("nightly", run=job, cron="0 3 * * *", timezone="Africa/Lagos")
    assert sched.problems() == [] and sched.body()["target"] == "job"
    assert Schedule("hb", event="beat", interval=every(minutes=5)).body()["interval_seconds"] == 300
    assert check(project.items) == []


def test_exactly_one_target(project):
    with pytest.raises(ValueError):
        Subscription("a", on="x")
    with pytest.raises(ValueError):
        Schedule("a", run=make_flow(), event="x", cron="* * * * *")
    with pytest.raises(ValueError):
        InboundHook("hook", verification="none")


def test_schedule_problems(project):
    text = " | ".join(Schedule("s", event="e").problems() + Schedule("t", event="e", cron="* *", interval=5).problems()
                      + Schedule("u", event="e", interval=5, timezone="Mars/Base").problems())
    assert "exactly one of cron= and interval=" in text and "5 fields" in text and "at least 10" in text and "timezone" in text


def test_secrets_come_from_the_environment(project, monkeypatch):
    hook = Webhook("erp", url="https://erp.example.com/h", secret=env("ERP_SECRET"))
    inbound = InboundHook("stripe", event="stripe.event", secret=env("STRIPE_SECRET"))
    assert hook.problems() == [] and inbound.problems() == []
    assert hook.body(resolve=False)["secret"] is None
    with pytest.raises(LookupError, match="ERP_SECRET"):
        hook.body()
    monkeypatch.setenv("ERP_SECRET", "x" * 20)
    assert hook.body()["secret"] == "x" * 20


def test_webhook_and_inbound_problems(project):
    text = " | ".join(Webhook("w", url="ftp://x", max_attempts=11, secret="short").problems()
                      + InboundHook("A", event="e", verification="hmac-sha256").problems())
    for expected in ("http://", "max_attempts", "16 characters", "slug", "needs a secret"):
        assert expected in text


def test_a_subscription_to_a_missing_flow(project):
    Subscription("s", on="e", run="ghost")
    assert "target flow 'ghost' is not defined" in "\n".join(map(str, check(project.items)))
