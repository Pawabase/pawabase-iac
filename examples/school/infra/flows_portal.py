"""What families and students see: their own pages, assembled from several tables."""

from infra.assessment import report_cards
from infra.attendance import attendance
from infra.finance import invoices
from infra.people import guardians, student_guardians, students

from pawabase_iac import Flow, P, blocks, ctx

# GET /rest/v1/parent/dashboard: the signed-in guardian's children with their latest attendance, open invoices and published report cards.
parent_dashboard = Flow("parent_dashboard", description="Everything a guardian needs on one screen")
d_start = parent_dashboard.add(blocks.trigger.http(method="GET", path="/parent/dashboard", policy="guardians_only").named("start"))
d_me = parent_dashboard.add(blocks.resource.list(resource=guardians, filters={"user_id": ctx.auth.user_id}, limit=1).named("me"))
d_known = parent_dashboard.add(blocks.control.if_(P.steps.me.output.total > 0).named("known"))
d_unknown = parent_dashboard.add(blocks.error.raise_(status=404, message="No guardian record is linked to this account.", code="not_a_guardian").named("unknown"))
d_links = parent_dashboard.add(
    blocks.resource.list(resource=student_guardians, filters={"guardian_id": ctx.steps.me.output.data[0].id}, limit=50).named("links")
)
d_each = parent_dashboard.add(blocks.control.foreach(items=ctx.steps.links.output.data).named("each_child"))
d_child = parent_dashboard.add(blocks.resource.get(resource=students, id=ctx.item.student_id).named("child"))
d_att = parent_dashboard.add(
    blocks.resource.list(resource=attendance, filters={"student_id": ctx.item.student_id}, sort="-date", limit=5).named("latest_attendance")
)
d_open = parent_dashboard.add(
    blocks.resource.list(resource=invoices, filters={"student_id": ctx.item.student_id, "status": "issued"}, limit=10).named("open_invoices")
)
d_overdue = parent_dashboard.add(
    blocks.resource.list(resource=invoices, filters={"student_id": ctx.item.student_id, "status": "overdue"}, limit=10).named("overdue_invoices")
)
d_cards = parent_dashboard.add(
    blocks.resource.list(resource=report_cards, filters={"student_id": ctx.item.student_id, "published": True}, sort="-created_at", limit=3).named("report_cards")
)
d_shape = parent_dashboard.add(
    blocks.transform.template(
        template={
            "student": {
                "id": ctx.steps.child.output.id,
                "name": ctx.steps.child.output.first_name,
                "surname": ctx.steps.child.output.last_name,
                "admission_number": ctx.steps.child.output.admission_number,
                "section_id": ctx.steps.child.output.section_id,
            },
            "attendance": ctx.steps.latest_attendance.output.data,
            "invoices_due": ctx.steps.open_invoices.output.total,
            "invoices_overdue": ctx.steps.overdue_invoices.output.total,
            "report_cards": ctx.steps.report_cards.output.data,
        }
    ).named("shape")
)
d_done = parent_dashboard.add(blocks.response.return_(body={"children": ctx.steps.each_child.output}).named("done"))
d_start >> d_me >> d_known
d_known.false >> d_unknown
d_known.true >> d_links >> d_each
d_each.each >> d_child >> d_att >> d_open >> d_overdue >> d_cards >> d_shape
d_each.done >> d_done

# GET /rest/v1/students/{id}/transcript: published report cards for one student. The route policy lets staff and guardians in; the flow
# checks the guardian really is linked to this student.
student_transcript = Flow("student_transcript", description="A student's published report cards")
s_start = student_transcript.add(blocks.trigger.http(method="GET", path="/students/{id}/transcript", policy="authenticated").named("start"))
s_student = student_transcript.add(blocks.resource.get(resource=students, id=ctx.input.params.id).named("student"))
s_missing = student_transcript.add(blocks.error.raise_(status=404, message="No such student.").named("no_student"))
s_allowed = student_transcript.add(
    blocks.policy.check(policy="student_record", record=ctx.steps.student.output).named("allowed")
)
s_denied = student_transcript.add(blocks.error.raise_(status=403, message="You may not see this student's transcript.", code="forbidden").named("denied"))
s_cards = student_transcript.add(
    blocks.resource.list(resource=report_cards, filters={"student_id": ctx.input.params.id, "published": True}, sort="-created_at", limit=20).named("cards")
)
s_done = student_transcript.add(blocks.response.return_(body={"student": ctx.steps.student.output, "report_cards": ctx.steps.cards.output.data}).named("done"))
s_start >> s_student
s_student.missing >> s_missing
s_student >> s_allowed
s_allowed.denied >> s_denied
s_allowed.allowed >> s_cards >> s_done
