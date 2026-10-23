"""Enrolling students, linking guardian accounts and promoting a year group."""

from infra.academics import academic_years, sections
from infra.flows_finance import issue_term_invoice
from infra.people import enrollments, guardians, student_guardians, students

from pawabase_iac import Flow, P, blocks, ctx

#: Every table whose rows describe one student and carry guardian_ids (see common.family_fields).
FAMILY_TABLES = [
    "enrollments", "attendance", "grades", "report_cards", "leave_requests", "invoices", "payments", "scholarships", "health_records",
    "incidents", "transport_assignments", "submissions",
]

# ── enrol a student ─────────────────────────────────────────────────────────
# POST /flows/v1/enroll_student  (the registry only). Creates the student, finds or creates each guardian, links them, records the
# enrolment for the current year, counts the place in the class and queues the first invoice.
enroll_student = Flow("enroll_student", description="Enrol a student into a class with their guardians", timeout=120)

start = enroll_student.add(blocks.trigger.http(method="POST", policy="registry").named("start"))
valid = enroll_student.add(
    blocks.validate.schema(
        value=ctx.input,
        fields=[
            {"name": "first_name", "type": "string", "required": True},
            {"name": "last_name", "type": "string", "required": True},
            {"name": "date_of_birth", "type": "string", "required": True},
            {"name": "gender", "type": "string", "required": True},
            {"name": "section_id", "type": "string", "required": True},
            {"name": "guardians", "type": "array", "required": True},
            {"name": "middle_name", "type": "string"},
            {"name": "nationality", "type": "string"},
            {"name": "email", "type": "email"},
            {"name": "address", "type": "json"},
        ],
    ).named("valid")
)
section = enroll_student.add(blocks.resource.get(resource=sections, id=ctx.input.section_id).named("section"))
no_section = enroll_student.add(blocks.error.raise_(status=404, message="That class does not exist.", code="no_such_section").named("no_section"))
full = enroll_student.add(blocks.control.if_(P.steps.section.output.enrolled >= P.steps.section.output.capacity).named("is_full"))
class_full = enroll_student.add(blocks.error.raise_(status=409, message="That class is full.", code="class_full").named("class_full"))
year = enroll_student.add(blocks.resource.list(resource=academic_years, filters={"current": True}, limit=1).named("year"))
today = enroll_student.add(blocks.time.now(format="date").named("today"))
suffix = enroll_student.add(blocks.util.id(kind="token", length=6).named("suffix"))
student = enroll_student.add(
    blocks.resource.create(
        resource=students,
        data={
            "admission_number": ctx.text("ADM-", ctx.steps.suffix.output.upper()),
            "first_name": ctx.input.first_name,
            "middle_name": ctx.input.middle_name,
            "last_name": ctx.input.last_name,
            "date_of_birth": ctx.input.date_of_birth,
            "gender": ctx.input.gender,
            "nationality": ctx.input.nationality,
            "email": ctx.input.email,
            "address": ctx.input.address,
            "grade_level_id": ctx.steps.section.output.grade_level_id,
            "section_id": ctx.input.section_id,
            "enrolled_on": ctx.steps.today.output,
            "status": "active",
        },
    ).named("student")
)

