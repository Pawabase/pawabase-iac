"""Exercise the deployed school system end to end: seed a little data, then run the real flows and check what they did.

    python scripts/smoke_test.py

Reads SCHOOL_ADMIN_KEY (a full-access key of the `school` environment) from .env.local and the payments hook secret from .env. Every run
makes its own records (names carry a short run id), so it can be repeated against the same environment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("SCHOOL_URL", "http://localhost:8080")
ENV = "school"


def read_env(name: str) -> dict[str, str]:
    path = ROOT / name
    out = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                out[key.strip()] = value.strip()
    return out


KEYS = {**read_env(".env"), **read_env(".env.local")}
ADMIN = KEYS["SCHOOL_ADMIN_KEY"]
HOOK_SECRET = KEYS["PAYMENTS_HOOK_SECRET"]
RUN = secrets.token_hex(3)
TEACHER = f"teacher-{RUN}"
http = httpx.Client(base_url=BASE, headers={"apikey": ADMIN}, timeout=60)
results: list[tuple[bool, str]] = []


def check(ok: bool, what: str, detail: object = "") -> bool:
    results.append((bool(ok), what))
    print(("  ✓ " if ok else "  ✗ ") + what + ("" if ok else f"   {str(detail)[:300]}"))
    return bool(ok)


def data(path: str, **filters) -> list[dict]:
    """List rows, filtering by equality: data("invoices", student_id=x) is GET /rest/v1/invoices?filter[student_id]=x."""
    params = {"per_page": 200, **{f"filter[{key}]": str(value) for key, value in filters.items()}}
    response = http.get(f"/rest/v1/{path}", params=params)
    response.raise_for_status()
    body = response.json()
    return body["data"] if isinstance(body, dict) else body


def create(path: str, body: dict) -> dict:
    response = http.post(f"/rest/v1/{path}", json=body)
    if response.status_code >= 400:
        raise SystemExit(f"could not create {path}: {response.status_code} {response.text[:300]}")
    return response.json()


def patch(path: str, row_id: str, body: dict) -> dict:
    response = http.patch(f"/rest/v1/{path}/{row_id}", json=body)
    response.raise_for_status()
    return response.json()


def flow(name: str, body: dict, *, as_user: dict | None = None) -> httpx.Response:
    """Call a flow the way an app would (POST /flows/v1/<name>), as the service."""
    return http.post(f"/flows/v1/{name}", json=body)


def run_flow(name: str, input: dict, *, as_user: dict | None = None) -> dict:
    """Run any flow now through the management API and get its result or its trace (for flows nothing exposes over HTTP)."""
    response = http.post(f"/platform/v1/envs/{ENV}/flows/{name}/run", json={"input": input, "as_user": as_user})
    response.raise_for_status()
    return response.json()


def wait_for(fetch, what: str, seconds: float = 25):
    deadline = time.time() + seconds
    while time.time() < deadline:
        found = fetch()
        if found:
            return found
        time.sleep(1)
    check(False, what, "timed out")
    return None


def section(title: str) -> None:
    print(f"\n{title}")


# ── seed ────────────────────────────────────────────────────────────────────
section("Seeding a school year")
for old in data("academic_years", current="true"):
    patch("academic_years", old["id"], {"current": False})
for old in data("terms", current="true"):
    patch("terms", old["id"], {"current": False})
year = create("academic_years", {"name": f"2026/27-{RUN}", "starts_on": "2026-09-01", "ends_on": "2027-07-15", "current": True})
term = create("terms", {"academic_year_id": year["id"], "name": "Term 1", "number": 1, "starts_on": "2026-09-01", "ends_on": "2026-12-18", "current": True, "status": "open"})
if not data("grade_scale"):
    for letter, low, high, points in (("A", 70, 100, 5), ("B", 60, 69.99, 4), ("C", 50, 59.99, 3), ("D", 40, 49.99, 2), ("F", 0, 39.99, 0)):
        create("grade_scale", {"letter": letter, "min_percent": low, "max_percent": high, "points": points})
existing = {row["code"]: row for row in data("grade_levels")}
level = existing.get("SMOKE7") or create("grade_levels", {"name": "Smoke test year 7", "code": "SMOKE7", "level": next(n for n in range(1, 21) if n not in {r["level"] for r in existing.values()}), "stage": "junior_secondary"})
room = create("rooms", {"name": f"Room {RUN}", "capacity": 30})
cls = create("sections", {"grade_level_id": level["id"], "academic_year_id": year["id"], "name": f"7A-{RUN}", "capacity": 2, "room_id": room["id"]})
maths = create("subjects", {"name": f"Mathematics {RUN}", "code": f"MA{RUN}"[:12]})
english = create("subjects", {"name": f"English {RUN}", "code": f"EN{RUN}"[:12]})
create("fee_structures", {
    "name": "Term 1 fees", "academic_year_id": year["id"], "term_id": term["id"], "grade_level_id": level["id"],
    "items": [{"name": "Tuition", "amount": 150000}, {"name": "Books", "amount": 25000}, {"name": "Lab", "amount": 10000}], "total": 185000,
})
check(True, f"school year, term, class {cls['name']}, two subjects and a fee structure created")

# ── enrolment ───────────────────────────────────────────────────────────────
section("Enrolling students")
family_email = f"parent.{RUN}@example.com"
first = flow("enroll_student", {
    "first_name": "Ada", "last_name": f"Okoye{RUN}", "date_of_birth": "2014-03-02", "gender": "female", "section_id": cls["id"],
    "address": {"line1": "12 School Road", "city": "Lagos"},
    "guardians": [
        {"first_name": "Chidi", "last_name": f"Okoye{RUN}", "email": family_email, "phone": "+2348012345678", "relationship": "father", "is_primary": True, "pays_fees": True},
        {"first_name": "Ngozi", "last_name": f"Okoye{RUN}", "email": f"ngozi.{RUN}@example.com", "relationship": "mother"},
    ],
})
ada = first.json() if first.status_code == 201 else {}
check(first.status_code == 201, "enroll_student creates a student with two guardians (201)", first.text[:300])
student = ada.get("student", {})
check(str(student.get("admission_number", "")).startswith("ADM-"), "the student gets an admission number", student)
check(len(data("student_guardians", student_id=student.get("id", "x"))) == 2, "both guardians are linked")
check(data("sections", id=cls["id"])[0]["enrolled"] == 1, "the class's place count went up to 1")
check(len(data("enrollments", student_id=student.get("id", "x"))) == 1, "an enrolment row records the year")

second = flow("enroll_student", {
    "first_name": "Emeka", "last_name": f"Okoye{RUN}", "date_of_birth": "2012-08-19", "gender": "male", "section_id": cls["id"],
    "guardians": [{"first_name": "Chidi", "last_name": f"Okoye{RUN}", "email": family_email, "relationship": "father", "is_primary": True, "pays_fees": True}],
})
check(second.status_code == 201, "a sibling can be enrolled with the same guardian email (201)", second.text[:300])
check(len([g for g in data("guardians", email=family_email)]) == 1, "the guardian is reused, not duplicated")
third = flow("enroll_student", {
    "first_name": "Zainab", "last_name": "Bello", "date_of_birth": "2014-01-01", "gender": "female", "section_id": cls["id"],
    "guardians": [{"first_name": "Musa", "last_name": "Bello", "email": f"musa.{RUN}@example.com"}],
})
check(third.status_code == 409 and "class_full" in third.text, "a full class refuses another student (409 class_full)", third.text[:200])
bad = flow("enroll_student", {"first_name": "No"})
check(bad.status_code == 422, "missing fields are refused (422)", bad.text[:200])
missing = flow("enroll_student", {
    "first_name": "A", "last_name": "B", "date_of_birth": "2014-01-01", "gender": "male", "section_id": "does-not-exist", "guardians": [],
})
check(missing.status_code == 404, "an unknown class is refused (404)", missing.text[:200])

# ── invoicing ───────────────────────────────────────────────────────────────
section("Invoices")
invoice = wait_for(lambda: (data("invoices", student_id=student["id"]) or [None])[0], "an invoice is created for the new student by the queued flow")
if invoice:
    check(invoice["subtotal"] == 185000 and invoice["total"] == 185000 and invoice["balance"] == 185000, "the invoice totals the three fee lines", invoice)
    check(len(data("invoice_lines", invoice_id=invoice["id"])) == 3, "three invoice lines were written")
    check(str(invoice["number"]).startswith("INV-") and invoice["status"] == "issued", "numbered and issued")
# a scholarship: 10% off the sibling's invoice
brother = second.json()["student"]
create("scholarships", {"student_id": brother["id"], "name": "Sibling discount", "kind": "percent", "value": 10, "active": True})
brother_invoice = wait_for(lambda: (data("invoices", student_id=brother["id"]) or [None])[0], "the sibling's invoice is created")
if brother_invoice:
    # the invoice may have been issued before the scholarship existed; run the flow again to apply it
    again = run_flow("issue_term_invoice", {"student_id": brother["id"]})
    check(again.get("status") == "succeeded", "issue_term_invoice can be run by hand", again)
    latest = sorted(data("invoices", student_id=brother["id"]), key=lambda r: r["created_at"])[-1]
    check(latest["discount"] == 18500 and latest["total"] == 166500, "a 10% scholarship takes 18,500 off 185,000", latest)

# ── payments through the signed hook ────────────────────────────────────────
section("Payments")
if invoice:
    def pay(reference: str, amount: float, *, status: str = "success", key: bytes | None = None) -> httpx.Response:
        body = json.dumps({"reference": reference, "invoice": invoice["number"], "amount": amount, "method": "transfer", "status": status}).encode()
        signature = hmac.new((key or HOOK_SECRET.encode()), body, hashlib.sha256).hexdigest()
        return httpx.post(f"{BASE}/hooks/v1/{ENV}/payments", content=body, headers={"x-signature": signature, "content-type": "application/json"})

    unsigned = pay(f"BAD-{RUN}", 1, key=b"wrong")
    check(unsigned.status_code == 401, "a notification with a wrong signature is refused (401)", unsigned.text[:200])
    part = pay(f"PAY-{RUN}-1", 100000)
    check(part.status_code in (200, 202), "a signed notification is accepted", part.text[:200])
    partial = wait_for(lambda: next((i for i in data("invoices", student_id=student["id"]) if i["status"] == "partial"), None), "the invoice becomes partial")
    if partial:
        check(partial["amount_paid"] == 100000 and partial["balance"] == 85000, "100,000 paid leaves 85,000", partial)
    pay(f"PAY-{RUN}-1", 100000)  # the provider retries the same notification
    time.sleep(3)
    check(len(data("payments", invoice_id=invoice["id"])) == 1, "a retried notification does not pay twice (unique reference)")
    pay(f"PAY-{RUN}-2", 85000)
    settled = wait_for(lambda: next((i for i in data("invoices", student_id=student["id"]) if i["status"] == "paid"), None), "the invoice becomes paid")
    if settled:
        check(settled["balance"] == 0 and settled["amount_paid"] == 185000, "the remaining 85,000 settles it", settled)
    pay(f"PAY-{RUN}-3", 5, status="failed")
    time.sleep(2)
    check(len(data("payments", invoice_id=invoice["id"])) == 2, "a failed payment notification is ignored")

# ── attendance ──────────────────────────────────────────────────────────────
section("Attendance")
marks = flow("mark_attendance", {"section_id": cls["id"], "date": "2026-10-05", "marks": [
    {"student_id": student["id"], "status": "absent", "reason": "unwell"},
    {"student_id": brother["id"], "status": "present"},
    {"student_id": "ghost", "status": "present"},
]})
check(marks.status_code == 200, "mark_attendance accepts a register", marks.text[:300])
if marks.status_code == 200:
    body = marks.json()
    check(body.get("tally") == {"absent": 1, "present": 2}, "the tally counts both statuses", body)
check(len(data("attendance", section_id=cls["id"], date="2026-10-05")) == 2, "two rows written; the unknown student was skipped")
again = flow("mark_attendance", {"section_id": cls["id"], "date": "2026-10-05", "marks": [{"student_id": student["id"], "status": "late"}]})
rows = data("attendance", student_id=student["id"], date="2026-10-05")
check(again.status_code == 200 and len(rows) == 1 and rows[0]["status"] == "late", "marking again corrects the row instead of duplicating it", rows)
check(flow("check_timetable_conflict", {"teacher_id": TEACHER, "weekday": 1, "period": 1}).status_code == 200, "a free teacher period is reported free")
create("timetable_slots", {"section_id": cls["id"], "subject_id": maths["id"], "teacher_id": TEACHER, "weekday": 1, "period": 1})
busy = flow("check_timetable_conflict", {"teacher_id": TEACHER, "weekday": 1, "period": 1})
check(busy.status_code == 409, "a booked teacher period conflicts (409)", busy.text[:200])

# ── grades and report cards ─────────────────────────────────────────────────
section("Grades and report cards")
kind = create("assessment_types", {"code": f"EX{RUN}"[:20], "name": "Exam", "weight": 100}) if not data("assessment_types") else data("assessment_types")[0]
exam = create("assessments", {"term_id": term["id"], "section_id": cls["id"], "subject_id": maths["id"], "teacher_id": TEACHER, "assessment_type_id": kind["id"], "title": "Maths exam", "max_score": 100})
english_exam = create("assessments", {"term_id": term["id"], "section_id": cls["id"], "subject_id": english["id"], "teacher_id": TEACHER, "assessment_type_id": kind["id"], "title": "English exam", "max_score": 50})
for assessment, who, score in ((exam, student, 78), (exam, brother, 35), (english_exam, student, 41), (english_exam, brother, 20)):
    create("grades", {"assessment_id": assessment["id"], "student_id": who["id"], "term_id": term["id"], "section_id": cls["id"], "subject_id": assessment["subject_id"],
                      "score": score, "max_score": assessment["max_score"]})
completed = wait_for(lambda: [g for g in data("grades", term_id=term["id"]) if g.get("letter")] if len([g for g in data("grades", term_id=term["id"]) if g.get("letter")]) == 4 else None, "all four grades get a percentage and letter")
if completed:
    by_score = {g["score"]: g for g in completed}
    check(by_score[78]["percentage"] == 78 and by_score[78]["letter"] == "A", "78/100 is 78% and an A", by_score[78])
    check(by_score[41]["percentage"] == 82 and by_score[41]["letter"] == "A", "41/50 is 82% and an A", by_score[41])
    check(by_score[35]["percentage"] == 35 and by_score[35]["letter"] == "F", "35/100 is 35% and an F", by_score[35])
cards = flow("compute_report_cards", {"term_id": term["id"], "section_id": cls["id"]})
check(cards.status_code == 201, "compute_report_cards builds the class's cards (201)", cards.text[:400])
built = data("report_cards", term_id=term["id"])
check(len(built) == 2, "one report card per student", built)
if len(built) == 2:
    top = next(c for c in built if c["student_id"] == student["id"])
    low = next(c for c in built if c["student_id"] == brother["id"])
    check(top["average"] == 80 and top["rank"] == 1 and top["letter"] == "A", "Ada averages 80, ranks first, grade A", top)
    check(low["average"] == 37.5 and low["rank"] == 2 and low["letter"] == "F", "Emeka averages 37.5, ranks second, grade F", low)
    check(isinstance(top["subjects"], dict) and len(top["subjects"]) == 2, "each card carries its two subjects", top["subjects"])
    published = flow("publish_report_cards", {"term_id": term["id"], "section_id": cls["id"]})
    check(published.status_code == 200 and published.json().get("published") == 2, "publish_report_cards publishes both", published.text[:200])
    check(all(c["published"] for c in data("report_cards", term_id=term["id"])), "cards are marked published")

# ── library ─────────────────────────────────────────────────────────────────
section("Library")
book = create("books", {"title": f"Things Fall Apart {RUN}", "author": "Chinua Achebe", "copies": 1, "available": 1, "isbn": f"978{int(RUN, 16):010d}"})
loan = flow("borrow_book", {"book_id": book["id"], "borrower_user_id": "reader-1", "borrower_name": "Ada"})
check(loan.status_code == 201 and loan.json()["status"] == "out", "borrow_book lends the book (201)", loan.text[:200])
check(data("books", id=book["id"])[0]["available"] == 0, "the shelf count drops to 0")
second_loan = flow("borrow_book", {"book_id": book["id"], "borrower_user_id": "reader-2"})
check(second_loan.status_code == 409, "no copy left: the next borrower is refused (409)", second_loan.text[:200])
back = flow("return_book", {"loan_id": loan.json()["id"]})
check(back.status_code == 200 and back.json()["fine"] == 0, "return_book takes it back with no fine", back.text[:200])
check(data("books", id=book["id"])[0]["available"] == 1, "the copy is back on the shelf")
check(flow("return_book", {"loan_id": loan.json()["id"]}).status_code == 409, "returning it twice is refused (409)")

# ── admissions ──────────────────────────────────────────────────────────────
section("Admissions")
application = create("admission_applications", {
    "first_name": "Tolu", "last_name": "Adeyemi", "date_of_birth": "2015-05-05", "gender": "female", "desired_grade_level_id": level["id"],
    "guardian_name": "Bola Adeyemi", "guardian_email": f"bola.{RUN}@example.com", "documents": ["a.pdf", "b.pdf"],
})
screened = wait_for(lambda: next((a for a in data("admission_applications", id=application["id"]) if a["status"] == "screening"), None), "a new application is screened automatically")
if screened:
    check(str(screened["reference"]).startswith("APP-") and screened["score"] == 40, "it gets a reference and a score of 40 (two documents)", screened)
decision = flow("decide_application", {"application_id": application["id"], "decision": "accepted", "notes": "Welcome"})
check(decision.status_code == 200 and data("admission_applications", id=application["id"])[0]["status"] == "accepted", "decide_application accepts it", decision.text[:200])
check(flow("decide_application", {"application_id": application["id"], "decision": "maybe"}).status_code == 422, "an invalid decision is refused (422)")

# ── promotion ───────────────────────────────────────────────────────────────
section("Promotion")
next_year = create("academic_years", {"name": f"2027/28-{RUN}", "starts_on": "2027-09-01", "ends_on": "2028-07-15", "current": False})
next_class = create("sections", {"grade_level_id": level["id"], "academic_year_id": next_year["id"], "name": f"8A-{RUN}", "capacity": 30})
moved = flow("promote_students", {"from_section_id": cls["id"], "to_section_id": next_class["id"]})
check(moved.status_code == 200 and len(moved.json()["promoted"]) == 2, "promote_students moves both students (200)", moved.text[:300])
check(all(s["section_id"] == next_class["id"] for s in data("students", section_id=next_class["id"])) and len(data("students", section_id=next_class["id"])) == 2, "they now sit in the new class")


# ── a guardian signs up; the portal ─────────────────────────────────────────
section("Guardian accounts and the portal")
PUBLISHABLE = KEYS["SCHOOL_PUBLISHABLE_KEY"]
password = f"Sch00l-{secrets.token_hex(4)}!"
admin_api = f"/platform/v1/envs/{ENV}/auth"
made = http.post(f"{admin_api}/users", json={"email": family_email, "password": password, "roles": ["guardian"], "email_verified": True})
check(made.status_code in (200, 201), "an account is created for the father (role guardian)", made.text[:200])
user_id = made.json().get("id") if made.status_code in (200, 201) else None
linked = wait_for(lambda: next((g for g in data("guardians", email=family_email) if g.get("user_id")), None), "the new account is attached to the guardian record by email")
if linked and user_id:
    check(linked["user_id"] == user_id, "the guardian's user id is the new account", linked)
    kids = wait_for(lambda: all(user_id in (data("students", id=s["id"])[0].get("guardian_ids") or []) for s in (student, brother)) or None, "both children now list the guardian's account")
    login = httpx.post(f"{BASE}/auth/v1/token", params={"grant_type": "password"}, headers={"apikey": PUBLISHABLE}, json={"email": family_email, "password": password})
    check(login.status_code == 200 and "access_token" in login.json(), "the guardian can sign in", login.text[:200])
    if login.status_code == 200:
        mine = {"apikey": PUBLISHABLE, "authorization": f"Bearer {login.json()['access_token']}"}
        dash = httpx.get(f"{BASE}/rest/v1/parent/dashboard", headers=mine)
        check(dash.status_code == 200, "GET /rest/v1/parent/dashboard works for a guardian", dash.text[:300])
        if dash.status_code == 200:
            children = dash.json().get("children", [])
            names = sorted(c["student"]["name"] for c in children)
            check(names == ["Ada", "Emeka"], "it lists both children", children)
            ada_card = next((c for c in children if c["student"]["name"] == "Ada"), {})
            check(ada_card.get("report_cards") and ada_card.get("invoices_due") == 0, "Ada has a published report card and no invoice due", ada_card)
        sees = httpx.get(f"{BASE}/rest/v1/invoices", headers=mine, params={"per_page": 100}).json()
        mine_only = {i["student_id"] for i in sees.get("data", [])}
        check(mine_only and mine_only <= {student["id"], brother["id"]}, "the guardian's invoice list holds only their own children's invoices", sorted(mine_only))
        check(len(sees.get("data", [])) < len(data("invoices")), "while staff see more", (len(sees.get("data", [])), len(data("invoices"))))
        transcript = httpx.get(f"{BASE}/rest/v1/students/{student['id']}/transcript", headers=mine)
        check(transcript.status_code == 200 and len(transcript.json()["report_cards"]) == 1, "the transcript route returns Ada's published report card", transcript.text[:200])
        other = data("students", first_name="Zainab")
        stranger = httpx.get(f"{BASE}/rest/v1/students/{other[0]['id']}/transcript", headers=mine) if other else None
        if stranger is not None:
            check(stranger.status_code == 403, "another family's transcript is refused (403)", stranger.text[:200])
        refused = httpx.post(f"{BASE}/rest/v1/grades", headers=mine, json={"assessment_id": exam["id"], "student_id": student["id"], "term_id": term["id"], "section_id": cls["id"], "subject_id": maths["id"], "score": 100, "max_score": 100})
        check(refused.status_code in (401, 403), "a guardian cannot write grades", refused.status_code)
        no_staff = httpx.get(f"{BASE}/rest/v1/students", headers=mine, params={"per_page": 100}).json().get("data", [])
        check({s["id"] for s in no_staff} <= {student["id"], brother["id"]}, "a guardian lists only their own children", len(no_staff))
public = httpx.post(f"{BASE}/rest/v1/admission_applications", headers={"apikey": PUBLISHABLE}, json={
    "first_name": "Public", "last_name": "Applicant", "date_of_birth": "2015-01-01", "desired_grade_level_id": level["id"],
    "guardian_name": "P Applicant", "guardian_email": f"public.{RUN}@example.com"})
check(public.status_code == 201, "anyone can submit an application with the publishable key (201)", public.text[:200])
nobody = httpx.get(f"{BASE}/rest/v1/admission_applications", headers={"apikey": PUBLISHABLE})
check(nobody.status_code in (401, 403), "but cannot read the applications", nobody.status_code)

# ── the sweeps ──────────────────────────────────────────────────────────────
section("Scheduled sweeps")
late_student = create("students", {"admission_number": f"LATE-{RUN}", "first_name": "Late", "last_name": "Payer", "date_of_birth": "2013-01-01", "gender": "male", "section_id": cls["id"], "grade_level_id": level["id"]})
overdue = create("invoices", {"number": f"INV-LATE-{RUN}", "student_id": late_student["id"], "term_id": term["id"], "issued_on": "2026-08-01", "due_on": "2026-09-01",
                              "subtotal": 100000, "total": 100000, "balance": 100000, "amount_paid": 0, "status": "issued"})
fresh = create("invoices", {"number": f"INV-FRESH-{RUN}", "student_id": late_student["id"], "term_id": term["id"], "issued_on": "2026-10-20", "due_on": "2027-01-01",
                            "subtotal": 100000, "total": 100000, "balance": 100000, "amount_paid": 0, "status": "issued"})
sweep = run_flow("late_fee_sweep", {})
check(sweep.get("status") == "succeeded", "late_fee_sweep runs", sweep.get("error") or sweep.get("code"))
late = data("invoices", id=overdue["id"])[0]
check(late["status"] == "overdue" and late["late_fee"] == 5000 and late["total"] == 105000 and late["balance"] == 105000, "a past-due invoice gets a 5% late fee (5,000) and becomes overdue", late)
check(data("invoices", id=fresh["id"])[0]["status"] == "issued", "an invoice not yet due is left alone")
old_book = create("books", {"title": f"Overdue {RUN}", "author": "A", "copies": 1, "available": 0})
create("loans", {"book_id": old_book["id"], "borrower_user_id": "reader-9", "borrowed_on": "2026-08-01", "due_on": "2026-08-15", "status": "out"})
create("loans", {"book_id": old_book["id"], "borrower_user_id": "reader-8", "borrowed_on": "2026-10-20", "due_on": "2026-11-20", "status": "out"})
run_flow("overdue_loans_sweep", {})
states = sorted(l["status"] for l in data("loans", book_id=old_book["id"]))
check(states == ["out", "overdue"], "overdue_loans_sweep marks only the late loan", states)
absent_runs = wait_for(lambda: [r for r in http.get(f"/platform/v1/envs/{ENV}/flow-runs", params={"flow": "absence_alert"}).json().get("data", []) if r.get("status") == "succeeded"] or None, "the absence alert flow ran when an absence was recorded")

# ── summary ─────────────────────────────────────────────────────────────────
failed = [what for ok, what in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
for what in failed:
    print("  ✗", what)
sys.exit(1 if failed else 0)
