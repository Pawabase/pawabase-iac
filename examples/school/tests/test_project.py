"""The school project, checked offline: it loads, it is valid, and its shape is what the README says."""

import os
from pathlib import Path

import pytest

from pawabase_iac import project
from pawabase_iac.engine import apply_plan, build_plan
from pawabase_iac.environments import EmulatedEnvironment
from pawabase_iac.validate import check

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def items():
    for name in ("PAYMENTS_HOOK_SECRET", "SMS_WEBHOOK_SECRET", "ACCOUNTING_WEBHOOK_SECRET"):
        os.environ.setdefault(name, "x" * 32)
    return project.load_project(project.load(ROOT))


def of(items, kind):
    return [i for i in items if i.kind == kind]


def test_the_project_is_valid(items):
    assert check(items) == []


def test_it_defines_the_whole_school(items):
    counts = {kind: len(of(items, kind)) for kind in ("roles", "policies", "resources", "flows", "routes", "subscriptions", "schedules", "buckets", "mail-templates")}
    assert counts["roles"] == 11 and counts["resources"] >= 35 and counts["flows"] >= 25 and counts["mail-templates"] == 8
    assert counts["buckets"] == 6 and counts["schedules"] == 5 and counts["routes"] == 2
    assert len(items) >= 130


def test_every_flow_can_start_and_is_reachable_some_way(items):
    reached = set()
    for kind in ("subscriptions", "schedules", "inbound-hooks", "routes"):
        reached |= {i.body(resolve=False).get("target") or i.body(resolve=False).get("handler") for i in of(items, kind)}
    for flow in of(items, "flows"):
        nodes = flow.graph()["nodes"]
        blocks_used = {n["data"]["block"] for n in nodes}
        triggers = {b for b in blocks_used if b.startswith("trigger.")}
        assert triggers, f"{flow.name} has no trigger"
        direct = "trigger.http" in triggers and any(n["data"]["block"] == "trigger.http" and not n["data"]["config"].get("path") for n in nodes)
        queued = any(
            n["data"]["block"] in ("queue.flow", "flow.call") and n["data"]["config"].get("flow") == flow.name
            for other in of(items, "flows") for n in other.graph()["nodes"]
        )
        self_started = bool(triggers & {"trigger.event", "trigger.schedule", "trigger.webhook"})
        assert flow.name in reached or direct or queued or self_started, f"nothing starts {flow.name}"


def test_rows_about_a_student_all_carry_the_family_fields(items):
    for table in ("attendance", "grades", "report_cards", "invoices", "payments", "leave_requests", "health_records", "incidents", "submissions"):
        names = {f["name"] for f in next(t for t in of(items, "resources") if t.name == table).fields}
        assert {"student_user_id", "guardian_ids"} <= names, table


def test_link_guardian_account_backfills_exactly_those_tables(items):
    flow = next(f for f in of(items, "flows") if f.name == "link_guardian_account")
    listed = next(n for n in flow.graph()["nodes"] if n["id"] == "each_table")["data"]["config"]["items"]
    carrying = {t.name for t in of(items, "resources") if {"student_id", "guardian_ids"} <= {f["name"] for f in t.fields}}
    assert set(listed) == carrying - {"students"}


def test_secrets_never_appear_in_the_code(items):
    for item in items:
        assert "x" * 32 not in repr(item.body(resolve=False))
    secrets = [i for i in items if i.kind in ("webhooks", "inbound-hooks")]
    assert all(s.secret is not None for s in secrets) and len(secrets) == 3


def test_an_emulated_deploy_is_stable(items):
    env = EmulatedEnvironment()
    outcomes = apply_plan(build_plan(items, env), items, env, resolve=False)
    assert outcomes and all(o.ok for o in outcomes)
    assert build_plan(items, env).summary()["create"] == 0  # a second plan against the same pretend environment finds nothing to do
