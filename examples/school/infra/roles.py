"""Who works at, studies at or has a child at the school, and what each kind of person may do.

Permissions are names; a policy decides what each one unlocks (see policies.py). Giving a role to a person is done in Accounts.
"""

from pawabase_iac import Role

Role("admin", description="System administrator", permissions=[
    "school.manage", "settings.manage", "students.manage", "staff.manage", "finance.manage", "finance.read", "grades.approve",
    "grades.write", "attendance.write", "reports.read", "announcements.write", "library.manage", "health.manage", "transport.manage",
    "admissions.review",
])  # fmt: skip
Role("principal", description="Head of school", permissions=[
    "school.manage", "students.manage", "staff.manage", "finance.read", "grades.approve", "reports.read", "announcements.write",
    "admissions.review",
])  # fmt: skip
Role("registrar", description="Admissions and student records", permissions=["students.manage", "admissions.review", "reports.read"])
Role("head_of_department", description="Leads a department", permissions=[
    "grades.write", "grades.approve", "attendance.write", "assignments.write", "lessons.approve", "lessons.write", "students.read",
])  # fmt: skip
Role("teacher", description="Teaching staff", permissions=[
    "grades.write", "attendance.write", "assignments.write", "lessons.write", "incidents.write", "students.read",
])  # fmt: skip
Role("accountant", description="Fees and payments", permissions=["finance.manage", "finance.read", "payments.record"])
Role("librarian", description="Runs the library", permissions=["library.manage", "students.read"])
Role("nurse", description="School nurse", permissions=["health.manage", "students.read"])
Role("transport_officer", description="Buses and routes", permissions=["transport.manage", "students.read"])
Role("student", description="A pupil", permissions=["self.read", "assignments.submit", "library.borrow"])
Role("guardian", description="A parent or guardian", permissions=["children.read", "payments.make", "leave.request"])
