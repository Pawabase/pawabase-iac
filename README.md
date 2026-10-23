# pawabase-iac

**Pawabase as code.** Define a whole [Pawabase](https://github.com/Pawabase/pawabase) backend in Python (tables, access policies, flows, routes, events, schedules, webhooks, buckets, email templates, roles), check it before anything is sent, see what a deploy would change, rehearse it against a simulated environment, and deploy it with an API key.

```bash
pip install pawabase-iac

pawabase init          # pawabase.toml, infra/app.py, .env.example
pawabase validate      # offline: every definition and every reference between them
pawabase emulate       # a pretend deploy: nothing real is touched, no key needed
pawabase plan          # what a deploy would change in the real environment (reads only)
pawabase deploy        # apply it; needs a deploy API key
```

* **Everything is code.** A table, a policy, a flow with branches and loops, a cron schedule: all Python you can review, test and version.
* **Checked before it is sent.** Names, field types, constraints, policy conditions, flow graphs, template syntax, block settings and the references between all of them are validated offline, with the server's own rules.
* **A plan before a change.** `plan` and `deploy --dry-run` show what would be created (`+`), changed (`~`, with the fields that differ) or removed (`-`).
* **Safe by default.** Pushing needs a secret API key; `merge` mode never deletes what your code does not mention; production asks first; secrets never sit in the code.

## Contents

[Quick start](#quick-start) · [Defining things](#defining-things) · [Policies](#policies) · [Flows](#flows) · [Commands](#commands) · [Deploying](#deploying) · [Emulate](#emulate) · [Using it in CI](#using-it-in-ci) · [Examples](#examples) · [Development](#development) · [Limits](#limits)

## Quick start

```bash
mkdir shop && cd shop
pawabase init
```

`pawabase.toml` says where to deploy (the key does not live here):

```toml
url = "http://localhost:8080"     # your Pawabase gateway
environment = "development"      # the environment to deploy to
entry = "infra"                  # a file or a folder of .py files holding your definitions
```

`infra/app.py` is a small working backend. Make the API key (Studio → API keys → New key → **Secret**, preset **Deploy and configure**) and put it in `.env`:

```bash
echo 'PAWABASE_API_KEY=pb_sk_...' >> .env
pawabase validate && pawabase emulate && pawabase deploy
```

Edit a definition and run `pawabase plan` to see exactly what changes before you deploy it.

## Defining things

Definitions register themselves as they are made. Files in your `entry` folder can import each other (`from infra.policies import mine`), and each file runs once. Pass a definition wherever a name is expected (`resource=todos`, `handler=summary`, `run=nightly`, `operations=crud(mine)`) and it is replaced by its name, so a rename follows and `validate` can see the dependency.

```python
from pawabase_iac import (
    Allow, Array, BelongsTo, Boolean, Desc, Email, Index, Integer, P, Policy, RateLimit, Role, String, Table, Where, crud,
)

Role("teacher", permissions=["grades.write"], description="Teaching staff")

mine = Policy("mine", P.owner("user_id"))
staff = Policy("staff", P.role("admin") | P.role("teacher"))

students = Table(
    "students",
    fields=[
        String("user_id", unique=True),
        String("admission_number", required=True, unique=True, max_length=20),
        Email("email"),
        Integer("age", minimum=3, maximum=25),
        String("status", enum=["active", "graduated", "withdrawn"], default="active"),
        Array("guardian_ids", of=String("guardian_id")),
    ],
    operations=crud(staff, get=Allow(mine.condition | staff.condition), delete=Allow(P.role("admin"))),
    indexes=[Index("status", Desc("age"), where=[Where("status", "!=", "withdrawn")])],
    rate_limit=RateLimit(120, 60),
    realtime=True,
)
```

| Kind | Class | What you set |
|---|---|---|
| Table | `Table` (also `Resource`) | typed fields, operations with a policy each, relations (`BelongsTo`, `HasMany`), indexes (`Index`, `Desc`, `Where`), rate limit, caching, owner field, realtime, event capture |
| Fields | `String`, `Text`, `Integer`, `Number`, `Boolean`, `DateTime`, `Date`, `UUID`, `ULID`, `Email`, `URL`, `JSON`, `Array`, `Object`, `Ref` | `required`, `nullable`, `default`, `unique`, `indexed`, `enum`, `min_length`/`max_length`, `minimum`/`maximum`, `pattern`, `read_only`, `write_only`, nested fields and items |
| Shapes | `Schema`, `Transformer` | reusable data shapes; omit / pick / set / rename / case on the way out |
| Access | `Role`, `Policy` | roles and their permission names; policies as Python expressions |
| Logic | `Flow`, `Route` | a graph of blocks; a custom HTTP endpoint that runs a flow |
| Events | `Subscription`, `Schedule`, `Webhook`, `InboundHook` | react to events, run on cron or an interval, call out, be called (signed) |
| Files | `Bucket` | per-action access policies, accepted types, size, signed URLs, image transforms, caching |
| Email | `MailTemplate` | subject / html / text with `{{ variables }}`, status, categories |

Secrets are never written in code: `Webhook(..., secret=env("ERP_SECRET"))` reads the variable when you deploy and refuses to deploy if it is unset.

## Policies

```python
from pawabase_iac import P, Policy, all_of, any_of

Policy("owner_or_staff", P.owner("user_id") | P.role("admin"))
Policy("paid_and_verified", P.authenticated() & (P.auth.plan != "free") & P.auth.email_verified.truthy())
Policy("family", (P.record.student_user_id == P.auth.user_id) | P.record.guardian_ids.contains(P.auth.user_id))
Policy("not_suspended", ~P.record.suspended.truthy())
```

`P.auth`, `P.record`, `P.input`, `P.request`, `P.env` and `P.credential` are paths into what a policy can see. Comparing a path builds a condition (`==`, `!=`, `>`, `>=`, `<`, `<=`, `.in_()`, `.not_in()`, `.contains()`, `.startswith()`, `.endswith()`, `.matches()`, `.exists()`, `.truthy()`, `.empty()`); `&`, `|` and `~` combine them. The shorthand checks are `P.authenticated()`, `P.role()`, `P.permission()`, `P.owner()`, `P.service()`, `P.kind()`, `P.scope()` and `P.aal()`. A condition has no truth value in Python, so `and` / `or` / `not` raise instead of silently dropping half a policy.

## Flows

```python
from pawabase_iac import Flow, P, blocks, ctx

invoice = Flow("issue_invoice", description="Invoice a student")
start = invoice.add(blocks.trigger.http(method="POST", policy="finance_staff").named("start"))
student = invoice.add(blocks.resource.get(resource="students", id=ctx.input.student_id).named("student"))
missing = invoice.add(blocks.error.raise_(status=404, message="No such student").named("missing"))
fees = invoice.add(blocks.resource.list(resource="fee_structures", filters={"grade": ctx.steps.student.output.grade}, limit=1).named("fees"))
total = invoice.add(blocks.transform.summarize(value=ctx.steps.fees.output.data[0].items, operation="sum", field="amount").named("total"))
big = invoice.add(blocks.control.if_(P.steps.total.output > 100000).named("big"))
review = invoice.add(blocks.event.emit(event="invoice.needs_review", payload={"total": ctx.steps.total.output}).named("review"))
done = invoice.add(blocks.response.return_(status=201, body={"total": ctx.steps.total.output}).named("done"))

start >> student
student.missing >> missing
student >> fees >> total >> big
big.true >> review >> done
big.false >> done
```

`a >> b` follows the `next` handle; `a.true >> b`, `a.error >> b` or `a.on("done") >> b` follow others. `flow.chain(a, b, c)` adds and links in one go; `flow["id"]` returns a node you named with `.named("id")`.

All **69 flow blocks** the server knows are available as typed functions, one module per family, every option documented with its default, limits and allowed values: `auth` · `cache` · `control` (if, switch, foreach, while, retry, timeout, set, merge, delay, stop) · `crypto` · `db` · `error` · `event` · `flow` · `http` · `json` · `log` · `mail` · `math` · `metric` · `policy` · `queue` · `realtime` · `resource` · `response` · `secret` · `storage` · `time` · `transform` (map, filter, sort, group, unique, flatten, slice, batch, pick, rename, summarize, template) · `trigger` (http, event, schedule, webhook, resource, job, realtime, manual) · `util` · `validate` · `webhook`.

### The rules the server enforces (and `validate` checks)

* **Templates are lookups.** `{{ steps.load.output.id }}` and the filters `default`, `upper`, `lower`, `length`, `int`, `float`, `str`, `bool`, `first`, `last`, `keys`, `json`; nothing else. No arithmetic, no comparison, no path after a filter. Compute with `blocks.math.calculate`; decide with `blocks.control.if_(P.steps.x.output.n > 3)`. A value that is exactly one template keeps its type (a list stays a list).
* **Conditions use `P`** (`control.if_`, `control.while_`, `transform.filter`): `P.input.x`, `P.steps.<id>.output.y`, `P.vars.z`, `P.item.w`.
* **What `input` holds** depends on how the flow started: an HTTP flow gets the body (`POST /flows/v1/<name>` for a trigger with no `path`) or `{params, query, body, headers}` (a `Route`); an event flow gets `{"event": {name, payload}}` (a table's changes are `<table>.created|updated|deleted` with the row at `payload.record`); a schedule gets `{scheduled_at}` or its payload; an inbound hook gets `{hook, headers, body}`.
* **Loops.** `ctx.item` and `ctx.index` are the current element and a nested loop shadows the outer `item`: keep what you need with `blocks.control.set(values={...})` and read it from `ctx.vars`. A loop's output is the list of its body's last outputs.
* **`validate.schema` is strict**: declare every optional input as well, or it is refused.
* **Debug a deployed flow** with `POST /platform/v1/envs/<env>/flows/<name>/run {"input": {...}}`: it returns the result, or a step-by-step trace.

## Commands

| Command | |
|---|---|
| `pawabase init` | start a project here |
| `pawabase validate` | check every definition and reference; contacts nothing |
| `pawabase plan` | compare your code with the environment; writes nothing |
| `pawabase deploy` | apply the plan (`--dry-run`, `--yes`, `--mode`, `--force-secrets`, `--no-migrate`) |
| `pawabase emulate` | rehearse a deploy against a simulated environment (`--reset`) |
| `pawabase whoami` | show the settings and test the API key |

Shared options: `-e/--env`, `--url`, `--entry`, `--json`. Exit code 0 on success, 1 on a failure or a refusal, 2 when `--yes` was needed but not given.

## Deploying

**A key is required to push.** `deploy` refuses without `PAWABASE_API_KEY` (in `.env` or the environment), and accepts only a *secret* key (`pb_sk…`). Use a **deploy key**: Studio → API keys → New key → Secret → preset *Deploy and configure*. It may change tables, policies, routes, flows, mail templates, roles, buckets, webhooks, hooks, subscriptions and schedules, and nothing else: not users, not API keys, not the database console, not the environment itself. The gateway refuses every other request from it.

**Modes.**

* `--mode merge` (default) creates and changes what your code defines and leaves everything else alone. Anything in the environment that your code does not mention is shown as `?` in the plan.
* `--mode override` makes the environment match your code exactly and **deletes the rest**. It asks first (or needs `--yes`).

**What happens.** Everything is validated first; if an `env("…")` variable is unset nothing is sent. Definitions are applied in dependency order (roles, schemas, transformers, policies, tables, flows, buckets, templates, routes, subscriptions, webhooks, hooks, schedules). After a table is created or changed its table is migrated: columns are created or **added**, never dropped. The deploy stops at the first refusal and tells you how many later changes were not attempted; what was applied stays applied, so fix it and deploy again. Production environments (`production`, `prod`, `live`) need `--yes` when not interactive.

**Secrets.** `Webhook` and `InboundHook` secrets are write-only: sent when the definition is created or otherwise changes, never compared. Rotate one with `--force-secrets`.

**How it compares.** The server fills in defaults and ids, so the comparison asks only whether what you wrote is present in what the server returns (an empty value matches a missing one). Fields the server derives when unset (a table's `table` name) are not compared.

## Emulate

`pawabase emulate` runs the same validation and planning against a **simulated** environment kept in `.pawabase/emulator-<env>.json`. It never touches a server and needs no key. It prints the plan, applies it to the pretend environment, and shows what the result would serve: every REST endpoint with its policy, custom routes, hooks, schedules, webhooks, subscriptions and buckets. Run it again after editing to see only what changed; `--reset` starts empty; `--mode override` shows what a destructive deploy would remove.

## Using it in CI

```yaml
- run: pip install pawabase-iac
- run: pawabase validate                       # on every pull request
- run: pawabase plan                           # show the diff in the log
  env: { PAWABASE_URL: ${{ vars.PAWABASE_URL }}, PAWABASE_API_KEY: ${{ secrets.PAWABASE_DEPLOY_KEY }} }
- run: pawabase deploy --yes                   # on merge to main
  env: { PAWABASE_URL: ${{ vars.PAWABASE_URL }}, PAWABASE_API_KEY: ${{ secrets.PAWABASE_DEPLOY_KEY }}, ERP_SECRET: ${{ secrets.ERP_SECRET }} }
```

`PAWABASE_URL` and `PAWABASE_ENV` override `pawabase.toml`.

## Examples

* [`examples/store`](examples/store): a small shop (tables, a checkout flow with a loop, retry and error paths, a receipt flow, switch-based ticket routing, subscriptions, a webhook, a signed inbound hook, buckets, a mail template).
* [`examples/school`](examples/school): a complete **school management system**: 11 roles, 22 policies, 43 tables, 25 flows, routes, subscriptions, schedules, signed payment webhooks, buckets and email templates (136 definitions) with a smoke test that runs the real flows against a deployed environment and its own offline tests.

## Development

```bash
pip install -e '.[test]'
pytest                              # the library, offline
```

The conformance tests compare every definition's request body with the server's own request models, run flows through the server's flow validator and check the generated block catalogue against the running server's. They run where `pawabase_server` is importable:

```bash
cd ../pawabase && PYTHONPATH=../pawabase-iac uv run python -m pytest ../pawabase-iac/tests/test_server_conformance.py
```

Regenerate the flow blocks when the server gains some:

```bash
cd ../pawabase && uv run python ../pawabase-iac/scripts/generate_blocks.py
```

```
pawabase_iac/
  core/          base Definition, env(), the registry
  expr/          P (policy conditions) and ctx (flow templates)
  tables/        fields, Table, Schema, indexes, relations
  policies/      Policy, Transformer, condition checks
  access/        Role
  flows/         Flow builder, graph checks, layout, catalogue.py and blocks/ (generated)
  api/           Route
  events/        Subscription, Schedule, Webhook, InboundHook
  storage/       Bucket
  mail/          MailTemplate
  validate/      cross-definition reference checks
  engine/        plan, apply, diff, what-it-serves
  environments/  Remote (the Platform API) and Emulated (in memory)
  project/       pawabase.toml, .env, importing your definitions
  cli/           the pawabase command
```

## Limits

Environment-level settings are not managed from code yet: auth providers and settings, secrets, API keys, firewall rules, domains, alarms, dashboards, backup schedules, and mail and storage connection settings. Users are not managed either (give people roles in Accounts). The twelve kinds above are.

## License

BSD 3-Clause. See [LICENSE](LICENSE).
