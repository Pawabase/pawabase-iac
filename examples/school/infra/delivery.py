"""How the flows are reached and what sends the outside world in: routes, subscriptions, schedules, hooks, webhooks, templates and buckets."""

from infra.flows_academics import (
    absence_alert, assignment_reminders, check_timetable_conflict, compute_report_cards, daily_attendance_summary, grade_posted,
    mark_attendance, publish_report_cards,
)
from infra.flows_campus import (
    announcement_fanout, borrow_book, decide_application, leave_decided, notify_report_card, overdue_loans_sweep, return_book,
    screen_application,
)
from infra.flows_finance import issue_term_invoice, issue_term_invoices, late_fee_sweep, record_payment
from infra.flows_portal import parent_dashboard, student_transcript
from infra.flows_students import enroll_student, link_guardian_account, promote_students
from infra.policies import guardians_only

from pawabase_iac import (
    Bucket, InboundHook, MailTemplate, P, RateLimit, Route, Schedule, Subscription, Webhook, env, every, variable,
)

# ── routes (served under /rest/v1) ──────────────────────────────────────────
Route("/parent/dashboard", handler=parent_dashboard, method="GET", policy=guardians_only, cache_ttl=0, tags=["portal"])
Route("/students/{id}/transcript", handler=student_transcript, method="GET", policy="authenticated", rate_limit=RateLimit(30, 60), tags=["portal"])

# ── reacting to what happens ────────────────────────────────────────────────
Subscription("on_absence", on="attendance.created", run=absence_alert, condition=P.event.payload.record.status == "absent")
Subscription("complete_new_grades", on="grades.created", run=grade_posted)
Subscription("mail_published_report_cards", on="report_card.published", run=notify_report_card)
Subscription("on_leave_decided", on="leave_requests.updated", run=leave_decided)
Subscription("on_new_announcement", on="announcements.created", run=announcement_fanout)
Subscription("screen_new_applications", on="admission_applications.created", run=screen_application)
Subscription("link_new_accounts", on="user.created", run=link_guardian_account)
Subscription("staff_feed_for_payments", on="payment.received", publish_to="finance")
Subscription("staff_feed_for_enrolments", on="student.enrolled", publish_to="registry")

# ── on a timetable ──────────────────────────────────────────────────────────
Schedule("nightly_late_fees", run=late_fee_sweep, cron="0 2 * * *", timezone="Africa/Lagos", overlap="skip")
Schedule("morning_overdue_books", run=overdue_loans_sweep, cron="0 6 * * *", timezone="Africa/Lagos", overlap="skip")
Schedule("afternoon_attendance_totals", run=daily_attendance_summary, cron="0 15 * * 1-5", timezone="Africa/Lagos", overlap="skip")
Schedule("hourly_assignment_reminders", run=assignment_reminders, interval=every(hours=1), overlap="skip")
Schedule("term_start_invoicing", run=issue_term_invoices, cron="0 6 1 1,5,9 *", timezone="Africa/Lagos", overlap="skip", catch_up=True)

# ── the outside world ───────────────────────────────────────────────────────
InboundHook(
    "payments", run=record_payment, verification="hmac-sha256", signature_header="x-signature", secret=env("PAYMENTS_HOOK_SECRET"),
    description="The payment provider's notifications",
)
Webhook(
    "sms_gateway", url="https://sms.example.com/v1/pawabase", events=["announcement.sms", "invoice.overdue", "attendance.*"],
    secret=env("SMS_WEBHOOK_SECRET"), max_attempts=6, description="Sends text messages to guardians who prefer them",
)
Webhook(
    "accounting", url="https://accounts.example.com/hooks/school", events=["invoice.issued", "payment.received"],
    secret=env("ACCOUNTING_WEBHOOK_SECRET"), headers={"x-tenant": "school"}, description="Keeps the accountant's ledger in step",
)

# ── files ───────────────────────────────────────────────────────────────────
Bucket("student-photos", public=False, accepts=["image/png", "image/jpeg"], max_bytes=2_000_000, read_policy="staff_or_family", write_policy="registry",
       signed_downloads=True, description="Passport photos")
Bucket("report-cards", public=False, accepts=["application/pdf"], max_bytes=5_000_000, read_policy="staff_or_family", write_policy="academic_leads",
       signed_downloads=True, description="Term report card PDFs")
Bucket("assignment-files", public=False, accepts=["application/pdf", "image/png", "image/jpeg", "text/plain"], max_bytes=10_000_000,
       read_policy="authenticated", write_policy="authenticated", description="Handouts and submitted work")
