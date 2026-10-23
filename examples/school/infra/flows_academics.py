"""Teaching flows: attendance, the timetable, grades and report cards."""

from infra.academics import terms, timetable_slots
from infra.assessment import assignments, grade_scale, grades, report_cards, submissions
from infra.attendance import attendance, attendance_stats
from infra.people import guardians, student_guardians, students

from pawabase_iac import Flow, P, blocks, ctx

# ── mark a class register ───────────────────────────────────────────────────
# POST /flows/v1/mark_attendance {section_id, date, period?, marks: [{student_id, status, reason?}]}. A second submission for the same
# day corrects the first (the unique index is on student, date and period, so the flow updates rather than inserts).
mark_attendance = Flow("mark_attendance", description="Mark a class register in one call", timeout=120)
m_start = mark_attendance.add(blocks.trigger.http(method="POST", policy="academic").named("start"))
m_valid = mark_attendance.add(
    blocks.validate.schema(
        value=ctx.input,
        fields=[
            {"name": "section_id", "type": "string", "required": True},
            {"name": "date", "type": "string", "required": True},
            {"name": "marks", "type": "array", "required": True},
            {"name": "period", "type": "integer"},
        ],
    ).named("valid")
)
m_term = mark_attendance.add(blocks.resource.list(resource=terms, filters={"current": True}, limit=1).named("term"))
m_each = mark_attendance.add(blocks.control.foreach(items=ctx.input.marks).named("each_mark"))
m_student = mark_attendance.add(blocks.resource.get(resource=students, id=ctx.item.student_id).named("student"))
m_skip = mark_attendance.add(blocks.control.noop().named("unknown_student"))
m_existing = mark_attendance.add(
    blocks.resource.list(
        resource=attendance,
        filters={"student_id": ctx.item.student_id, "date": ctx.input.date, "period": ctx.input.period.default(0)},
        limit=1,
    ).named("existing")
)
m_exists = mark_attendance.add(blocks.control.if_(P.steps.existing.output.total > 0).named("exists"))
m_update = mark_attendance.add(
    blocks.resource.update(
        resource=attendance,
        id=ctx.steps.existing.output.data[0].id,
        data={"status": ctx.item.status, "reason": ctx.item.reason, "marked_by": ctx.auth.user_id},
    ).named("correct")
)
m_create = mark_attendance.add(
    blocks.resource.create(
        resource=attendance,
        data={
            "student_id": ctx.item.student_id,
            "section_id": ctx.input.section_id,
            "term_id": ctx.steps.term.output.data[0].id,
            "date": ctx.input.date,
            "period": ctx.input.period.default(0),
            "status": ctx.item.status,
            "reason": ctx.item.reason,
            "marked_by": ctx.auth.user_id,
            "student_user_id": ctx.steps.student.output.user_id,
            "guardian_ids": ctx.steps.student.output.guardian_ids,
        },
    ).named("record")
)
m_tally = mark_attendance.add(blocks.transform.summarize(value=ctx.input.marks, operation="count", group_by="status").named("tally"))
m_announce = mark_attendance.add(
    blocks.event.emit(event="attendance.submitted", payload={"section_id": ctx.input.section_id, "date": ctx.input.date, "tally": ctx.steps.tally.output}).named("announce")
)
m_done = mark_attendance.add(blocks.response.return_(body={"marked": ctx.steps.each_mark.output.length(), "tally": ctx.steps.tally.output}).named("done"))
m_start >> m_valid >> m_term >> m_each
m_each.each >> m_student
m_student.missing >> m_skip
m_student >> m_existing >> m_exists
m_exists.true >> m_update
m_exists.false >> m_create
m_each.done >> m_tally >> m_announce >> m_done

