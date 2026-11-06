"""Pieces several tables share."""

from pawabase_iac import Array, Schema, String

#: Rows about a student carry who the student is and who their guardians are, so one policy can answer "is this yours?".
family_fields = [
    String("student_user_id", indexed=True, description="The student's user id (copied from the student)"),
    Array("guardian_ids", of=String("guardian_id"), description="The guardians' user ids (copied from the student)"),
]

address = Schema(
    "Address",
    fields=[
        String("line1", required=True, max_length=200),
        String("line2", max_length=200),
        String("city", required=True, max_length=100),
        String("state", max_length=100),
        String("postcode", max_length=12),
        String("country", default="NG", max_length=2),
    ],
)

