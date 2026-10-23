"""Money: issuing invoices, taking payments from the provider's notifications, and chasing what is late."""

from infra.academics import terms
from infra.finance import fee_structures, invoice_lines, invoices, payments, scholarships
from infra.people import student_guardians, students

from pawabase_iac import Flow, P, blocks, ctx

# ── issue one student's invoice for the current term ────────────────────────
# Queued by the enrolment flow, or run for a whole school by issue_term_invoices. Applies the student's scholarship, numbers the invoice,
# writes its lines, tells the paying guardian and announces it.
issue_term_invoice = Flow("issue_term_invoice", description="Invoice one student for the current term", timeout=120)
i_start = issue_term_invoice.add(blocks.trigger.manual().named("start"))
i_student = issue_term_invoice.add(blocks.resource.get(resource=students, id=ctx.input.student_id).named("student"))
i_no_student = issue_term_invoice.add(blocks.error.raise_(status=404, message="No such student.").named("no_student"))
i_term = issue_term_invoice.add(blocks.resource.list(resource=terms, filters={"current": True}, limit=1).named("term"))
i_have_term = issue_term_invoice.add(blocks.control.if_(P.steps.term.output.total > 0).named("have_term"))
i_no_term = issue_term_invoice.add(blocks.log.write(message="no current term, so no invoice was issued", level="warning").named("no_term"))
i_fees = issue_term_invoice.add(
    blocks.resource.list(
        resource=fee_structures,
        filters={"term_id": ctx.steps.term.output.data[0].id, "grade_level_id": ctx.steps.student.output.grade_level_id},
        limit=1,
    ).named("fees")
)
i_have_fees = issue_term_invoice.add(blocks.control.if_(P.steps.fees.output.total > 0).named("have_fees"))
i_no_fees = issue_term_invoice.add(
    blocks.log.write(message=ctx.text("no fee structure for student ", ctx.input.student_id), level="warning").named("no_fees")
)
i_subtotal = issue_term_invoice.add(
    blocks.transform.summarize(value=ctx.steps.fees.output.data[0].items, operation="sum", field="amount").named("subtotal")
)
i_awards = issue_term_invoice.add(
    blocks.resource.list(resource=scholarships, filters={"student_id": ctx.input.student_id, "active": True}, limit=1).named("awards")
)
i_has_award = issue_term_invoice.add(blocks.control.if_(P.steps.awards.output.total > 0).named("has_award"))
i_is_percent = issue_term_invoice.add(blocks.control.if_(P.steps.awards.output.data[0].kind == "percent").named("is_percent"))
i_percent = issue_term_invoice.add(
    blocks.math.calculate(operation="multiply", values=[ctx.steps.subtotal.output, ctx.steps.awards.output.data[0].value, 0.01]).named("percent_discount")
)
i_fixed = issue_term_invoice.add(blocks.control.set(values={"discount": ctx.steps.awards.output.data[0].value}).named("fixed_discount"))
i_set_percent = issue_term_invoice.add(blocks.control.set(values={"discount": ctx.steps.percent_discount.output}).named("set_percent"))
i_none = issue_term_invoice.add(blocks.control.set(values={"discount": 0}).named("no_discount"))
i_total = issue_term_invoice.add(blocks.math.calculate(operation="subtract", values=[ctx.steps.subtotal.output, ctx.vars.discount]).named("total"))
i_floor = issue_term_invoice.add(blocks.math.calculate(operation="max", values=[ctx.steps.total.output, 0]).named("floor"))
i_today = issue_term_invoice.add(blocks.time.now(format="date").named("today"))
i_due = issue_term_invoice.add(blocks.time.now(offset_seconds=30 * 86400, format="date").named("due"))
i_token = issue_term_invoice.add(blocks.util.id(kind="token", length=6).named("token"))
i_invoice = issue_term_invoice.add(
    blocks.resource.create(
        resource=invoices,
        data={
            "number": ctx.text("INV-", ctx.steps.token.output.upper()),
            "student_id": ctx.input.student_id,
            "term_id": ctx.steps.term.output.data[0].id,
            "issued_on": ctx.steps.today.output,
            "due_on": ctx.steps.due.output,
            "subtotal": ctx.steps.subtotal.output,
            "discount": ctx.vars.discount,
            "total": ctx.steps.floor.output,
            "amount_paid": 0,
            "balance": ctx.steps.floor.output,
            "currency": ctx.steps.fees.output.data[0].currency,
            "status": "issued",
            "student_user_id": ctx.steps.student.output.user_id,
            "guardian_ids": ctx.steps.student.output.guardian_ids,
        },
    ).named("invoice")
)
i_each_line = issue_term_invoice.add(blocks.control.foreach(items=ctx.steps.fees.output.data[0].items).named("each_line"))
i_line = issue_term_invoice.add(
    blocks.resource.create(
        resource=invoice_lines,
        data={"invoice_id": ctx.steps.invoice.output.id, "description": ctx.item.name, "amount": ctx.item.amount, "quantity": 1},
    ).named("line")
)
i_payer = issue_term_invoice.add(
    blocks.resource.list(resource=student_guardians, filters={"student_id": ctx.input.student_id, "pays_fees": True}, limit=1).named("payer")
)
i_has_payer = issue_term_invoice.add(blocks.control.if_(P.steps.payer.output.total > 0).named("has_payer"))
i_guardian = issue_term_invoice.add(blocks.resource.get(resource="guardians", id=ctx.steps.payer.output.data[0].guardian_id).named("guardian"))
i_mail = issue_term_invoice.add(
    blocks.mail.send(
        to=ctx.steps.guardian.output.email,
        template="invoice_issued",
        data={"guardian": ctx.steps.guardian.output, "student": ctx.steps.student.output, "invoice": ctx.steps.invoice.output},
    ).named("mail_guardian")
)
i_mail_failed = issue_term_invoice.add(blocks.log.write(message="could not email the invoice", level="warning", data=ctx.error).named("mail_failed"))
i_announce = issue_term_invoice.add(
    blocks.event.emit(event="invoice.issued", payload={"invoice_id": ctx.steps.invoice.output.id, "student_id": ctx.input.student_id}).named("announce")
)
i_done = issue_term_invoice.add(blocks.response.return_(status=201, body=ctx.steps.invoice.output).named("done"))

