import pytest

from pawabase_iac import Bucket, Flow, Policy, P, String, Table, Webhook, blocks, crud, env
from pawabase_iac.engine import apply_plan, build_plan, differences
from pawabase_iac.environments import ApiError, EmulatedEnvironment


def sample(project):
    mine = Policy("mine", P.owner())
    Table("orders", fields=[String("owner_id")], operations=crud(mine))
    f = Flow("f")
    f.chain(blocks.trigger.manual(), blocks.control.noop())
    Bucket("files", public=True)
    return project.items


def deploy(items, env_, mode="merge", **kw):
    plan = build_plan(items, env_, mode, **kw)
    outcomes = apply_plan(plan, items, env_)
    assert all(o.ok for o in outcomes), [o.error for o in outcomes]
    return plan


def test_first_deploy_creates_in_dependency_order_then_nothing_changes(project):
    items = sample(project)
    env_ = EmulatedEnvironment()
    plan = build_plan(items, env_)
    assert [c.label for c in plan.of("create")] == ["policies/mine", "resources/orders", "flows/f", "buckets/files"]
    apply_plan(plan, items, env_)
    again = build_plan(items, env_)
    assert again.summary() == {"create": 0, "update": 0, "delete": 0, "noop": 4, "extra": 0}


def test_a_change_is_an_update_with_a_diff(project):
    items = sample(project)
    env_ = EmulatedEnvironment()
    deploy(items, env_)
    items[-1].public = False
    plan = build_plan(items, env_)
    (change,) = plan.of("update")
    assert change.label == "buckets/files" and change.diff == {"public": (True, False)}


def test_merge_leaves_extras_and_override_deletes_them(project):
    items = sample(project)
    env_ = EmulatedEnvironment()
    deploy(items, env_)
    env_.create("buckets", {"name": "old", "public": False})
    merge = build_plan(items, env_, "merge")
    assert [c.label for c in merge.of("extra")] == ["buckets/old"] and not merge.pending
    override = build_plan(items, env_, "override")
    assert [c.label for c in override.of("delete")] == ["buckets/old"]
    apply_plan(override, items, env_)
    assert [r["name"] for r in env_.list("buckets")] == ["files"]


def test_the_server_adding_defaults_is_not_a_difference():
    assert differences({"a": 1, "extra": 2, "n": {"x": 1, "y": 2}}, {"a": 1, "n": {"x": 1}}) == []
    assert differences({"a": None, "b": []}, {"a": "", "b": None}) == []
    assert differences({"a": 1}, {"a": 2}) == [("a", 1, 2)]
    assert differences({"l": [1, 2]}, {"l": [1]}) == [("l", [1, 2], [1])]
    assert differences({"t": 5.0}, {"t": 5}) == []


def test_secrets_are_write_only_and_not_compared(project, monkeypatch):
    monkeypatch.setenv("S", "s" * 20)
    Webhook("w", url="https://x.example/h", secret=env("S"))
    env_ = EmulatedEnvironment()
    deploy(project.items, env_)
    row = env_.list("webhooks")[0]
    assert "secret" not in row and row["secret_set"] is True
    assert build_plan(project.items, env_).summary()["update"] == 0
    assert build_plan(project.items, env_, force_secrets=True).summary()["update"] == 1


def test_a_failure_stops_the_deploy_there(project):
    items = sample(project)
    env_ = EmulatedEnvironment()
    env_.create("buckets", {"name": "files"})
    plan = build_plan(items, env_)
    plan.changes.insert(0, plan.changes[-1].__class__("create", "buckets", "files", {"name": "files"}))
    outcomes = apply_plan(plan, items, env_)
    assert not outcomes[-1].ok and "already exists" in outcomes[-1].error


def test_emulated_state_survives_a_restart(project, tmp_path):
    items = sample(project)
    path = tmp_path / "state.json"
    env_ = EmulatedEnvironment("dev", path)
    deploy(items, env_)
    env_.save()
    assert build_plan(items, EmulatedEnvironment("dev", path)).summary()["noop"] == 4


def test_renaming_through_replace_is_refused():
    env_ = EmulatedEnvironment()
    live = env_.create("buckets", {"name": "a"})
    with pytest.raises(ApiError):
        env_.replace("buckets", live, {"name": "b"})


def test_roles_are_a_kind_and_migrations_run_for_tables(project):
    from pawabase_iac import Role

    Role("teacher", permissions=["b", "a"])
    Table("t", fields=[String("x")])
    env_ = EmulatedEnvironment()
    plan = build_plan(project.items, env_)
    assert [c.label for c in plan.of("create")] == ["roles/teacher", "resources/t"]
    outcomes = apply_plan(plan, project.items, env_)
    assert [o.statements for o in outcomes] == [[], ["(emulated) create or alter table for t"]]
    assert env_.list("roles")[0]["permissions"] == ["a", "b"]
    assert [o.statements for o in apply_plan(plan, project.items, EmulatedEnvironment(), migrate=False)] == [[], []]
