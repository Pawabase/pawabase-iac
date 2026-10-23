"""Who was in school, who is away, and the daily totals."""

from infra.academics import sections, terms
from infra.common import family_fields
from infra.people import students
from infra.policies import academic, management, requesting_for_own_child, staff, staff_or_family

from pawabase_iac import Allow, Array, BelongsTo, Date, DateTime, Desc, Index, Integer, Number, String, Table, read_only

attendance = Table(
    "attendance",
    description="One row per student per day (period 0) or per lesson. Marked in bulk by mark_attendance.",
    fields=[
        String("student_id", required=True),
        String("section_id", required=True),
        String("term_id"),
        Date("date", required=True),
        Integer("period", minimum=0, maximum=12, default=0),
        String("status", enum=["present", "absent", "late", "excused"], required=True),
        String("reason", max_length=300),
        String("marked_by"),
        *family_fields,
    ],
    operations={
        "list": Allow(staff_or_family),
        "get": Allow(staff_or_family),
        "create": Allow(academic),
        "update": Allow(academic),
        "delete": Allow(management),
    },
    relations=[BelongsTo("student", students, "student_id"), BelongsTo("section", sections, "section_id")],
    indexes=[
        Index("student_id", "date", "period", unique=True, name="uniq_attendance"),
        Index("section_id", "date"),
        Index("student_user_id", Desc("date")),
    ],
    realtime=True,
)

attendance_stats = Table(
    "attendance_stats",
    description="Daily totals per class, written by the nightly summary.",
    fields=[
        Date("date", required=True),
        String("section_id", required=True),
        Integer("present", minimum=0, default=0),
        Integer("absent", minimum=0, default=0),
        Integer("late", minimum=0, default=0),
        Integer("excused", minimum=0, default=0),
        Number("rate", minimum=0, maximum=100),
    ],
    operations={**read_only(staff)},
    indexes=[Index("date", "section_id", unique=True, name="uniq_stat_day")],
)

leave_requests = Table(
    "leave_requests",
    description="A guardian asks for a student to be excused. Staff approve or reject; the guardian is told.",
    fields=[
        String("student_id", required=True),
        String("requested_by", required=True, description="The guardian's user id"),
        Date("from_date", required=True),
        Date("to_date", required=True),
        String("reason", required=True, max_length=500),
        String("status", enum=["pending", "approved", "rejected"], default="pending"),
        String("decided_by"),
        DateTime("decided_at"),
        String("decision_note", max_length=300),
        *family_fields,
    ],
    operations={
        "list": Allow(staff_or_family),
        "get": Allow(staff_or_family),
        "create": Allow(requesting_for_own_child),
        "update": Allow(academic),
        "delete": Allow(management),
    },
    relations=[BelongsTo("student", students, "student_id")],
    indexes=[Index("student_id", "status"), Index("status", "from_date")],
    realtime=True,
)