# For every guardian: reuse the one with that email (a sibling may already be enrolled), otherwise create them; then link.
each_guardian = enroll_student.add(blocks.control.foreach(items=ctx.input.guardians).named("each_guardian"))
find_guardian = enroll_student.add(blocks.resource.list(resource=guardians, filters={"email": ctx.item.email}, limit=1).named("find_guardian"))
known = enroll_student.add(blocks.control.if_(P.steps.find_guardian.output.total > 0).named("known"))
reuse = enroll_student.add(
    blocks.control.set(values={"guardian_id": ctx.steps.find_guardian.output.data[0].id, "guardian_user_id": ctx.steps.find_guardian.output.data[0].user_id}).named("reuse")
)
new_guardian = enroll_student.add(
    blocks.resource.create(
        resource=guardians,
        data={
            "first_name": ctx.item.first_name,
            "last_name": ctx.item.last_name,
            "email": ctx.item.email,
            "phone": ctx.item.phone,
            "occupation": ctx.item.occupation,
            "address": ctx.input.address,
        },
    ).named("new_guardian")
)
remember = enroll_student.add(blocks.control.set(values={"guardian_id": ctx.steps.new_guardian.output.id, "guardian_user_id": None}).named("remember"))
link = enroll_student.add(
    blocks.resource.create(
        resource=student_guardians,
        data={
            "student_id": ctx.steps.student.output.id,
            "guardian_id": ctx.vars.guardian_id,
            "relationship": ctx.item.relationship,
            "is_primary": ctx.item.is_primary,
            "pays_fees": ctx.item.pays_fees,
        },
    ).named("link")
)
shape = enroll_student.add(
    blocks.transform.template(template={"guardian_id": ctx.vars.guardian_id, "user_id": ctx.vars.guardian_user_id, "link_id": ctx.steps.link.output.id}).named("shape")
)
user_ids = enroll_student.add(
    blocks.transform.summarize(value=ctx.steps.each_guardian.output, operation="collect", field="user_id").named("user_ids")
)
family = enroll_student.add(
    blocks.resource.update(resource=students, id=ctx.steps.student.output.id, data={"guardian_ids": ctx.steps.user_ids.output}).named("family")
)
enrolment = enroll_student.add(
    blocks.resource.create(
        resource=enrollments,
        data={
            "student_id": ctx.steps.student.output.id,
            "section_id": ctx.input.section_id,
            "academic_year_id": ctx.steps.year.output.data[0].id,
            "status": "enrolled",
            "enrolled_on": ctx.steps.today.output,
            "guardian_ids": ctx.steps.user_ids.output,
        },
    ).named("enrolment")
)
count = enroll_student.add(blocks.math.calculate(operation="add", values=[ctx.steps.section.output.enrolled, 1]).named("count"))
place = enroll_student.add(blocks.resource.update(resource=sections, id=ctx.input.section_id, data={"enrolled": ctx.steps.count.output}).named("place"))
announce = enroll_student.add(
    blocks.event.emit(event="student.enrolled", payload={"student_id": ctx.steps.student.output.id, "section_id": ctx.input.section_id}).named("announce")
)
invoice = enroll_student.add(
    blocks.queue.flow(flow=issue_term_invoice, input={"student_id": ctx.steps.student.output.id}).named("invoice_later")
)
done = enroll_student.add(
    blocks.response.return_(status=201, body={"student": ctx.steps.student.output, "guardians": ctx.steps.each_guardian.output}).named("done")
)

start >> valid >> section
section.missing >> no_section
section >> full
full.true >> class_full
full.false >> year >> today >> suffix >> student >> each_guardian
each_guardian.each >> find_guardian >> known
known.true >> reuse >> link
known.false >> new_guardian >> remember >> link
link >> shape
each_guardian.done >> user_ids >> family >> enrolment >> count >> place >> announce >> invoice >> done

