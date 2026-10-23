"""Library, leave, announcements and admissions."""

from infra.admissions import admission_applications
from infra.attendance import leave_requests
from infra.campus import announcements, books, loans
from infra.people import guardians, student_guardians, students

from pawabase_iac import Flow, P, blocks, ctx

# ── borrow a book ───────────────────────────────────────────────────────────
borrow_book = Flow("borrow_book", description="Lend a book for fourteen days")
b_start = borrow_book.add(blocks.trigger.http(method="POST", policy="library_staff").named("start"))
b_valid = borrow_book.add(
    blocks.validate.schema(
        value=ctx.input,
        fields=[
            {"name": "book_id", "type": "string", "required": True},
            {"name": "borrower_user_id", "type": "string", "required": True},
            {"name": "borrower_kind", "type": "string"},
            {"name": "borrower_name", "type": "string"},
        ],
    ).named("valid")
)
b_book = borrow_book.add(blocks.resource.get(resource=books, id=ctx.input.book_id).named("book"))
b_missing = borrow_book.add(blocks.error.raise_(status=404, message="No such book.").named("no_book"))
b_out = borrow_book.add(blocks.control.if_(P.steps.book.output.available < 1).named("none_left"))
b_unavailable = borrow_book.add(blocks.error.raise_(status=409, message="Every copy is out.", code="none_available").named("unavailable"))
b_today = borrow_book.add(blocks.time.now(format="date").named("today"))
b_due = borrow_book.add(blocks.time.now(offset_seconds=14 * 86400, format="date").named("due"))
b_loan = borrow_book.add(
    blocks.resource.create(
        resource=loans,
        data={
            "book_id": ctx.input.book_id,
            "borrower_user_id": ctx.input.borrower_user_id,
            "borrower_kind": ctx.input.borrower_kind.default("student"),
            "borrower_name": ctx.input.borrower_name,
            "borrowed_on": ctx.steps.today.output,
            "due_on": ctx.steps.due.output,
            "status": "out",
        },
    ).named("loan")
)
b_left = borrow_book.add(blocks.math.calculate(operation="subtract", values=[ctx.steps.book.output.available, 1]).named("remaining"))
b_shelf = borrow_book.add(blocks.resource.update(resource=books, id=ctx.input.book_id, data={"available": ctx.steps.remaining.output}).named("take_from_shelf"))
b_done = borrow_book.add(blocks.response.return_(status=201, body=ctx.steps.loan.output).named("done"))
b_start >> b_valid >> b_book
b_book.missing >> b_missing
b_book >> b_out
b_out.true >> b_unavailable
b_out.false >> b_today >> b_due >> b_loan >> b_left >> b_shelf >> b_done

# ── return a book ───────────────────────────────────────────────────────────
return_book = Flow("return_book", description="Take a book back and charge a fine if it was late")
t_start = return_book.add(blocks.trigger.http(method="POST", policy="library_staff").named("start"))
t_loan = return_book.add(blocks.resource.get(resource=loans, id=ctx.input.loan_id).named("loan"))
t_missing = return_book.add(blocks.error.raise_(status=404, message="No such loan.").named("no_loan"))
t_open = return_book.add(blocks.control.if_(P.steps.loan.output.returned_on.exists()).named("already_back"))
t_already = return_book.add(blocks.error.raise_(status=409, message="That book is already back.", code="already_returned").named("already"))
t_today = return_book.add(blocks.time.now(format="date").named("today"))
t_late = return_book.add(blocks.control.if_(P.steps.loan.output.due_on < P.steps.today.output).named("late"))
t_fine = return_book.add(blocks.control.set(values={"fine": 50}).named("fine_late"))
t_nofine = return_book.add(blocks.control.set(values={"fine": 0}).named("fine_none"))
t_update = return_book.add(
    blocks.resource.update(resource=loans, id=ctx.input.loan_id, data={"returned_on": ctx.steps.today.output, "status": "returned", "fine": ctx.vars.fine}).named("close_loan")
)
t_book = return_book.add(blocks.resource.get(resource=books, id=ctx.steps.loan.output.book_id).named("book"))
t_plus = return_book.add(blocks.math.calculate(operation="add", values=[ctx.steps.book.output.available, 1]).named("back_on_shelf"))
t_shelf = return_book.add(blocks.resource.update(resource=books, id=ctx.steps.loan.output.book_id, data={"available": ctx.steps.back_on_shelf.output}).named("shelve"))
t_done = return_book.add(blocks.response.return_(body={"fine": ctx.vars.fine, "loan": ctx.steps.close_loan.output}).named("done"))
t_start >> t_loan
t_loan.missing >> t_missing
t_loan >> t_open
t_open.true >> t_already
t_open.false >> t_today >> t_late
t_late.true >> t_fine >> t_update
t_late.false >> t_nofine >> t_update
t_update >> t_book >> t_plus >> t_shelf >> t_done