Bucket("documents", public=False, accepts=["application/pdf", "image/png", "image/jpeg"], max_bytes=8_000_000, read_policy="registry", write_policy="public",
       description="Documents uploaded with an application")
Bucket("library-covers", public=True, accepts=["image/png", "image/jpeg", "image/webp"], max_bytes=1_000_000, write_policy="library_staff", cache_max_age=86400,
       description="Book covers")
Bucket("school-assets", public=True, accepts=["image/png", "image/svg+xml", "image/jpeg"], max_bytes=2_000_000, write_policy="management", cache_max_age=604800,
       description="Logo and branding")

# ── email ───────────────────────────────────────────────────────────────────
WRAP = '<div style="font-family:system-ui,sans-serif;max-width:560px;margin:auto;color:#1a1a2e">{body}<p style="color:#888;font-size:12px">Sent by the school office.</p></div>'


def page(body: str) -> str:
    return WRAP.format(body=body)


MailTemplate(
    "invoice_issued", category="finance", subject="Invoice {{ invoice.number }} for {{ student.first_name }}",
    html=page("<h2>Fees for {{ student.first_name }} {{ student.last_name }}</h2><p>Invoice <b>{{ invoice.number }}</b>: <b>{{ invoice.total }} {{ invoice.currency }}</b>, due {{ invoice.due_on }}.</p>"),
    text="Invoice {{ invoice.number }}: {{ invoice.total }} {{ invoice.currency }}, due {{ invoice.due_on }}.",
    variables=[variable("guardian", "The paying guardian"), variable("student", "The student"), variable("invoice", "The invoice")],
)
MailTemplate(
    "payment_receipt", category="finance", subject="Payment received: {{ payment.reference }}",
    html=page("<h2>Thank you</h2><p>We received <b>{{ payment.amount }}</b> against invoice {{ invoice.number }}. Balance: {{ invoice.balance }}.</p>"),
    text="We received {{ payment.amount }} against invoice {{ invoice.number }}. Balance: {{ invoice.balance }}.",
)
MailTemplate(
    "absence_notice", category="attendance", subject="{{ student.first_name }} was marked absent on {{ record.date }}",
    html=page("<p>{{ student.first_name }} {{ student.last_name }} was marked <b>absent</b> on {{ record.date }}.</p><p>Absences this term so far: {{ absences }}. Reply to this email if there is a reason we should know.</p>"),
    text="{{ student.first_name }} was marked absent on {{ record.date }}. Absences so far: {{ absences }}.",
)
MailTemplate(
    "leave_decision", category="attendance", subject="Leave request for {{ student.first_name }}: {{ request.status }}",
    html=page("<p>The request to excuse {{ student.first_name }} from {{ request.from_date }} to {{ request.to_date }} was <b>{{ request.status }}</b>.</p><p>{{ request.decision_note }}</p>"),
    text="Leave for {{ student.first_name }} ({{ request.from_date }} to {{ request.to_date }}): {{ request.status }}. {{ request.decision_note }}",
)
MailTemplate(
    "report_card_ready", category="academics", subject="{{ student.first_name }}'s report card is ready",
    html=page("<p>{{ student.first_name }}'s term report is now available in the parent portal. Average: <b>{{ card.average }}</b> ({{ card.letter }}), position {{ card.rank }} of {{ card.class_size }}.</p>"),
    text="{{ student.first_name }}'s report is ready. Average {{ card.average }} ({{ card.letter }}), position {{ card.rank }} of {{ card.class_size }}.",
)
MailTemplate(
    "overdue_book", category="library", subject="A library book is overdue",
    html=page("<p>{{ book.title }} was due on {{ loan.due_on }}. Please return it; a fine of {{ loan.fine }} applies per week.</p>"),
    text="{{ book.title }} was due on {{ loan.due_on }}. Please return it.",
)
MailTemplate(
    "application_received", category="admissions", subject="We received your application {{ reference }}",
    html=page("<h2>Thank you, {{ application.guardian_name }}</h2><p>We have your application for {{ application.first_name }} {{ application.last_name }}. Your reference is <b>{{ reference }}</b>.</p>"),
    text="We have your application for {{ application.first_name }}. Reference: {{ reference }}.",
)
MailTemplate(
    "application_decision", category="admissions", subject="About your application {{ application.reference }}",
    html=page("<p>Dear {{ application.guardian_name }}, our decision on the application for {{ application.first_name }} is: <b>{{ decision }}</b>.</p>"),
    text="Our decision on the application for {{ application.first_name }}: {{ decision }}.",
)