i_start >> i_student
i_student.missing >> i_no_student
i_student >> i_term >> i_have_term
i_have_term.false >> i_no_term
i_have_term.true >> i_fees >> i_have_fees
i_have_fees.false >> i_no_fees
i_have_fees.true >> i_subtotal >> i_awards >> i_has_award
i_has_award.false >> i_none
i_has_award.true >> i_is_percent
i_is_percent.true >> i_percent >> i_set_percent
i_is_percent.false >> i_fixed
for chosen in (i_set_percent, i_fixed, i_none):
    chosen >> i_total
i_total >> i_floor >> i_today >> i_due >> i_token >> i_invoice >> i_each_line
i_each_line.each >> i_line
i_each_line.done >> i_payer >> i_has_payer
i_has_payer.true >> i_guardian >> i_mail >> i_announce
i_mail.error >> i_mail_failed >> i_announce
i_has_payer.false >> i_announce
i_announce >> i_done

# ── invoice everyone for the term ───────────────────────────────────────────
issue_term_invoices = Flow("issue_term_invoices", description="Queue an invoice for every active student")
b_start = issue_term_invoices.add(blocks.trigger.http(method="POST", policy="finance_staff").named("start"))
b_list = issue_term_invoices.add(blocks.resource.list(resource=students, filters={"status": "active"}, limit=500).named("pupils"))
b_each = issue_term_invoices.add(blocks.control.foreach(items=ctx.steps.pupils.output.data).named("each_pupil"))
b_queue = issue_term_invoices.add(blocks.queue.flow(flow=issue_term_invoice, input={"student_id": ctx.item.id}).named("queue_invoice"))
b_done = issue_term_invoices.add(blocks.response.return_(status=202, body={"queued": ctx.steps.each_pupil.output}).named("done"))
b_start >> b_list >> b_each
b_each.each >> b_queue
b_each.done >> b_done