# ── overdue books ───────────────────────────────────────────────────────────
overdue_loans_sweep = Flow("overdue_loans_sweep", description="Mark books past their due date as overdue")
o_start = overdue_loans_sweep.add(blocks.trigger.schedule(cron="0 6 * * *").named("start"))
o_today = overdue_loans_sweep.add(blocks.time.now(format="date").named("today"))
o_out = overdue_loans_sweep.add(blocks.resource.list(resource=loans, filters={"status": "out"}, limit=500).named("out"))
o_late = overdue_loans_sweep.add(blocks.transform.filter(value=ctx.steps.out.output.data, condition=P.item.due_on < P.steps.today.output).named("late"))
o_each = overdue_loans_sweep.add(blocks.control.foreach(items=ctx.steps.late.output).named("each_late"))
o_mark = overdue_loans_sweep.add(blocks.resource.update(resource=loans, id=ctx.item.id, data={"status": "overdue"}).named("mark_overdue"))
o_event = overdue_loans_sweep.add(blocks.event.emit(event="loan.overdue", payload={"loan_id": ctx.item.id, "borrower_user_id": ctx.item.borrower_user_id}).named("announce"))
o_user = overdue_loans_sweep.add(blocks.auth.lookup(user_id=ctx.item.borrower_user_id).named("borrower"))
o_book = overdue_loans_sweep.add(blocks.resource.get(resource=books, id=ctx.item.book_id).named("book"))
o_mail = overdue_loans_sweep.add(
    blocks.mail.send(to=ctx.steps.borrower.output.email, template="overdue_book", data={"book": ctx.steps.book.output, "loan": ctx.item}).named("remind")
)
o_failed = overdue_loans_sweep.add(blocks.log.write(message="overdue reminder failed", level="warning", data=ctx.error).named("remind_failed"))
o_start >> o_today >> o_out >> o_late >> o_each
o_each.each >> o_mark >> o_event >> o_user
o_user.missing >> blocks.control.noop().named("no_account")
o_user >> o_book >> o_mail
o_mail.error >> o_failed

# ── a leave request is decided ──────────────────────────────────────────────
leave_decided = Flow("leave_decided", description="Excuse the days and tell the guardian when a leave request is approved or rejected")
v_start = leave_decided.add(blocks.trigger.event(event="leave_requests.updated").named("start"))
v_changed = leave_decided.add(blocks.control.if_(P.input.event.payload.record.status != "pending").named("decided"))
v_student = leave_decided.add(blocks.resource.get(resource=students, id=ctx.input.event.payload.record.student_id).named("student"))
v_guardian = leave_decided.add(blocks.resource.list(resource=guardians, filters={"user_id": ctx.input.event.payload.record.requested_by}, limit=1).named("guardian"))
v_has = leave_decided.add(blocks.control.if_(P.steps.guardian.output.total > 0).named("has_guardian"))
v_mail = leave_decided.add(
    blocks.mail.send(
        to=ctx.steps.guardian.output.data[0].email,
        template="leave_decision",
        data={"student": ctx.steps.student.output, "request": ctx.input.event.payload.record},
    ).named("notify")
)
v_failed = leave_decided.add(blocks.log.write(message="leave decision email failed", level="warning", data=ctx.error).named("notify_failed"))
v_start >> v_changed
v_changed.true >> v_student >> v_guardian >> v_has
v_has.true >> v_mail
v_mail.error >> v_failed

