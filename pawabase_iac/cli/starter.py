STARTER = '''"""Your backend, as code.  pawabase validate  →  pawabase emulate  →  pawabase deploy"""

from pawabase_iac import Allow, BelongsTo, Boolean, Flow, Index, Integer, P, Policy, Route, Schedule, String, Table, Text, blocks, crud, ctx

# Who may do what.
mine = Policy("mine", P.owner("user_id"), description="The signed-in user owns the row.")
staff = Policy("staff", P.role("admin") | P.role("support"))

# Tables, each with a generated REST API under /rest/v1/<name>.
projects = Table(
    "projects",
    fields=[String("name", required=True, max_length=120), Text("notes"), String("user_id", required=True)],
    operations=crud(mine, delete=Allow(staff)),
    owner_field="user_id",
    realtime=True,
)
todos = Table(
    "todos",
    fields=[
        String("title", required=True, max_length=200),
        Boolean("done", default=False),
        Integer("priority", minimum=1, maximum=5, default=3),
        String("project_id", required=True),
        String("user_id", required=True),
    ],
    operations=crud(mine),
    relations=[BelongsTo("project", projects, "project_id")],
    indexes=[Index("project_id", "done")],
    owner_field="user_id",
)

# Logic: a flow is a graph of blocks. `>>` follows the next handle; `.true` / `.false` / `.error` follow others.
summary = Flow("project_summary", description="Open and done counts for a project")
start = summary.add(blocks.trigger.http(method="GET", path="/projects/summary", policy="authenticated"))
open_todos = summary.add(blocks.resource.list(resource=todos, filters={"project_id": ctx.input.project_id, "done": False}))
start >> open_todos
count = summary.add(blocks.transform.summarize(value=ctx.steps.resource_list.output, operation="count"))
open_todos >> count
count >> blocks.response.return_(body={"open": ctx.steps.transform_summarize.output})

Route("/projects/summary", handler=summary, method="GET", policy="authenticated")

# Work that happens on its own.
nightly = Flow("nightly_tidy", description="Log that the nightly job ran")
nightly.chain(blocks.trigger.schedule(cron="0 3 * * *"), blocks.log.write(message="nightly tidy ran", level="info"))
Schedule("nightly_tidy", run=nightly, cron="0 3 * * *", overlap="skip")
'''
