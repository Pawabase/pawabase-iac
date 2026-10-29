"""The library sends what the server accepts. Runs only where ``pawabase_server`` is importable (the Pawabase repo's environment):

    cd ../../pawabase && uv run --no-sync python -m pytest ../_split/python-iac/tests/test_server_conformance.py -p no:cacheprovider
"""

import pytest

pytest.importorskip("pawabase_server")

from pawabase_server.flows.engine import validate_flow  # noqa: E402
from pawabase_server.policies.engine import validate_condition  # noqa: E402
from pawabase_server.routes.identity.admin import RoleBody  # noqa: E402
from pawabase_server.routes.platform.definitions import KINDS as SERVER_KINDS  # noqa: E402

from pawabase_iac import (  # noqa: E402
    Bucket, Flow, InboundHook, MailTemplate, P, Policy, Role, Route, Schedule, Schema, String, Subscription, Table, Transformer, Webhook,
    blocks, crud, ctx, every,
)
from pawabase_iac.flows.catalogue import BLOCKS  # noqa: E402
from pawabase_iac.kinds import KINDS  # noqa: E402


def sample_flow():
    f = Flow("sample")
    start, check = f.chain(blocks.trigger.http(method="POST", path="/s"), blocks.control.if_(P.input.n > 1))
    check.true >> blocks.response.return_(body={"ok": True})
    check.false >> blocks.error.raise_(status=422, message="n too small")
    return f


def samples():
    mine = Policy("mine", P.owner("user_id"))
    flow = sample_flow()
    return [
        Role("teacher", permissions=["grades.write"]),
        Schema("Address", fields=[String("city")]),
        Transformer("t", omit=["x"], case="camel"),
        mine,
        Table("orders", fields=[String("user_id")], operations=crud(mine), owner_field="user_id"),
        flow,
        Bucket("files"),
        MailTemplate("welcome", subject="Hi", html="<p>Hi {{ name }}</p>"),
        Route("/s", handler=flow),
        Subscription("sub", on="e", run=flow),
        Webhook("hook", url="https://example.com/h"),
        InboundHook("inbound", event="e", verification="none"),
        Schedule("sched", run=flow, interval=every(minutes=1)),
    ]


def test_every_kind_is_covered_and_named_like_the_server():
    assert {k["path"] for k in SERVER_KINDS} | {"roles"} == set(KINDS)


@pytest.mark.parametrize("item", samples(), ids=lambda i: i.label)
def test_body_fields_match_the_servers_request_model(item):
    model = RoleBody if item.kind == "roles" else next(k for k in SERVER_KINDS if k["path"] == item.kind)["body"]
    ours = set(item.body())
    theirs = set(model.model_fields)
    # The server has optional fields we do not manage from code (draft/design/favorite, a branch's autosave): they keep their defaults.
    extra_on_server = theirs - ours
    assert not (ours - theirs), f"{item.kind}: sent but the server has no such field: {sorted(ours - theirs)}"
    assert extra_on_server <= {"design", "draft", "favorite", "apply_schema", "provision_table"}, f"{item.kind}: server fields we do not send: {sorted(extra_on_server)}"
    model.model_validate(item.body())  # the server's own request model accepts it


def test_flow_documents_pass_the_servers_validator():
    assert validate_flow(sample_flow().graph()) == []


def test_conditions_pass_the_servers_validator():
    for cond in (P.owner(), P.role("a") | P.role("b"), ~P.service(), P.record.title.matches("^x"), P.input.n.in_([1, 2]), P.aal("aal2")):
        validate_condition(cond.json())


def test_the_catalogue_matches_the_running_servers_blocks():
    from pawabase_server.flows.registry import default_registry

    server = {b["key"]: b for b in default_registry().catalogue()}
    assert set(server) == set(BLOCKS), f"regenerate with scripts/generate_blocks.py: {sorted(set(server) ^ set(BLOCKS))}"
    for key, block in server.items():
        assert block["handles"] == BLOCKS[key]["handles"], key
        assert [c["name"] for c in block["config"]] == list(BLOCKS[key]["config"]), key