# ── announcements ───────────────────────────────────────────────────────────
announcement_fanout = Flow("announcement_fanout", description="Push a new announcement to the right people in real time and to the SMS gateway")
n_start = announcement_fanout.add(blocks.trigger.event(event="announcements.created").named("start"))
n_audience = announcement_fanout.add(blocks.control.switch(value=ctx.input.event.payload.record.audience, cases=["all", "staff", "students", "guardians", "section", "grade_level"]).named("audience"))
n_all = announcement_fanout.add(blocks.realtime.publish(channel="announcements", event="announcement", payload=ctx.input.event.payload.record).named("to_everyone"))
n_staff = announcement_fanout.add(blocks.realtime.publish(channel="staff", event="announcement", payload=ctx.input.event.payload.record).named("to_staff"))
n_section = announcement_fanout.add(
    blocks.realtime.publish(channel=ctx.text("section:", ctx.input.event.payload.record.section_id), event="announcement", payload=ctx.input.event.payload.record).named("to_section")
)
n_grade = announcement_fanout.add(
    blocks.realtime.publish(channel=ctx.text("grade:", ctx.input.event.payload.record.grade_level_id), event="announcement", payload=ctx.input.event.payload.record).named("to_grade")
)
n_sms = announcement_fanout.add(blocks.webhook.send(event="announcement.sms", payload={"title": ctx.input.event.payload.record.title}).named("sms_gateway"))
n_start >> n_audience
n_audience.on("all") >> n_all
n_audience.on("students") >> n_all
n_audience.on("staff") >> n_staff
n_audience.on("section") >> n_section
n_audience.on("grade_level") >> n_grade
n_audience.on("guardians") >> n_sms
n_audience.on("default") >> n_all

# ── admissions ──────────────────────────────────────────────────────────────
# POST /rest/v1/admissions/apply is public (rate limited); it only writes a row. Everything after that is automatic.
screen_application = Flow("screen_application", description="Reference, first score and acknowledgement for a new application")
s_start = screen_application.add(blocks.trigger.event(event="admission_applications.created").named("start"))
s_token = screen_application.add(blocks.util.id(kind="token", length=8).named("token"))
s_docs = screen_application.add(
    blocks.math.calculate(operation="min", values=[ctx.input.event.payload.record.documents.length(), 3]).named("documents")
)
s_score = screen_application.add(blocks.math.calculate(operation="multiply", values=[ctx.steps.documents.output, 20]).named("score"))
s_update = screen_application.add(
    blocks.resource.update(
        resource=admission_applications,
        id=ctx.input.event.payload.record.id,
        data={
            "reference": ctx.text("APP-", ctx.steps.token.output.upper()),
            "score": ctx.steps.score.output,
            "status": "screening",
            "screening": {"documents": ctx.steps.documents.output, "rule": "20 points per document, up to three"},
        },
    ).named("screen")
)
s_mail = screen_application.add(
    blocks.mail.send(
        to=ctx.input.event.payload.record.guardian_email,
        template="application_received",
        data={"application": ctx.steps.screen.output, "reference": ctx.text("APP-", ctx.steps.token.output.upper())},
    ).named("acknowledge")
)
s_failed = screen_application.add(blocks.log.write(message="application acknowledgement failed", level="warning", data=ctx.error).named("acknowledge_failed"))
s_start >> s_token >> s_docs >> s_score >> s_update >> s_mail
s_mail.error >> s_failed