# ── an absence is recorded ──────────────────────────────────────────────────
# Subscribed to attendance.created when the status is absent. Counts recent absences; the guardian hears at once, and from the third
# absence a concern is logged for staff.
absence_alert = Flow("absence_alert", description="Tell the guardian a student is absent; escalate repeated absences")
a_start = absence_alert.add(blocks.trigger.event(event="attendance.created").named("start"))
a_student = absence_alert.add(blocks.resource.get(resource=students, id=ctx.input.event.payload.record.student_id).named("student"))
a_recent = absence_alert.add(
    blocks.resource.list(
        resource=attendance, filters={"student_id": ctx.input.event.payload.record.student_id, "status": "absent"}, sort="-date", limit=10
    ).named("recent")
)
a_payer = absence_alert.add(
    blocks.resource.list(resource=student_guardians, filters={"student_id": ctx.input.event.payload.record.student_id, "is_primary": True}, limit=1).named("primary")
)
a_has = absence_alert.add(blocks.control.if_(P.steps.primary.output.total > 0).named("has_guardian"))
a_guardian = absence_alert.add(blocks.resource.get(resource=guardians, id=ctx.steps.primary.output.data[0].guardian_id).named("guardian"))
a_mail = absence_alert.add(
    blocks.mail.send(
        to=ctx.steps.guardian.output.email,
        template="absence_notice",
        data={"student": ctx.steps.student.output, "record": ctx.input.event.payload.record, "absences": ctx.steps.recent.output.total},
    ).named("notify")
)
a_mail_failed = absence_alert.add(blocks.log.write(message="absence email failed", level="warning", data=ctx.error).named("notify_failed"))
a_live = absence_alert.add(
    blocks.realtime.publish(
        channel="staff", event="absence", payload={"student_id": ctx.input.event.payload.record.student_id, "section_id": ctx.input.event.payload.record.section_id}
    ).named("tell_staff")
)
a_repeat = absence_alert.add(blocks.control.if_(P.steps.recent.output.total >= 3).named("repeated"))
a_concern = absence_alert.add(
    blocks.log.write(
        message=ctx.text("repeated absence: ", ctx.steps.student.output.first_name, " ", ctx.steps.student.output.last_name),
        level="warning",
        category="attendance",
        data={"absences": ctx.steps.recent.output.total},
    ).named("concern")
)
a_start >> a_student >> a_recent >> a_payer >> a_has
a_has.true >> a_guardian >> a_mail >> a_live
a_mail.error >> a_mail_failed >> a_live
a_has.false >> a_live
a_live >> a_repeat
a_repeat.true >> a_concern

# ── daily totals ────────────────────────────────────────────────────────────
daily_attendance_summary = Flow("daily_attendance_summary", description="Write each class's attendance totals for the day")
d_start = daily_attendance_summary.add(blocks.trigger.schedule(cron="0 15 * * 1-5").named("start"))
d_today = daily_attendance_summary.add(blocks.time.now(format="date").named("today"))
d_rows = daily_attendance_summary.add(blocks.resource.list(resource=attendance, filters={"date": ctx.steps.today.output}, limit=1000).named("rows"))
d_groups = daily_attendance_summary.add(blocks.transform.group(value=ctx.steps.rows.output.data, field="section_id").named("by_section"))
d_sections = daily_attendance_summary.add(blocks.control.foreach(items=ctx.steps.by_section.output.keys()).named("each_section"))
d_log = daily_attendance_summary.add(
    blocks.log.write(message=ctx.text("attendance totals for ", ctx.item), level="info", data={"date": ctx.steps.today.output}).named("note")
)
d_start >> d_today >> d_rows >> d_groups >> d_sections
d_sections.each >> d_log

# ── is this teacher free? ───────────────────────────────────────────────────
# POST /flows/v1/check_timetable_conflict {teacher_id, weekday, period}: 409 if the teacher already teaches then.
check_timetable_conflict = Flow("check_timetable_conflict", description="Is a teacher already teaching in that period?")
c_start = check_timetable_conflict.add(blocks.trigger.http(method="POST", policy="academic").named("start"))
c_slots = check_timetable_conflict.add(
    blocks.resource.list(
        resource=timetable_slots, filters={"teacher_id": ctx.input.teacher_id, "weekday": ctx.input.weekday, "period": ctx.input.period}, limit=1
    ).named("slots")
)
c_busy = check_timetable_conflict.add(blocks.control.if_(P.steps.slots.output.total > 0).named("busy"))
c_conflict = check_timetable_conflict.add(
    blocks.error.raise_(status=409, message="That teacher is already teaching in that period.", code="teacher_busy").named("conflict")
)
c_free = check_timetable_conflict.add(blocks.response.return_(body={"free": True}).named("free"))
c_start >> c_slots >> c_busy
c_busy.true >> c_conflict
c_busy.false >> c_free

