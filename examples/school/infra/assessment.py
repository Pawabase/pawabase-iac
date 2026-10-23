"""Teaching and learning: assessments, grades, report cards, assignments, submissions and lesson plans."""

from infra.academics import sections, subjects, terms
from infra.common import family_fields
from infra.people import students, teachers
from infra.policies import academic, academic_leads, academic_or_published_family, management, staff, staff_or_family, submitting_for_self

from pawabase_iac import (
    Allow, Array, BelongsTo, Boolean, DateTime, Date, Desc, Index, Integer, JSON, Number, RateLimit, String, Table, Text, Where, read_only,
)

assessment_types = Table(
    "assessment_types",
    fields=[
        String("code", required=True, unique=True, max_length=20),
        String("name", required=True, max_length=60),
        Number("weight", required=True, minimum=0, maximum=100, description="Percent of the term mark"),
    ],
    operations={**read_only("authenticated"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
)

grade_scale = Table(
    "grade_scale",
    description="Percentage bands and the letter and points each earns.",
    fields=[
        String("letter", required=True, unique=True, max_length=3),
        Number("min_percent", required=True, minimum=0, maximum=100),
        Number("max_percent", required=True, minimum=0, maximum=100),
        Number("points", minimum=0, maximum=5),
        String("descriptor", max_length=60),
    ],
    operations={**read_only("authenticated"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
)

assessments = Table(
    "assessments",
    fields=[
        String("term_id", required=True),
        String("section_id", required=True),
        String("subject_id", required=True),
        String("teacher_id", required=True),
        String("assessment_type_id", required=True),
        String("title", required=True, max_length=200),
        Number("max_score", required=True, minimum=1),
        Date("held_on"),
        String("status", enum=["draft", "open", "graded", "published"], default="draft"),
    ],
    operations={**read_only(staff), "create": Allow(academic), "update": Allow(academic), "delete": Allow(academic_leads)},
    relations=[BelongsTo("term", terms, "term_id"), BelongsTo("section", sections, "section_id"), BelongsTo("subject", subjects, "subject_id")],
    indexes=[Index("term_id", "section_id", "subject_id"), Index("teacher_id", "status")],
)

grades = Table(
    "grades",
    description="A student's score on one assessment. Families see it once it is published.",
    fields=[
        String("assessment_id", required=True),
        String("student_id", required=True),
        String("term_id", required=True),
        String("section_id", required=True),
        String("subject_id", required=True),
        Number("score", required=True, minimum=0),
        Number("max_score", required=True, minimum=1),
        Number("percentage", minimum=0, maximum=100),
        String("letter", max_length=3),
        String("remarks", max_length=500),
        String("recorded_by"),
        Boolean("published", default=False),
        *family_fields,
    ],
    operations={
        "list": Allow(academic_or_published_family),
        "get": Allow(academic_or_published_family),
        "create": Allow(academic),
        "update": Allow(academic),
        "delete": Allow(academic_leads),
    },
    relations=[BelongsTo("assessment", assessments, "assessment_id"), BelongsTo("student", students, "student_id")],
    indexes=[
        Index("assessment_id", "student_id", unique=True, name="uniq_grade"),
        Index("student_id", "term_id"),
        Index("term_id", "section_id", "subject_id"),
        Index("student_user_id", Desc("created_at"), where=[Where("published", "=", True)], name="published_by_student"),
    ],
    rate_limit=RateLimit(300, 60),
    realtime=True,
)

report_cards = Table(
    "report_cards",
    description="A student's term report: marks per subject, average, class rank, attendance and remarks. Built by compute_report_cards.",
    fields=[
        String("student_id", required=True),
        String("term_id", required=True),
        String("section_id", required=True),
        Number("average", minimum=0, maximum=100),
        String("letter", max_length=3),
        Integer("rank", minimum=1),
        Integer("class_size", minimum=0),
        Number("attendance_rate", minimum=0, maximum=100),
        JSON("subjects", description="[{subject_id, subject, average, letter, grades}]"),
        String("teacher_remarks", max_length=1000),
        String("principal_remarks", max_length=1000),
        String("status", enum=["draft", "approved", "published"], default="draft"),
        DateTime("published_at"),
        String("file_key", description="The PDF in the report-cards bucket"),
        Boolean("published", default=False),
        *family_fields,
    ],
    operations={
        "list": Allow(academic_or_published_family),
        "get": Allow(academic_or_published_family),
        "update": Allow(academic_leads),
        "delete": Allow(management),
    },
    relations=[BelongsTo("student", students, "student_id"), BelongsTo("term", terms, "term_id")],
    indexes=[Index("student_id", "term_id", unique=True, name="uniq_report_card"), Index("term_id", "section_id", "rank")],
)

assignments = Table(
    "assignments",
    fields=[
        String("section_id", required=True),
        String("subject_id", required=True),
        String("teacher_id", required=True),
        String("title", required=True, max_length=200),
        Text("instructions"),
        DateTime("due_at", required=True),
        Number("max_score", minimum=1, default=100),
        Array("attachments", of=String("key")),
        Boolean("published", default=False),
        Boolean("due_soon_notified", default=False),
    ],
    operations={"list": Allow("authenticated"), "get": Allow("authenticated"), "create": Allow(academic), "update": Allow(academic),
                "delete": Allow(academic)},
    relations=[BelongsTo("section", sections, "section_id"), BelongsTo("subject", subjects, "subject_id")],
    indexes=[Index("section_id", Desc("due_at")), Index("teacher_id", "published")],
    realtime=True,
)

submissions = Table(
    "submissions",
    fields=[
        String("assignment_id", required=True),
        String("student_id", required=True),
        DateTime("submitted_at"),
        Text("answer"),
        Array("file_keys", of=String("key")),
        Number("score", minimum=0),
        Text("feedback"),
        String("status", enum=["submitted", "late", "graded", "returned"], default="submitted"),
        *family_fields,
    ],
    operations={
        "list": Allow(staff_or_family),
        "get": Allow(staff_or_family),
        "create": Allow(submitting_for_self),
        "update": Allow(academic),
        "delete": Allow(academic_leads),
    },
    relations=[BelongsTo("assignment", assignments, "assignment_id"), BelongsTo("student", students, "student_id")],
    indexes=[Index("assignment_id", "student_id", unique=True, name="uniq_submission"), Index("student_id", Desc("submitted_at"))],
)

lesson_plans = Table(
    "lesson_plans",
    fields=[
        String("teacher_id", required=True),
        String("subject_id", required=True),
        String("grade_level_id", required=True),
        String("term_id", required=True),
        Integer("week", required=True, minimum=1, maximum=20),
        String("topic", required=True, max_length=200),
        Text("objectives"),
        Array("resources", of=String("resource")),
        String("status", enum=["draft", "submitted", "approved", "rejected"], default="draft"),
        String("reviewed_by"),
        Text("review_notes"),
    ],
    operations={**read_only(academic), "create": Allow(academic), "update": Allow(academic), "delete": Allow(academic_leads)},
    relations=[BelongsTo("teacher", teachers, "teacher_id"), BelongsTo("subject", subjects, "subject_id")],
    indexes=[Index("teacher_id", "term_id", "week"), Index("status")],
)
