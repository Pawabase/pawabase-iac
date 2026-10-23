"""Life around lessons: the library, buses, the sick bay, discipline, announcements, the calendar and messages."""

from infra.academics import grade_levels, sections
from infra.common import family_fields, public_announcement
from infra.people import students
from infra.policies import (
    academic, health_confidential, health_staff, library_staff, management, staff, staff_or_family, transport_staff,
)

from pawabase_iac import (
    Allow, Array, BelongsTo, Boolean, Date, DateTime, Desc, HasMany, Index, Integer, Number, String, Table, Text, Where, read_only,
)

# ── library ─────────────────────────────────────────────────────────────────
books = Table(
    "books",
    fields=[
        String("isbn", unique=True, max_length=20),
        String("title", required=True, max_length=250),
        String("author", required=True, max_length=150),
        String("category", max_length=60),
        Integer("copies", minimum=0, default=1),
        Integer("available", minimum=0, default=1),
        String("shelf", max_length=20),
        String("cover_key", description="Object key in the library-covers bucket"),
    ],
    operations={**read_only("authenticated"), "create": Allow(library_staff), "update": Allow(library_staff), "delete": Allow(library_staff)},
    indexes=[Index("title"), Index("author"), Index("category", "available")],
    cache_ttl=30,
)

loans = Table(
    "loans",
    fields=[
        String("book_id", required=True),
        String("borrower_user_id", required=True),
        String("borrower_kind", enum=["student", "teacher"], default="student"),
        String("borrower_name", max_length=160),
        Date("borrowed_on", required=True),
        Date("due_on", required=True),
        Date("returned_on"),
        Number("fine", minimum=0, default=0),
        String("status", enum=["out", "returned", "overdue", "lost"], default="out"),
    ],
    operations={"list": Allow(library_staff), "get": Allow(library_staff), "create": Allow(library_staff), "update": Allow(library_staff),
                "delete": Allow(management)},
    relations=[BelongsTo("book", books, "book_id")],
    indexes=[Index("borrower_user_id", "status"), Index("status", "due_on", where=[Where("returned_on", "is_null")], name="open_loans_by_due")],
)

# ── transport ───────────────────────────────────────────────────────────────
transport_routes = Table(
    "transport_routes",
    fields=[
        String("name", required=True, unique=True, max_length=80),
        String("vehicle_plate", max_length=20),
        String("driver_name", max_length=100),
        String("driver_phone", max_length=20),
        Integer("capacity", minimum=1, default=40),
        String("morning_departure", pattern=r"^[0-2][0-9]:[0-5][0-9]$"),
        String("afternoon_departure", pattern=r"^[0-2][0-9]:[0-5][0-9]$"),
    ],
    operations={**read_only("authenticated"), "create": Allow(transport_staff), "update": Allow(transport_staff), "delete": Allow(transport_staff)},
    relations=[HasMany("stops", "transport_stops", "route_id")],
)

transport_stops = Table(
    "transport_stops",
    fields=[
        String("route_id", required=True),
        String("name", required=True, max_length=100),
        Integer("sequence", required=True, minimum=1),
        String("pickup_time", pattern=r"^[0-2][0-9]:[0-5][0-9]$"),
    ],
    operations={**read_only("authenticated"), "create": Allow(transport_staff), "update": Allow(transport_staff), "delete": Allow(transport_staff)},
    relations=[BelongsTo("route", transport_routes, "route_id")],
    indexes=[Index("route_id", "sequence", unique=True, name="uniq_stop_order")],
)

transport_assignments = Table(
    "transport_assignments",
    fields=[
        String("student_id", required=True),
        String("route_id", required=True),
        String("stop_id", required=True),
        String("direction", enum=["both", "morning", "afternoon"], default="both"),
        Boolean("active", default=True),
        *family_fields,
    ],
    operations={"list": Allow(staff_or_family), "get": Allow(staff_or_family), "create": Allow(transport_staff),
                "update": Allow(transport_staff), "delete": Allow(transport_staff)},
    relations=[BelongsTo("student", students, "student_id"), BelongsTo("route", transport_routes, "route_id")],
    indexes=[Index("student_id", unique=True, where=[Where("active", "=", True)], name="one_active_route")],
)

