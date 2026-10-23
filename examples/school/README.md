# School management on Pawabase

A complete school system defined as code with [`pawabase-iac`](../..): 11 roles, 22 access policies, 43 tables, 25 flows, custom routes, event subscriptions, schedules, inbound and outbound webhooks, 8 email templates and 6 file buckets. 136 definitions, deployed to the `school` environment of the local Pawabase.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ../.. pytest   # once
.venv/bin/pawabase validate          # offline: every definition and every reference
.venv/bin/pawabase emulate           # a pretend deploy, nothing real is touched
.venv/bin/pawabase plan              # what a deploy would change in `school`
.venv/bin/pawabase deploy            # apply it (needs PAWABASE_API_KEY, a deploy key)
.venv/bin/python scripts/smoke_test.py   # run the real flows against the deployed environment
.venv/bin/python -m pytest tests     # the project's own offline tests
```

`pawabase.toml` says where; `.env` holds the deploy key and the three webhook secrets; `.env.local` holds the environment's full-access keys for the smoke test. Neither is committed.

## What is in it

| File | Defines |
|---|---|
| `infra/roles.py` | admin, principal, registrar, head_of_department, teacher, accountant, librarian, nurse, transport_officer, student, guardian, with their permissions |
| `infra/policies.py` | who may do what: staff groups (`management`, `registry`, `academic`, `finance_staff`…) and rules about a particular row (`family_of_record`, `student_record`, `health_confidential`…) |
| `infra/academics.py` | academic years, terms, departments, year groups, rooms, classes, subjects, curriculum, timetable |
| `infra/people.py` | students, guardians and their links, teachers, staff, enrolments |
| `infra/assessment.py` | assessment types, grade scale, assessments, grades, report cards, assignments, submissions, lesson plans |
| `infra/attendance.py` | attendance, daily totals, leave requests |
| `infra/finance.py` | fee structures, scholarships, invoices and lines, payments |
| `infra/campus.py` | library, transport, health records, incidents, announcements, calendar, messages |
| `infra/admissions.py` | applications (public form to decision) |
| `infra/flows_*.py` | the 25 flows, below |
| `infra/delivery.py` | routes, subscriptions, schedules, hooks, webhooks, buckets and mail templates that connect the flows to the world |

### Flows

| Flow | Starts from | Does |
|---|---|---|
| `enroll_student` | `POST /flows/v1/enroll_student` (registry) | validates, checks the class has room, creates the student, finds or creates each guardian by email, links them, records the enrolment, counts the place, queues the first invoice |
| `link_guardian_account` | `user.created` | gives a new account to the guardian with that email and back-fills their children's rows in 12 tables so the family policies recognise them |
| `promote_students` | `POST /flows/v1/promote_students` | moves a class up a year, keeping history |
| `issue_term_invoice` / `issue_term_invoices` | queued by enrolment / term-start schedule | finds the fee structure, applies a percent or fixed scholarship, numbers the invoice, writes lines, mails the paying guardian |
| `record_payment` | signed hook `/hooks/v1/school/payments` | idempotent on the provider's reference; partial and full settlement; receipt email |
| `late_fee_sweep` | nightly | 5% late fee on past-due invoices, marks them overdue |
| `mark_attendance` | `POST /flows/v1/mark_attendance` | one call per register; a second submission corrects the first |
| `absence_alert` | `attendance.created` when absent | counts recent absences, emails the guardian, tells staff live, logs a concern from the third |
| `daily_attendance_summary` | weekdays 15:00 | groups the day's marks by class |
| `check_timetable_conflict` | `POST /flows/v1/…` | 409 if a teacher is already teaching then |
| `grade_posted` | `grades.created` | percentage, letter from the grade scale, low-score flag, live update |
| `compute_report_cards` / `publish_report_cards` / `notify_report_card` | HTTP / HTTP / `report_card.published` | per-subject averages, overall average and letter, class ranking; publishing; emailing the guardian |
| `assignment_reminders` | hourly | assignments due within a day, reminded once |
| `borrow_book` / `return_book` / `overdue_loans_sweep` | HTTP / HTTP / daily | copies on the shelf, 14-day loans, fines, overdue marking and reminders |
| `leave_decided` | `leave_requests.updated` | tells the guardian the decision |
| `announcement_fanout` | `announcements.created` | routes by audience (everyone, staff, one class, one year group, guardians by SMS) |
| `screen_application` / `decide_application` | `admission_applications.created` / HTTP | reference and score, acknowledgement, accept / waitlist / reject with the right email |
| `parent_dashboard` | `GET /rest/v1/parent/dashboard` | each child's latest attendance, invoices due and overdue, published report cards |
| `student_transcript` | `GET /rest/v1/students/{id}/transcript` | published report cards, after checking the caller may see this student |

## How access works

Rows about a student carry the student's user id and their guardians' user ids (`student_user_id`, `guardian_ids`), so one policy (`family_of_record`) answers "is this yours?" without joining tables. Staff are covered by role groups. A guardian signing up triggers `link_guardian_account`, which copies their account onto their children's existing rows. Guardians list only their own children's invoices, attendance, grades and so on; they cannot write; another family's transcript is a 403; the public admissions form can create an application but nobody without the registry role can read one.

## Try it

Make an environment for it (Studio → Environments → New, or `pawabase-server env create --project <project> school`), then:

```bash
# a deploy key for that environment: Studio → API keys → New key → Secret → "Deploy and configure"
cat > .env <<'ENV'
PAWABASE_API_KEY=pb_sk_...                      # the deploy key
PAYMENTS_HOOK_SECRET=...                         # any 16+ characters; the payment provider signs with it
SMS_WEBHOOK_SECRET=...
ACCOUNTING_WEBHOOK_SECRET=...
ENV
# a full-access key and the publishable key of the same environment, for the smoke test only
printf 'SCHOOL_ADMIN_KEY=pb_sk_...\nSCHOOL_PUBLISHABLE_KEY=pb_pk_...\n' > .env.local

.venv/bin/pawabase deploy
.venv/bin/python scripts/smoke_test.py       # 67 checks against the real flows
```

The deploy key can change definitions but cannot manage users, API keys, the database console or the environment itself. After a deploy, `pawabase plan` reports 0 changes. The smoke test leaves its records in the environment (each carries a short run id), so run it against a scratch environment.

## Not wired up

* Email goes to the environment's mail provider; none is configured locally, so `mail.send` queues and the delivery job fails quietly (the flows keep going).
* The SMS gateway, accounting and payment-provider URLs are placeholders (`*.example.com`).
* Student accounts: students' own rows use `student_user_id`, set when a student has an account; linking a student account is the same idea as `link_guardian_account` and is not written.
* Roles are defined, but giving a role to a person is done in Accounts (Studio → Users, or the users API).
