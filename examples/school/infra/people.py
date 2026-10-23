"""Students, their guardians, teachers and staff, and the links between them."""

from infra.academics import academic_years, grade_levels, sections
from infra.common import address, family_fields
from infra.policies import academic, management, registry, registry_or_self, staff, staff_or_self, student_record

from pawabase_iac import Allow, Array, BelongsTo, Boolean, Date, Email, HasMany, Index, Integer, Ref, String, Table, read_only

students = Table(
    "students",
    description="Every pupil. Created by the enrolment flow, which also links guardians and copies ids onto the rows that describe them.",
    fields=[
        String("user_id", unique=True, description="The student's account, when they have one"),
        String("admission_number", required=True, unique=True, max_length=20),
        String("first_name", required=True, max_length=80),
        String("middle_name", max_length=80),
        String("last_name", required=True, max_length=80),
        Date("date_of_birth", required=True),
        String("gender", enum=["female", "male", "other"], required=True),
        String("nationality", max_length=60),
        Email("email"),
        String("grade_level_id"),
        String("section_id"),
        String("status", enum=["applicant", "active", "suspended", "graduated", "withdrawn", "transferred"], default="active"),
        Date("enrolled_on"),
        Ref("address", schema=address),
        String("photo_key", description="Object key in the student-photos bucket"),
        Array("guardian_ids", of=String("guardian_id"), description="The guardians' user ids"),
    ],
    operations={
        "list": Allow(student_record),
        "get": Allow(student_record),
        "create": Allow(registry),
        "update": Allow(registry),
        "delete": Allow(management),
    },
    relations=[
        BelongsTo("grade_level", grade_levels, "grade_level_id"),
        BelongsTo("section", sections, "section_id"),
        HasMany("guardians", "student_guardians", "student_id"),
    ],
    indexes=[Index("section_id", "status"), Index("last_name", "first_name"), Index("grade_level_id", "status")],
    realtime=True,
)

guardians = Table(
    "guardians",
    fields=[
        String("user_id", unique=True),
        String("first_name", required=True, max_length=80),
        String("last_name", required=True, max_length=80),
        Email("email", required=True),
        String("phone", pattern=r"^\+?[0-9 ()-]{7,20}$"),
        String("occupation", max_length=100),
        String("preferred_channel", enum=["email", "sms"], default="email"),
        Ref("address", schema=address),
    ],
    operations={
        "list": Allow(registry_or_self),
        "get": Allow(registry_or_self),
        "create": Allow(registry),
        "update": Allow(registry_or_self),
        "delete": Allow(management),
    },
    indexes=[Index("email"), Index("last_name")],
)

student_guardians = Table(
    "student_guardians",
    description="Which guardians a student has, and what each is for.",
    fields=[
        String("student_id", required=True),
        String("guardian_id", required=True),
        String("relationship", enum=["mother", "father", "guardian", "grandparent", "sibling", "other"], default="guardian"),
        Boolean("is_primary", default=False),
        Boolean("pays_fees", default=False),
        Boolean("emergency_contact", default=True),
    ],
    operations={"list": Allow(staff), "get": Allow(staff), "create": Allow(registry), "update": Allow(registry), "delete": Allow(registry)},
    relations=[BelongsTo("student", students, "student_id"), BelongsTo("guardian", guardians, "guardian_id")],
    indexes=[Index("student_id", "guardian_id", unique=True, name="uniq_student_guardian"), Index("guardian_id")],
)

teachers = Table(
    "teachers",
    fields=[
        String("user_id", unique=True),
        String("staff_number", required=True, unique=True, max_length=20),
        String("first_name", required=True, max_length=80),
        String("last_name", required=True, max_length=80),
        Email("email", required=True),
        String("phone", max_length=20),
        String("department_id"),
        String("qualification", max_length=200),
        Date("hired_on"),
        String("status", enum=["active", "on_leave", "resigned"], default="active"),
        Integer("max_weekly_periods", minimum=1, maximum=60, default=30),
    ],
    operations={
        "list": Allow(staff),
        "get": Allow(staff),
        "create": Allow(management),
        "update": Allow(management),
        "delete": Allow(management),
    },
    indexes=[Index("department_id", "status")],
)

teacher_subjects = Table(
    "teacher_subjects",
    description="What each teacher is qualified to teach, and for which year groups.",
    fields=[String("teacher_id", required=True), String("subject_id", required=True), String("grade_level_id")],
    operations={**read_only(staff), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
    relations=[BelongsTo("teacher", teachers, "teacher_id")],
    indexes=[Index("teacher_id", "subject_id", "grade_level_id", unique=True, name="uniq_teacher_subject")],
)

staff_members = Table(
    "staff_members",
    description="Non-teaching staff: office, library, health, transport, kitchen, security.",
    fields=[
        String("user_id", unique=True),
        String("staff_number", required=True, unique=True, max_length=20),
        String("first_name", required=True, max_length=80),
        String("last_name", required=True, max_length=80),
        Email("email"),
        String("title", max_length=100),
        String("section", enum=["office", "library", "health", "transport", "kitchen", "security", "maintenance"], default="office"),
        Date("hired_on"),
        String("status", enum=["active", "on_leave", "resigned"], default="active"),
    ],
    operations={**read_only(staff_or_self), "create": Allow(management), "update": Allow(management), "delete": Allow(management)},
)

enrollments = Table(
    "enrollments",
    description="A student's place in a class for a school year. One row per year, so history is kept.",
    fields=[
        String("student_id", required=True),
        String("section_id", required=True),
        String("academic_year_id", required=True),
        String("status", enum=["enrolled", "promoted", "repeated", "withdrawn", "graduated"], default="enrolled"),
        Date("enrolled_on"),
        Date("left_on"),
        *family_fields,
    ],
    operations={"list": Allow(academic), "get": Allow(academic), "create": Allow(registry), "update": Allow(registry), "delete": Allow(management)},
    relations=[
        BelongsTo("student", students, "student_id"),
        BelongsTo("section", sections, "section_id"),
        BelongsTo("academic_year", academic_years, "academic_year_id"),
    ],
    indexes=[Index("student_id", "academic_year_id", unique=True, name="uniq_enrollment_year"), Index("section_id", "status")],
)
