"""Fees: what each year group pays, invoices, payments and scholarships."""

from infra.academics import academic_years, grade_levels, terms
from infra.common import family_fields
from infra.people import students
from infra.policies import finance_staff, management, staff_or_family

from pawabase_iac import (
    Allow, Array, BelongsTo, Boolean, Date, DateTime, Desc, HasMany, Index, Integer, JSON, Number, RateLimit, String, Table, Text, Where,
    read_only,
)

fee_structures = Table(
    "fee_structures",
    description="What a year group pays in a term, line by line.",
    fields=[
        String("name", required=True, max_length=120),
        String("academic_year_id", required=True),
        String("term_id", required=True),
        String("grade_level_id", required=True),
        JSON("items", required=True, description="[{name, amount, optional}]"),
        Number("total", minimum=0),
        String("currency", default="NGN", max_length=3),
        Integer("due_in_days", minimum=0, maximum=120, default=30),
        Number("late_fee_percent", minimum=0, maximum=100, default=5),
    ],
    operations={**read_only("authenticated"), "create": Allow(finance_staff), "update": Allow(finance_staff), "delete": Allow(management)},
    relations=[BelongsTo("term", terms, "term_id"), BelongsTo("grade_level", grade_levels, "grade_level_id")],
    indexes=[Index("term_id", "grade_level_id", unique=True, name="uniq_fee_structure")],
)

scholarships = Table(
    "scholarships",
    fields=[
        String("student_id", required=True),
        String("name", required=True, max_length=120),
        String("kind", enum=["percent", "fixed"], required=True),
        Number("value", required=True, minimum=0),
        String("term_id", description="Empty means every term"),
        Boolean("active", default=True),
        *family_fields,
    ],
    operations={"list": Allow(staff_or_family), "get": Allow(staff_or_family), "create": Allow(management), "update": Allow(management),
                "delete": Allow(management)},
    relations=[BelongsTo("student", students, "student_id")],
    indexes=[Index("student_id", "active")],
)

invoices = Table(
    "invoices",
    fields=[
        String("number", required=True, unique=True, max_length=30),
        String("student_id", required=True),
        String("term_id", required=True),
        Date("issued_on", required=True),
        Date("due_on", required=True),
        Number("subtotal", required=True, minimum=0),
        Number("discount", minimum=0, default=0),
        Number("late_fee", minimum=0, default=0),
        Number("total", required=True, minimum=0),
        Number("amount_paid", minimum=0, default=0),
        Number("balance", minimum=0),
        String("currency", default="NGN", max_length=3),
        String("status", enum=["draft", "issued", "partial", "paid", "overdue", "void"], default="issued"),
        Text("notes"),
        *family_fields,
    ],
    operations={"list": Allow(staff_or_family), "get": Allow(staff_or_family), "create": Allow(finance_staff), "update": Allow(finance_staff),
                "delete": Allow(management)},
    relations=[BelongsTo("student", students, "student_id"), BelongsTo("term", terms, "term_id"), HasMany("lines", "invoice_lines", "invoice_id"),
               HasMany("payments", "payments", "invoice_id")],
    indexes=[
        Index("student_id", "term_id", name="invoice_student_term"),
        Index("status", "due_on", where=[Where("status", "!=", "paid")], name="open_by_due"),
        Index("student_user_id", Desc("issued_on")),
    ],
    realtime=True,
    rate_limit=RateLimit(120, 60),
)

invoice_lines = Table(
    "invoice_lines",
    fields=[
        String("invoice_id", required=True),
        String("description", required=True, max_length=200),
        Number("amount", required=True),
        Integer("quantity", minimum=1, default=1),
    ],
    operations={"list": Allow(finance_staff), "get": Allow(finance_staff), "create": Allow(finance_staff), "update": Allow(finance_staff),
                "delete": Allow(finance_staff)},
    relations=[BelongsTo("invoice", invoices, "invoice_id")],
    indexes=[Index("invoice_id")],
)

payments = Table(
    "payments",
    description="Money received. reference is unique, so a provider that retries a notification cannot pay an invoice twice.",
    fields=[
        String("invoice_id", required=True),
        String("student_id", required=True),
        Number("amount", required=True, minimum=0.01),
        String("method", enum=["cash", "card", "transfer", "mobile", "cheque"], required=True),
        String("reference", required=True, unique=True, max_length=80),
        DateTime("paid_at"),
        String("received_by"),
        String("status", enum=["pending", "confirmed", "failed", "refunded"], default="confirmed"),
        JSON("provider_payload"),
        *family_fields,
    ],
    operations={"list": Allow(staff_or_family), "get": Allow(staff_or_family), "create": Allow(finance_staff), "update": Allow(finance_staff),
                "delete": Allow(management)},
    relations=[BelongsTo("invoice", invoices, "invoice_id")],
    indexes=[Index("invoice_id"), Index("student_id", Desc("paid_at"))],
)