# ── a grade is posted ───────────────────────────────────────────────────────
grade_posted = Flow("grade_posted", description="Complete a grade's percentage and letter, and flag low scores")
g_start = grade_posted.add(blocks.trigger.event(event="grades.created").named("start"))
g_ratio = grade_posted.add(
    blocks.math.calculate(operation="divide", values=[ctx.input.event.payload.record.score, ctx.input.event.payload.record.max_score]).named("ratio")
)
g_pct = grade_posted.add(blocks.math.calculate(operation="multiply", values=[ctx.steps.ratio.output, 100]).named("scaled"))
g_round = grade_posted.add(blocks.math.calculate(operation="round", values=[ctx.steps.scaled.output], digits=1).named("percentage"))
g_scale = grade_posted.add(blocks.resource.list(resource=grade_scale, limit=20).named("scale"))
g_band = grade_posted.add(
    blocks.transform.filter(
        value=ctx.steps.scale.output.data,
        condition=(P.item.min_percent <= P.steps.percentage.output) & (P.item.max_percent >= P.steps.percentage.output),
    ).named("band")
)
g_update = grade_posted.add(
    blocks.resource.update(
        resource=grades,
        id=ctx.input.event.payload.record.id,
        data={"percentage": ctx.steps.percentage.output, "letter": ctx.steps.band.output[0].letter},
    ).named("complete")
)
g_low = grade_posted.add(blocks.control.if_(P.steps.percentage.output < 40).named("low"))
g_flag = grade_posted.add(
    blocks.log.write(
        message="low score", level="warning", category="grades",
        data={"student_id": ctx.input.event.payload.record.student_id, "percentage": ctx.steps.percentage.output},
    ).named("flag")
)
g_live = grade_posted.add(
    blocks.realtime.publish(
        channel=ctx.text("student:", ctx.input.event.payload.record.student_id), event="grade",
        payload={"subject_id": ctx.input.event.payload.record.subject_id, "percentage": ctx.steps.percentage.output},
    ).named("tell_student")
)
g_start >> g_ratio >> g_pct >> g_round >> g_scale >> g_band >> g_update >> g_low
g_low.true >> g_flag >> g_live
g_low.false >> g_live

# ── report cards ────────────────────────────────────────────────────────────
# POST /flows/v1/compute_report_cards {term_id, section_id}. For each active student: group their grades by subject, average each, take
# the overall average, look up the letter, store the card. Then rank the class by average.
compute_report_cards = Flow("compute_report_cards", description="Build a term's report cards for a class and rank it", timeout=300)
rc_start = compute_report_cards.add(blocks.trigger.http(method="POST", policy="academic_leads").named("start"))
rc_valid = compute_report_cards.add(
    blocks.validate.schema(
        value=ctx.input, fields=[{"name": "term_id", "type": "string", "required": True}, {"name": "section_id", "type": "string", "required": True}]
    ).named("valid")
)
rc_pupils = compute_report_cards.add(
    blocks.resource.list(resource=students, filters={"section_id": ctx.input.section_id, "status": "active"}, limit=200).named("pupils")
)
rc_grades = compute_report_cards.add(
    blocks.resource.list(resource=grades, filters={"term_id": ctx.input.term_id, "section_id": ctx.input.section_id}, limit=1000).named("all_grades")
)
rc_scale = compute_report_cards.add(blocks.resource.list(resource=grade_scale, limit=20).named("scale"))
rc_each = compute_report_cards.add(blocks.control.foreach(items=ctx.steps.pupils.output.data).named("each_pupil"))
rc_mine = compute_report_cards.add(
    blocks.transform.filter(value=ctx.steps.all_grades.output.data, condition=P.item.student_id == P.vars.current_student).named("their_grades")
)
rc_bySubject = compute_report_cards.add(blocks.transform.group(value=ctx.steps.their_grades.output, field="subject_id").named("by_subject"))
rc_avg = compute_report_cards.add(blocks.transform.summarize(value=ctx.steps.their_grades.output, operation="average", field="percentage").named("average"))
rc_avg_round = compute_report_cards.add(blocks.math.calculate(operation="round", values=[ctx.steps.average.output], digits=1).named("overall"))
rc_band = compute_report_cards.add(
    blocks.transform.filter(
        value=ctx.steps.scale.output.data,
        condition=(P.item.min_percent <= P.steps.overall.output) & (P.item.max_percent >= P.steps.overall.output),
    ).named("band")
)
rc_card = compute_report_cards.add(
    blocks.resource.create(
        resource=report_cards,
        data={
            "student_id": ctx.item.id,
            "term_id": ctx.input.term_id,
            "section_id": ctx.input.section_id,
            "average": ctx.steps.overall.output,
            "letter": ctx.steps.band.output[0].letter,
            "class_size": ctx.steps.pupils.output.total,
            "subjects": ctx.steps.by_subject.output,
            "status": "draft",
            "published": False,
            "student_user_id": ctx.item.user_id,
            "guardian_ids": ctx.item.guardian_ids,
        },
    ).named("card")
)
rc_mark = compute_report_cards.add(blocks.control.set(values={"current_student": ctx.item.id}).named("remember_student"))
rc_cards = compute_report_cards.add(
    blocks.resource.list(resource=report_cards, filters={"term_id": ctx.input.term_id, "section_id": ctx.input.section_id}, sort="-average", limit=200).named("cards")
)
rc_rank_each = compute_report_cards.add(blocks.control.foreach(items=ctx.steps.cards.output.data).named("each_card"))
rc_rank_math = compute_report_cards.add(blocks.math.calculate(operation="add", values=[ctx.index, 1]).named("position"))
rc_rank = compute_report_cards.add(
    blocks.resource.update(resource=report_cards, id=ctx.item.id, data={"rank": ctx.steps.position.output}).named("set_rank")
)
rc_announce = compute_report_cards.add(
    blocks.event.emit(event="report_cards.computed", payload={"term_id": ctx.input.term_id, "section_id": ctx.input.section_id}).named("announce")
)
rc_done = compute_report_cards.add(
    blocks.response.return_(status=201, body={"cards": ctx.steps.each_card.output.length(), "term_id": ctx.input.term_id}).named("done")
)
rc_start >> rc_valid >> rc_pupils >> rc_grades >> rc_scale >> rc_each
rc_each.each >> rc_mark >> rc_mine >> rc_bySubject >> rc_avg >> rc_avg_round >> rc_band >> rc_card
rc_each.done >> rc_cards >> rc_rank_each
rc_rank_each.each >> rc_rank_math >> rc_rank
rc_rank_each.done >> rc_announce >> rc_done

