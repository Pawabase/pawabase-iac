"""The shape of the school: years and terms, departments, classes, subjects, rooms and the timetable."""

from infra.policies import academic, management, staff

from pawabase_iac import Allow, BelongsTo, Boolean, Date, HasMany, Index, Integer, String, Table, read_only

academic_years = Table(
    "academic_years",
    description="A school year, e.g. 2026/2027. Exactly one is current.",
    fields=[
        String("name", required=True, unique=True, max_length=20),
        Date("starts_on", required=True),
        Date("ends_on", required=True),
        Boolean("current", default=False),
    ],
    operations={**read_only(staff), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
    relations=[HasMany("terms", "terms", "academic_year_id")],
    indexes=[Index("current")],
)

terms = Table(
    "terms",
    fields=[
        String("academic_year_id", required=True),
        String("name", required=True, max_length=40),
        Integer("number", required=True, minimum=1, maximum=4),
        Date("starts_on", required=True),
        Date("ends_on", required=True),
        Boolean("current", default=False),
        String("status", enum=["upcoming", "open", "closed", "published"], default="upcoming"),
    ],
    operations={**read_only("authenticated"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
    relations=[BelongsTo("academic_year", academic_years, "academic_year_id")],
    indexes=[Index("academic_year_id", "number", unique=True, name="uniq_term_number"), Index("current")],
)

departments = Table(
    "departments",
    fields=[
        String("name", required=True, unique=True, max_length=100),
        String("code", required=True, unique=True, max_length=10),
        String("head_teacher_id"),
        String("description", max_length=500),
    ],
    operations={**read_only("authenticated"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
)

grade_levels = Table(
    "grade_levels",
    description="A year group, e.g. Grade 7. next_level_id says where a student goes on promotion.",
    fields=[
        String("name", required=True, unique=True, max_length=40),
        String("code", required=True, unique=True, max_length=10),
        Integer("level", required=True, minimum=0, maximum=20),
        String("stage", enum=["nursery", "primary", "junior_secondary", "senior_secondary"], required=True),
        String("next_level_id"),
    ],
    operations={**read_only("authenticated"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
    indexes=[Index("level", unique=True, name="uniq_grade_level")],
)

rooms = Table(
    "rooms",
    fields=[
        String("name", required=True, unique=True, max_length=40),
        String("building", max_length=60),
        Integer("capacity", minimum=0, default=30),
        String("kind", enum=["classroom", "lab", "hall", "library", "field", "office"], default="classroom"),
    ],
    operations={**read_only(staff), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
)

sections = Table(
    "sections",
    description="A class group within a year group and school year, e.g. 7A in 2026/2027.",
    fields=[
        String("grade_level_id", required=True),
        String("academic_year_id", required=True),
        String("name", required=True, max_length=20),
        String("form_teacher_id"),
        String("room_id"),
        Integer("capacity", minimum=1, default=30),
        Integer("enrolled", minimum=0, default=0),
    ],
    operations={**read_only("authenticated"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
    relations=[BelongsTo("grade_level", grade_levels, "grade_level_id"), BelongsTo("academic_year", academic_years, "academic_year_id"),
               BelongsTo("room", rooms, "room_id")],
    indexes=[Index("academic_year_id", "grade_level_id", "name", unique=True, name="uniq_section")],
)

subjects = Table(
    "subjects",
    fields=[
        String("name", required=True, max_length=100),
        String("code", required=True, unique=True, max_length=12),
        String("department_id"),
        String("kind", enum=["core", "elective", "extracurricular"], default="core"),
        Integer("credit_hours", minimum=0, maximum=20, default=1),
    ],
    operations={**read_only("authenticated"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
    relations=[BelongsTo("department", departments, "department_id")],
)

curriculum = Table(
    "curriculum",
    description="Which subjects a year group studies, how often, and what a pass is.",
    fields=[
        String("grade_level_id", required=True),
        String("subject_id", required=True),
        Integer("weekly_periods", minimum=1, maximum=20, default=3),
        Boolean("mandatory", default=True),
        Integer("pass_mark", minimum=0, maximum=100, default=40),
    ],
    operations={**read_only("authenticated"), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
    relations=[BelongsTo("grade_level", grade_levels, "grade_level_id"), BelongsTo("subject", subjects, "subject_id")],
    indexes=[Index("grade_level_id", "subject_id", unique=True, name="uniq_curriculum_line")],
)

timetable_slots = Table(
    "timetable_slots",
    fields=[
        String("section_id", required=True),
        String("subject_id", required=True),
        String("teacher_id", required=True),
        String("room_id"),
        Integer("weekday", required=True, minimum=1, maximum=7),
        Integer("period", required=True, minimum=1, maximum=12),
        String("starts_at", pattern=r"^[0-2][0-9]:[0-5][0-9]$"),
        String("ends_at", pattern=r"^[0-2][0-9]:[0-5][0-9]$"),
    ],
    operations={**read_only("authenticated"), "create": Allow(academic), "update": Allow(academic), "delete": Allow(academic)},
    relations=[BelongsTo("section", sections, "section_id"), BelongsTo("subject", subjects, "subject_id")],
    indexes=[
        Index("section_id", "weekday", "period", unique=True, name="uniq_section_period"),
        Index("teacher_id", "weekday", "period", name="by_teacher_period"),
    ],
    realtime=True,
)
