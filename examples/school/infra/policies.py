"""Access rules. Read top to bottom: roles, then the groups that combine them, then rules about a particular row."""

from pawabase_iac import P, Policy

# ── groups of staff ─────────────────────────────────────────────────────────
management = Policy("management", P.role("admin") | P.role("principal"), description="Admin and principal.")
registry = Policy("registry", P.role("admin") | P.role("principal") | P.role("registrar"), description="Who keeps student records.")
academic = Policy(
    "academic",
    P.role("admin") | P.role("principal") | P.role("head_of_department") | P.role("teacher"),
    description="Anyone who teaches or leads teaching.",
)
academic_leads = Policy("academic_leads", P.role("admin") | P.role("principal") | P.role("head_of_department"))
finance_staff = Policy("finance_staff", P.role("admin") | P.role("principal") | P.role("accountant"))
library_staff = Policy("library_staff", P.role("admin") | P.role("librarian"))
health_staff = Policy("health_staff", P.role("admin") | P.role("principal") | P.role("nurse"))
transport_staff = Policy("transport_staff", P.role("admin") | P.role("transport_officer"))
staff = Policy(
    "staff",
    P.role("admin") | P.role("principal") | P.role("registrar") | P.role("head_of_department") | P.role("teacher")
    | P.role("accountant") | P.role("librarian") | P.role("nurse") | P.role("transport_officer"),
    description="Anyone who works at the school.",
)

# ── a row about a particular student ────────────────────────────────────────
# Rows about a student carry the student's own user id and their guardians' user ids (kept up to date by the enrolment flow),
# so one rule covers the student, their guardians and staff without joining tables.
family_of_record = Policy(
    "family_of_record",
    (P.record.student_user_id == P.auth.user_id) | P.record.guardian_ids.contains(P.auth.user_id),
    description="The student the row is about, or one of their guardians.",
)
staff_or_family = Policy("staff_or_family", staff.condition | family_of_record.condition)
academic_or_published_family = Policy(
    "academic_or_published_family",
    academic.condition | (family_of_record.condition & (P.record.published == True)),  # noqa: E712 (a policy expression, not a Python comparison)
    description="Teachers always; the family only once it is published.",
)
health_confidential = Policy(
    "health_confidential",
    health_staff.condition | (family_of_record.condition & (P.record.confidential == False)),  # noqa: E712
    description="Nurse and management always; guardians only for non-confidential entries.",
)

# ── a row that belongs to one person ────────────────────────────────────────
self_row = Policy("self_row", P.record.user_id == P.auth.user_id, description="The row is the signed-in person.")
staff_or_self = Policy("staff_or_self", staff.condition | self_row.condition)
registry_or_self = Policy("registry_or_self", registry.condition | self_row.condition)

# ── doing things ────────────────────────────────────────────────────────────
students_only = Policy("students_only", P.role("student"))
guardians_only = Policy("guardians_only", P.role("guardian"))
submitting_for_self = Policy(
    "submitting_for_self",
    P.role("student") & (P.input.student_user_id == P.auth.user_id),
    description="A student may only submit their own work.",
)
requesting_for_own_child = Policy(
    "requesting_for_own_child",
    P.role("guardian") & P.input.guardian_ids.contains(P.auth.user_id),
    description="A guardian may only file requests for their own children.",
)
verified_adult = Policy("verified_adult", P.authenticated() & P.auth.email_verified.truthy(), description="Signed in with a confirmed email.")

student_record = Policy(
    "student_record",
    staff.condition | (P.record.user_id == P.auth.user_id) | P.record.guardian_ids.contains(P.auth.user_id),
    description="The student's own row: staff, the student, or a guardian.",
)