# ── a guardian signs up ─────────────────────────────────────────────────────
# When an account is created, find the guardian with that email and give them the account; then copy the account onto each child's
# students row so the family policies recognise them. (Older rows keep working through the staff policies; new rows copy it.)
link_guardian_account = Flow("link_guardian_account", description="Attach a new account to the guardian with that email")
g_start = link_guardian_account.add(blocks.trigger.event(event="user.created").named("start"))
g_find = link_guardian_account.add(
    blocks.resource.list(resource=guardians, filters={"email": ctx.input.event.payload.email}, limit=1).named("find")
)
g_found = link_guardian_account.add(blocks.control.if_(P.steps.find.output.total > 0).named("found"))
g_set = link_guardian_account.add(
    blocks.resource.update(resource=guardians, id=ctx.steps.find.output.data[0].id, data={"user_id": ctx.input.event.payload.user_id}).named("set_account")
)
g_links = link_guardian_account.add(
    blocks.resource.list(resource=student_guardians, filters={"guardian_id": ctx.steps.find.output.data[0].id}, limit=100).named("links")
)
g_each = link_guardian_account.add(blocks.control.foreach(items=ctx.steps.links.output.data).named("each_child"))
g_child = link_guardian_account.add(blocks.resource.get(resource=students, id=ctx.item.student_id).named("child"))
g_flat = link_guardian_account.add(
    blocks.transform.flatten(value=[ctx.steps.child.output.guardian_ids.default([]), [ctx.input.event.payload.user_id]], depth=1).named("merge_ids")
)
g_unique = link_guardian_account.add(blocks.transform.unique(value=ctx.steps.merge_ids.output).named("unique"))
g_update = link_guardian_account.add(
    blocks.resource.update(resource=students, id=ctx.steps.child.output.id, data={"guardian_ids": ctx.steps.unique.output}).named("update_child")
)
# Rows written before the account existed carry no guardian id; copy it onto each of the child's rows in every table that has one.
g_remember = link_guardian_account.add(blocks.control.set(values={"child_id": ctx.steps.child.output.id}).named("remember_child"))
g_tables = link_guardian_account.add(
    blocks.control.foreach(items=FAMILY_TABLES).named("each_table")
)
g_which = link_guardian_account.add(blocks.control.set(values={"table": ctx.item}).named("remember_table"))
g_rows = link_guardian_account.add(
    blocks.resource.list(resource=ctx.vars.table, filters={"student_id": ctx.vars.child_id}, limit=500).named("rows")
)
g_each_row = link_guardian_account.add(blocks.control.foreach(items=ctx.steps.rows.output.data).named("each_row"))
g_stamp = link_guardian_account.add(
    blocks.resource.update(resource=ctx.vars.table, id=ctx.item.id, data={"guardian_ids": ctx.steps.unique.output}).named("stamp_row")
)
g_start >> g_find >> g_found
g_found.true >> g_set >> g_links >> g_each
g_each.each >> g_child >> g_flat >> g_unique >> g_update >> g_remember >> g_tables
g_tables.each >> g_which >> g_rows >> g_each_row
g_each_row.each >> g_stamp

# ── promote a year group ────────────────────────────────────────────────────
# POST /flows/v1/promote_students {from_section_id, to_section_id}: moves every active student of a class up one year, keeping history.
promote_students = Flow("promote_students", description="Move a class up to its next year group", timeout=300)
p_start = promote_students.add(blocks.trigger.http(method="POST", policy="management").named("start"))
p_valid = promote_students.add(
    blocks.validate.schema(
        value=ctx.input,
        fields=[{"name": "from_section_id", "type": "string", "required": True}, {"name": "to_section_id", "type": "string", "required": True}],
    ).named("valid")
)
p_to = promote_students.add(blocks.resource.get(resource=sections, id=ctx.input.to_section_id).named("to_section"))
p_missing = promote_students.add(blocks.error.raise_(status=404, message="The destination class does not exist.").named("no_destination"))
p_list = promote_students.add(
    blocks.resource.list(resource=students, filters={"section_id": ctx.input.from_section_id, "status": "active"}, limit=500).named("pupils")
)
p_each = promote_students.add(blocks.control.foreach(items=ctx.steps.pupils.output.data).named("each_pupil"))
p_move = promote_students.add(
    blocks.resource.update(
        resource=students,
        id=ctx.item.id,
        data={"section_id": ctx.input.to_section_id, "grade_level_id": ctx.steps.to_section.output.grade_level_id},
    ).named("move")
)
p_history = promote_students.add(
    blocks.resource.create(
        resource=enrollments,
        data={
            "student_id": ctx.item.id,
            "section_id": ctx.input.to_section_id,
            "academic_year_id": ctx.steps.to_section.output.academic_year_id,
            "status": "enrolled",
            "student_user_id": ctx.item.user_id,
            "guardian_ids": ctx.item.guardian_ids,
        },
    ).named("history")
)
p_done = promote_students.add(
    blocks.response.return_(body={"promoted": ctx.steps.each_pupil.output, "to_section_id": ctx.input.to_section_id}).named("done")
)
p_start >> p_valid >> p_to
p_to.missing >> p_missing
p_to >> p_list >> p_each
p_each.each >> p_move >> p_history
p_each.done >> p_done