# ── health and discipline ───────────────────────────────────────────────────
health_records = Table(
    "health_records",
    description="Sick bay entries. Guardians see non-confidential ones; confidential ones stay with the nurse and management.",
    fields=[
        String("student_id", required=True),
        String("kind", enum=["checkup", "illness", "injury", "vaccination", "allergy", "medication"], required=True),
        Text("description", required=True),
        Date("recorded_on", required=True),
        String("recorded_by"),
        Date("follow_up_on"),
        Boolean("confidential", default=False),
        *family_fields,
    ],
    operations={"list": Allow(health_confidential), "get": Allow(health_confidential), "create": Allow(health_staff), "update": Allow(health_staff),
                "delete": Allow(management)},
    relations=[BelongsTo("student", students, "student_id")],
    indexes=[Index("student_id", Desc("recorded_on")), Index("follow_up_on", where=[Where("follow_up_on", "not_null")], name="due_follow_ups")],
)

incidents = Table(
    "incidents",
    fields=[
        String("student_id", required=True),
        String("reported_by", required=True),
        Date("occurred_on", required=True),
        String("severity", enum=["minor", "moderate", "serious"], default="minor"),
        String("category", enum=["conduct", "bullying", "property", "safety", "academic_honesty", "other"], default="conduct"),
        Text("description", required=True),
        Text("action_taken"),
        Boolean("guardian_notified", default=False),
        String("status", enum=["open", "resolved"], default="open"),
        *family_fields,
    ],
    operations={"list": Allow(staff_or_family), "get": Allow(staff_or_family), "create": Allow(academic), "update": Allow(academic),
                "delete": Allow(management)},
    relations=[BelongsTo("student", students, "student_id")],
    indexes=[Index("student_id", Desc("occurred_on")), Index("severity", "status")],
)

# ── communication ───────────────────────────────────────────────────────────
announcements = Table(
    "announcements",
    fields=[
        String("title", required=True, max_length=200),
        Text("body", required=True),
        String("audience", enum=["all", "staff", "students", "guardians", "section", "grade_level"], default="all"),
        String("section_id"),
        String("grade_level_id"),
        DateTime("publish_at"),
        DateTime("expires_at"),
        Boolean("pinned", default=False),
        String("author_id"),
    ],
    operations={**read_only("authenticated"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
    transformer=public_announcement,
    relations=[BelongsTo("section", sections, "section_id"), BelongsTo("grade_level", grade_levels, "grade_level_id")],
    indexes=[Index("audience", Desc("publish_at")), Index("pinned")],
    realtime=True,
    cache_ttl=15,
)

calendar_events = Table(
    "calendar_events",
    fields=[
        String("title", required=True, max_length=200),
        String("kind", enum=["holiday", "exam", "meeting", "sports", "trip", "assembly", "other"], default="other"),
        Date("starts_on", required=True),
        Date("ends_on"),
        String("audience", enum=["all", "staff", "students", "guardians"], default="all"),
        String("location", max_length=120),
        Text("description"),
    ],
    operations={**read_only("public"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
    indexes=[Index("starts_on"), Index("kind", "starts_on")],
    cache_ttl=120,
)

messages = Table(
    "messages",
    description="Direct messages between staff and guardians. Each person sees only what they sent or received.",
    fields=[
        String("thread_id", required=True, indexed=True),
        String("sender_user_id", required=True),
        String("recipient_user_id", required=True),
        Text("body", required=True),
        DateTime("read_at"),
        Array("attachments", of=String("key")),
    ],
    operations={
        "list": Allow("authenticated"),
        "get": Allow("authenticated"),
        "create": Allow("authenticated"),
        "update": Allow("authenticated"),
    },
    owner_field="sender_user_id",
    indexes=[Index("recipient_user_id", Desc("created_at")), Index("thread_id", "created_at")],
    realtime=True,
)
