import pytest

from pawabase_iac import Flow, P, Table, blocks, ctx, String
from pawabase_iac.flows.catalogue import BLOCKS
from pawabase_iac.validate import check


def test_every_block_has_a_function():
    import keyword
    from importlib import import_module

    for key in BLOCKS:
        family, name = key.split(".", 1)
        module = import_module(f"pawabase_iac.flows.blocks.{family}")
        function = getattr(module, name + "_" if keyword.iskeyword(name) else name)
        assert function.__doc__, key


def test_a_flow_builds_the_studio_document(project):
    f = Flow("greet")
    start = f.add(blocks.trigger.http(method="POST", path="/greet"))
    check_node = f.add(blocks.control.if_(P.input.name.exists()), id="has_name")
    yes = f.add(blocks.response.return_(body={"hello": ctx.input.name}))
    no = f.add(blocks.response.return_(status=422, body={"error": "name?"}))
    start >> check_node
    check_node.true >> yes
    check_node.on("false") >> no
    assert f.problems() == []
    graph = f.graph()
    assert [n["id"] for n in graph["nodes"]] == ["trigger_http", "has_name", "response_return", "response_return_2"]
    assert graph["nodes"][2]["data"] == {"block": "response.return", "config": {"body": {"hello": "{{ input.name }}"}}}
    assert graph["nodes"][1]["data"]["config"] == {"condition": {"truthy": "$input.name"}} or graph["nodes"][1]["data"]["config"]["condition"] == {"exists": "$input.name"}
    assert {"id": "has_name-true-response_return", "source": "has_name", "target": "response_return", "sourceHandle": "true"} in graph["edges"]
    assert {"id": "trigger_http-next-has_name", "source": "trigger_http", "target": "has_name"} in graph["edges"]
    assert all("position" in n for n in graph["nodes"])


def test_chaining_and_error_branches(project):
    f = Flow("c")
    a, b, c = f.chain(blocks.trigger.manual(), blocks.log.write(message="x"), blocks.control.noop())
    b.error >> blocks.log.write(message="failed", level="error")
    assert f.problems() == []
    assert len(f.graph()["edges"]) == 3


def test_a_block_only_follows_its_own_handles(project):
    f = Flow("h")
    n = f.add(blocks.log.write(message="x"))
    with pytest.raises(ValueError, match="no 'true' handle"):
        n.on("true")
    with pytest.raises(AttributeError):
        n.true


def test_problems_the_server_would_report(project):
    f = Flow("bad")
    t = f.add(blocks.trigger.manual())
    t >> f.add(blocks.resource.list(resource="orders", limit=5000))
    f.add(blocks.control.delay(seconds=900))
    f.add(blocks.mail.send(to="a@b.c", text=ctx.steps.ghost.output))
    f.add(blocks.http.request(url="https://x.y", method="TEAPOT"))
    text = "\n".join(f.problems())
    assert "can never run" in text
    assert "seconds is at most 300" in text
    assert "refers to steps.ghost" in text
    assert "method is one of GET, POST" in text


def test_no_trigger_and_unknown_things(project):
    f = Flow("empty")
    f.add(blocks.log.write(message="x"))
    assert any("no trigger" in p for p in f.problems())
    raw = Flow("raw", definition={"nodes": [{"id": "a", "data": {"block": "nope.nope", "config": {"zzz": 1}}}], "edges": [{"source": "a", "target": "b"}]})
    text = "\n".join(raw.problems())
    assert "unknown block 'nope.nope'" in text and "does not exist" in text


def test_a_flow_passed_a_definition_cannot_also_be_built(project):
    f = Flow("raw", definition={"nodes": [], "edges": []})
    with pytest.raises(ValueError):
        f.add(blocks.control.noop())


def test_flows_reference_other_definitions(project):
    orders = Table("orders", fields=[String("x")])
    f = Flow("uses")
    f.chain(blocks.trigger.resource(resource=orders), blocks.resource.get(resource=orders, id=ctx.input.id),
            blocks.storage.put(bucket="ghost", key="k", content="c"), blocks.flow.call(flow="missing_flow"),
            blocks.mail.send(to="a@b.c", template="nope"))
    text = "\n".join(map(str, check(project.items)))
    assert "bucket 'ghost' is not defined" in text
    assert "'missing_flow' is not defined" in text
    assert "'nope' is not defined" in text
    assert "orders" not in text.replace("flows/uses", "")


def test_templates_are_lookups_with_filters_like_the_server_reads_them(project):
    assert ctx.input.name.default("guest").template() == '{{ input.name | default:"guest" }}'
    assert ctx.steps.list.output.data.length().template() == "{{ steps.list.output.data | length }}"
    assert ctx.input.items[0].template() == "{{ input.items.0 }}"
    assert ctx.input.name.upper().default("x").template() == '{{ input.name | upper | default:"x" }}'
    with pytest.raises(TypeError, match="cannot compare or calculate"):
        _ = ctx.input.n > 3
    with pytest.raises(TypeError):
        _ = ctx.input.n + 1
    with pytest.raises(ValueError, match="unknown template filter"):
        ctx.input.n.filter("round")

    f = Flow("t")
    f.chain(blocks.trigger.manual(), blocks.log.write(message="{{ input.a + 1 }}"), blocks.log.write(message="{{ input.b | round }}"),
            blocks.log.write(message="{{ input['x'] }}"), blocks.log.write(message=ctx.text("ok ", ctx.input.a.default("-"))))
    text = "\n".join(f.problems())
    assert text.count("only a path") == 2 and "unknown filter 'round'" in text
    assert "ok" not in text


def test_blocks_can_be_named_and_nodes_fetched_by_id(project):
    f = Flow("named")
    f.chain(blocks.trigger.manual().named("start"), blocks.resource.get(resource="x", id="1").named("load"), blocks.control.noop())
    f["load"].missing >> blocks.control.noop().named("gone")
    assert list(f.nodes) == ["start", "load", "control_noop", "gone"]
    with pytest.raises(KeyError, match="no node 'nope'"):
        f["nope"]
