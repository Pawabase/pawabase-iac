from pawabase_iac import Agent, Connection, Embed, Flow, Index, KnowledgeBase, Policy, P, String, Table, Text, Vector, blocks, crud, tools
from pawabase_iac.validate import check


def problems(project):
    return "\n".join(map(str, check(project.items)))


def test_an_agent_with_everything_it_needs_is_valid(project):
    mine = Policy("mine", P.owner("user_id"))
    orders = Table("orders", fields=[String("user_id")], operations=crud(mine), owner_field="user_id")
    refund = Flow("refund")
    refund.chain(blocks.trigger.manual(), blocks.response.return_(body={"ok": True}))
    github = Connection.mcp("github", "https://api.githubcopilot.com/mcp/", secret="GITHUB_TOKEN")
    help_articles = KnowledgeBase("help", embedding_model="embed", policy="authenticated")
    Agent(
        "support", model="chat", policy="authenticated", knowledge=[help_articles],
        tools=[tools.table(orders, ["list", "get"]), tools.flow(refund, description="Refund an order"), tools.mcp(github), tools.web_search(), tools.code()],
        limits={"max_steps": 8, "max_cost": 0.5},
    )
    assert check(project.items) == []
    body = project.items[-1].body()
    assert body["knowledge"] == ["help"]
    assert body["tools"][0] == {"kind": "table", "resource": "orders", "actions": ["list", "get"]}
    assert body["tools"][1]["flow"] == "refund" and body["tools"][2]["connection"] == "github"


def test_a_connection_is_sent_as_the_server_calls_it(project):
    body = Connection.notion("wiki", secret="NOTION_KEY").body()
    assert body["kind"] == "notion" and "service" not in body
    jira = Connection.mcp("jira", "https://mcp.atlassian.com/v1/mcp", secret="JIRA", auth="basic", username="a@b.co")
    assert jira.body()["config"] == {"url": "https://mcp.atlassian.com/v1/mcp", "auth": "basic", "username": "a@b.co"}
    assert Connection.web_search("ddg", provider="duckduckgo").problems() == []


def test_connections_say_what_they_still_need(project):
    messages = {
        "needs the name of the secret": Connection.notion("n", secret=""),
        "http or https address": Connection.mcp("m", "ftp://nope"),
        "needs the email": Connection.mcp("m2", "https://x.test/mcp", auth="basic"),
        "name the header": Connection.mcp("m3", "https://x.test/mcp", auth="header"),
        "choose a search provider": Connection.web_search("w", provider="bing"),  # type: ignore[arg-type]
        "its key": Connection.web_search("w2", provider="exa"),
    }
    for expected, item in messages.items():
        assert any(expected in p for p in item.problems()), (expected, item.problems())


def test_references_between_agents_are_checked(project):
    Agent("a", model="chat", knowledge=["ghost_kb"], tools=[
        tools.table("ghost_table"), tools.flow("ghost_flow"), tools.mcp("ghost_conn"), tools.agent("a"), tools.agent("ghost_agent"),
    ], policy="ghost_policy")
    text = problems(project)
    for expected in ("'ghost_kb' is not defined", "'ghost_table' is not defined", "'ghost_flow' is not defined", "'ghost_conn' is not defined",
                     "'ghost_agent' is not defined", "can't hand work to itself", "'ghost_policy' is not defined"):
        assert expected in text, (expected, text)


def test_tools_are_checked_on_their_own(project):
    bad = Agent("b", model="", tools=[tools.table("t", ["explode"]), tools.notion("n", ["fly"]), tools.image("", ""), {"kind": "magic"}, "no"],  # type: ignore[list-item]
                limits={"max_steps": 0, "speed": 3})
    text = "\n".join(bad.problems())
    for expected in ("model names a chat model", "can't explode", "Notion can't fly", "name the provider", "unknown tool kind", "build tools with", "whole number above zero", "unknown limit"):
        assert expected in text, (expected, text)


def test_a_knowledge_base_is_checked(project):
    assert KnowledgeBase("help", embedding_model="embed").problems() == []
    text = "\n".join(KnowledgeBase("Help", embedding_model="", chunk_size=100, chunk_overlap=500).problems())
    for expected in ("not a valid name", "embedding_model", "chunk_size", "smaller than chunk_size"):
        assert expected in text


def test_vector_fields_and_indexes(project):
    table = Table(
        "articles", fields=[String("title"), Text("body"), Vector("embedding", dimensions=1536, embed=Embed("embed", "title", "body"))],
        indexes=[Index("embedding", method="hnsw", metric="l2")],
    )
    assert table.problems() == []
    assert table.fields[-1] == {"name": "embedding", "type": "vector", "dimensions": 1536, "embed": {"model": "embed", "from": ["title", "body"]}}
    assert table.indexes[0]["method"] == "hnsw" and table.indexes[0]["metric"] == "l2"
    bad = Table("b", fields=[String("t"), Vector("v", dimensions=0, embed=Embed("m", "nope"))], indexes=[Index("t", "v", method="hnsw", metric="euclid")])
    text = "\n".join(bad.problems())
    for expected in ("needs dimensions", "not a string or text field", "covers one vector column", "metric is cosine, l2 or ip"):
        assert expected in text, (expected, text)


def test_flows_that_call_agents_and_knowledge_are_checked(project):
    flow = Flow("ask")
    flow.chain(blocks.trigger.manual(), blocks.ai.agent(agent="ghost", input="hi"), blocks.ai.knowledge_search(base="ghost_kb", query="x"))
    text = problems(project)
    assert "'ghost' is not defined" in text and "'ghost_kb' is not defined" in text