# ── a payment arrives ───────────────────────────────────────────────────────
# The payment provider posts to /hooks/v1/payments (signed). The reference is unique, so a retried notification cannot pay twice.
record_payment = Flow("record_payment", description="Apply a confirmed payment to its invoice")
r_start = record_payment.add(blocks.trigger.webhook(hook="payments").named("start"))
r_ok = record_payment.add(blocks.control.if_(P.input.body.status == "success").named("successful"))
r_ignored = record_payment.add(blocks.log.write(message=ctx.text("ignored payment notification ", ctx.input.body.reference), level="info").named("ignored"))
r_find = record_payment.add(blocks.resource.list(resource=invoices, filters={"number": ctx.input.body.invoice}, limit=1).named("find_invoice"))
r_found = record_payment.add(blocks.control.if_(P.steps.find_invoice.output.total > 0).named("found"))
r_unknown = record_payment.add(blocks.log.write(message=ctx.text("payment for unknown invoice ", ctx.input.body.invoice), level="warning").named("unknown_invoice"))
r_now = record_payment.add(blocks.time.now().named("now"))
r_pay = record_payment.add(
    blocks.resource.create(
        resource=payments,
        data={
            "invoice_id": ctx.steps.find_invoice.output.data[0].id,
            "student_id": ctx.steps.find_invoice.output.data[0].student_id,
            "amount": ctx.input.body.amount,
            "method": ctx.input.body.method.default("transfer"),
            "reference": ctx.input.body.reference,
            "paid_at": ctx.steps.now.output,
            "status": "confirmed",
            "provider_payload": ctx.input.body,
            "student_user_id": ctx.steps.find_invoice.output.data[0].student_user_id,
            "guardian_ids": ctx.steps.find_invoice.output.data[0].guardian_ids,
        },
    ).named("payment")
)
r_duplicate = record_payment.add(blocks.log.write(message=ctx.text("duplicate payment reference ", ctx.input.body.reference), level="info").named("duplicate"))
r_paid = record_payment.add(
    blocks.math.calculate(operation="add", values=[ctx.steps.find_invoice.output.data[0].amount_paid, ctx.input.body.amount]).named("paid_so_far")
)
r_balance = record_payment.add(
    blocks.math.calculate(operation="subtract", values=[ctx.steps.find_invoice.output.data[0].total, ctx.steps.paid_so_far.output]).named("balance")
)
r_settled = record_payment.add(blocks.control.if_(P.steps.balance.output <= 0).named("settled"))
r_full = record_payment.add(
    blocks.resource.update(
        resource=invoices,
        id=ctx.steps.find_invoice.output.data[0].id,
        data={"amount_paid": ctx.steps.paid_so_far.output, "balance": 0, "status": "paid"},
    ).named("mark_paid")
)
r_part = record_payment.add(
    blocks.resource.update(
        resource=invoices,
        id=ctx.steps.find_invoice.output.data[0].id,
        data={"amount_paid": ctx.steps.paid_so_far.output, "balance": ctx.steps.balance.output, "status": "partial"},
    ).named("mark_partial")
)
r_has_email = record_payment.add(blocks.control.if_(P.input.body.email.exists()).named("has_email"))
r_receipt = record_payment.add(
    blocks.mail.send(
        to=ctx.input.body.email,
        template="payment_receipt",
        data={"payment": ctx.steps.payment.output, "invoice": ctx.steps.find_invoice.output.data[0]},
    ).named("receipt")
)
r_receipt_failed = record_payment.add(blocks.log.write(message="receipt email failed", level="warning", data=ctx.error).named("receipt_failed"))
r_event = record_payment.add(
    blocks.event.emit(
        event="payment.received",
        payload={"payment_id": ctx.steps.payment.output.id, "invoice_id": ctx.steps.find_invoice.output.data[0].id, "amount": ctx.input.body.amount},
    ).named("announce")
)
r_start >> r_ok
r_ok.false >> r_ignored
r_ok.true >> r_find >> r_found
r_found.false >> r_unknown
r_found.true >> r_now >> r_pay
r_pay.error >> r_duplicate
r_pay >> r_paid >> r_balance >> r_settled
r_settled.true >> r_full >> r_event
r_settled.false >> r_part >> r_event
r_event >> r_has_email
r_has_email.true >> r_receipt
r_receipt.error >> r_receipt_failed

# ── chase what is late ──────────────────────────────────────────────────────
# Every night: invoices past their due date that are not paid get a late fee, move to overdue, and the guardian is told.
late_fee_sweep = Flow("late_fee_sweep", description="Add a late fee to unpaid invoices past their due date")
l_start = late_fee_sweep.add(blocks.trigger.schedule(cron="0 2 * * *").named("start"))
l_today = late_fee_sweep.add(blocks.time.now(format="date").named("today"))
l_issued = late_fee_sweep.add(blocks.resource.list(resource=invoices, filters={"status": "issued"}, limit=500).named("issued"))
l_partial = late_fee_sweep.add(blocks.resource.list(resource=invoices, filters={"status": "partial"}, limit=500).named("partial"))
l_all = late_fee_sweep.add(blocks.transform.flatten(value=[ctx.steps.issued.output.data, ctx.steps.partial.output.data], depth=1).named("open"))
l_late = late_fee_sweep.add(blocks.transform.filter(value=ctx.steps.open.output, condition=P.item.due_on < P.steps.today.output).named("late"))
l_each = late_fee_sweep.add(blocks.control.foreach(items=ctx.steps.late.output).named("each_late"))
l_fee = late_fee_sweep.add(blocks.math.calculate(operation="multiply", values=[ctx.item.balance, 0.05]).named("fee"))
l_total = late_fee_sweep.add(blocks.math.calculate(operation="add", values=[ctx.item.total, ctx.steps.fee.output]).named("new_total"))
l_balance = late_fee_sweep.add(blocks.math.calculate(operation="add", values=[ctx.item.balance, ctx.steps.fee.output]).named("new_balance"))
l_update = late_fee_sweep.add(
    blocks.resource.update(
        resource=invoices,
        id=ctx.item.id,
        data={"status": "overdue", "late_fee": ctx.steps.fee.output, "total": ctx.steps.new_total.output, "balance": ctx.steps.new_balance.output},
    ).named("mark_overdue")
)
l_announce = late_fee_sweep.add(blocks.event.emit(event="invoice.overdue", payload={"invoice_id": ctx.item.id, "student_id": ctx.item.student_id}).named("announce"))
l_done = late_fee_sweep.add(blocks.log.write(message=ctx.text("late fees added to ", ctx.steps.each_late.output.length(), " invoices"), level="info").named("summary"))
l_start >> l_today >> l_issued >> l_partial >> l_all >> l_late >> l_each
l_each.each >> l_fee >> l_total >> l_balance >> l_update >> l_announce
l_each.done >> l_done