# POST /flows/v1/decide_application {application_id, decision: accepted | waitlisted | rejected, notes?}
decide_application = Flow("decide_application", description="Record the registry's decision and tell the family")
x_start = decide_application.add(blocks.trigger.http(method="POST", policy="registry").named("start"))
x_valid = decide_application.add(
    blocks.validate.schema(
        value=ctx.input,
        fields=[
            {"name": "application_id", "type": "string", "required": True},
            {"name": "decision", "type": "string", "required": True},
            {"name": "notes", "type": "string"},
        ],
    ).named("valid")
)
x_app = decide_application.add(blocks.resource.get(resource=admission_applications, id=ctx.input.application_id).named("application"))
x_missing = decide_application.add(blocks.error.raise_(status=404, message="No such application.").named("no_application"))
x_now = decide_application.add(blocks.time.now().named("now"))
x_choice = decide_application.add(blocks.control.switch(value=ctx.input.decision, cases=["accepted", "waitlisted", "rejected"]).named("choice"))
x_bad = decide_application.add(blocks.error.raise_(status=422, message="decision is accepted, waitlisted or rejected.", code="bad_decision").named("bad_decision"))
x_accept = decide_application.add(
    blocks.resource.update(
        resource=admission_applications, id=ctx.input.application_id,
        data={"status": "accepted", "decided_at": ctx.steps.now.output, "decided_by": ctx.auth.user_id, "notes": ctx.input.notes},
    ).named("accept")
)
x_wait = decide_application.add(
    blocks.resource.update(
        resource=admission_applications, id=ctx.input.application_id,
        data={"status": "waitlisted", "decided_at": ctx.steps.now.output, "decided_by": ctx.auth.user_id, "notes": ctx.input.notes},
    ).named("waitlist")
)
x_reject = decide_application.add(
    blocks.resource.update(
        resource=admission_applications, id=ctx.input.application_id,
        data={"status": "rejected", "decided_at": ctx.steps.now.output, "decided_by": ctx.auth.user_id, "notes": ctx.input.notes},
    ).named("reject")
)
x_mail = decide_application.add(
    blocks.mail.send(
        to=ctx.steps.application.output.guardian_email,
        template="application_decision",
        data={"application": ctx.steps.application.output, "decision": ctx.input.decision},
    ).named("tell_family")
)
x_failed = decide_application.add(blocks.log.write(message="decision email failed", level="warning", data=ctx.error).named("tell_failed"))
x_done = decide_application.add(blocks.response.return_(body={"application_id": ctx.input.application_id, "decision": ctx.input.decision}).named("done"))
x_start >> x_valid >> x_app
x_app.missing >> x_missing
x_app >> x_now >> x_choice
x_choice.on("accepted") >> x_accept >> x_mail
x_choice.on("waitlisted") >> x_wait >> x_mail
x_choice.on("rejected") >> x_reject >> x_mail
x_choice.on("default") >> x_bad
x_mail >> x_done
x_mail.error >> x_failed >> x_done

# ── a report card is published ──────────────────────────────────────────────
notify_report_card = Flow("notify_report_card", description="Email the primary guardian when a report card is published")
q_start = notify_report_card.add(blocks.trigger.event(event="report_card.published").named("start"))
q_card = notify_report_card.add(blocks.resource.get(resource="report_cards", id=ctx.input.event.payload.report_card_id).named("card"))
q_student = notify_report_card.add(blocks.resource.get(resource=students, id=ctx.input.event.payload.student_id).named("student"))
q_primary = notify_report_card.add(
    blocks.resource.list(resource=student_guardians, filters={"student_id": ctx.input.event.payload.student_id, "is_primary": True}, limit=1).named("primary")
)
q_has = notify_report_card.add(blocks.control.if_(P.steps.primary.output.total > 0).named("has_guardian"))
q_guardian = notify_report_card.add(blocks.resource.get(resource=guardians, id=ctx.steps.primary.output.data[0].guardian_id).named("guardian"))
q_mail = notify_report_card.add(
    blocks.mail.send(
        to=ctx.steps.guardian.output.email, template="report_card_ready",
        data={"student": ctx.steps.student.output, "card": ctx.steps.card.output},
    ).named("notify")
)
q_failed = notify_report_card.add(blocks.log.write(message="report card email failed", level="warning", data=ctx.error).named("notify_failed"))
q_live = notify_report_card.add(
    blocks.realtime.publish(channel=ctx.text("student:", ctx.input.event.payload.student_id), event="report_card", payload={"term_id": ctx.input.event.payload.term_id}).named("tell_student")
)
q_start >> q_card >> q_student >> q_primary >> q_has
q_has.true >> q_guardian >> q_mail >> q_live
q_mail.error >> q_failed >> q_live
q_has.false >> q_live
