"""Applications to join the school, from the public form to the decision."""

from infra.common import address
from infra.policies import management, registry

from pawabase_iac import Allow, Array, Date, DateTime, Desc, Email, Index, Integer, JSON, Number, RateLimit, Ref, String, Table, Text

admission_applications = Table(
    "admission_applications",
    description="Anyone may apply (the public form creates a row); only the registry can read or decide on them.",
    fields=[
        String("reference", unique=True, max_length=20, description="Given to the applicant to follow their application"),
        String("first_name", required=True, max_length=80),
        String("last_name", required=True, max_length=80),
        Date("date_of_birth", required=True),
        String("gender", enum=["female", "male", "other"]),
        String("desired_grade_level_id", required=True),
        String("guardian_name", required=True, max_length=160),
        Email("guardian_email", required=True),
        String("guardian_phone", pattern=r"^\+?[0-9 ()-]{7,20}$"),
        String("previous_school", max_length=200),
        Ref("address", schema=address),
        Array("documents", of=String("key"), description="Object keys in the documents bucket"),
        Integer("score", minimum=0, maximum=100, default=0),
        JSON("screening", description="How the score was reached"),
        String("status", enum=["received", "screening", "interview", "accepted", "waitlisted", "rejected", "enrolled"], default="received"),
        Text("notes"),
        DateTime("decided_at"),
        String("decided_by"),
    ],
    operations={
        "list": Allow(registry),
        "get": Allow(registry),
        "create": Allow("public"),
        "update": Allow(registry),
        "delete": Allow(management),
    },
    rate_limit=RateLimit(10, 60),
    indexes=[Index("status", Desc("created_at")), Index("desired_grade_level_id", "status"), Index("guardian_email")],
)