# ── publish report cards ────────────────────────────────────────────────────
publish_report_cards = Flow("publish_report_cards", description="Make a class's approved report cards visible to families")
pub_start = publish_report_cards.add(blocks.trigger.http(method="POST", policy="management").named("start"))
pub_cards = publish_report_cards.add(
    blocks.resource.list(resource=report_cards, filters={"term_id": ctx.input.term_id, "section_id": ctx.input.section_id}, limit=200).named("cards")
)
pub_now = publish_report_cards.add(blocks.time.now().named("now"))
pub_each = publish_report_cards.add(blocks.control.foreach(items=ctx.steps.cards.output.data).named("each_card"))
pub_update = publish_report_cards.add(
    blocks.resource.update(
        resource=report_cards, id=ctx.item.id, data={"status": "published", "published": True, "published_at": ctx.steps.now.output}
    ).named("publish")
)
pub_event = publish_report_cards.add(
    blocks.event.emit(event="report_card.published", payload={"report_card_id": ctx.item.id, "student_id": ctx.item.student_id, "term_id": ctx.input.term_id}).named("announce")
)
pub_done = publish_report_cards.add(blocks.response.return_(body={"published": ctx.steps.each_card.output.length()}).named("done"))
pub_start >> pub_cards >> pub_now >> pub_each
pub_each.each >> pub_update >> pub_event
pub_each.done >> pub_done

# ── assignment reminders ────────────────────────────────────────────────────
assignment_reminders = Flow("assignment_reminders", description="Tell classes about assignments due in the next day")
r_start = assignment_reminders.add(blocks.trigger.schedule(cron="0 * * * *").named("start"))
r_now = assignment_reminders.add(blocks.time.now().named("now"))
r_soon = assignment_reminders.add(blocks.time.now(offset_seconds=86400).named("tomorrow"))
r_open = assignment_reminders.add(blocks.resource.list(resource=assignments, filters={"published": True, "due_soon_notified": False}, limit=200).named("open"))
r_due = assignment_reminders.add(
    blocks.transform.filter(
        value=ctx.steps.open.output.data,
        condition=(P.item.due_at > P.steps.now.output) & (P.item.due_at <= P.steps.tomorrow.output),
    ).named("due_soon")
)
r_each = assignment_reminders.add(blocks.control.foreach(items=ctx.steps.due_soon.output).named("each_due"))
r_live = assignment_reminders.add(
    blocks.realtime.publish(channel=ctx.text("section:", ctx.item.section_id), event="assignment.due_soon", payload={"assignment_id": ctx.item.id, "title": ctx.item.title, "due_at": ctx.item.due_at}).named("remind")
)
r_flag = assignment_reminders.add(blocks.resource.update(resource=assignments, id=ctx.item.id, data={"due_soon_notified": True}).named("mark_notified"))
r_start >> r_now >> r_soon >> r_open >> r_due >> r_each
r_each.each >> r_live >> r_flag
