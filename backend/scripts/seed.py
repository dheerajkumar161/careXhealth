"""Minimal clean seed (port of prisma/seed.ts): one doctor, two nurses, one admitted patient (no care plan, no history),
one specialist doctor who receives referrals (physiotherapy) and one test center. Every agent action is then triggered live.

    python scripts/seed.py            # wipe + seed
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.security import hash_password  # noqa: E402
from app.core.db import Base, get_engine, init_db, session_scope  # noqa: E402
from app.models import Patient, Provider, User  # noqa: E402

PASSWORD = "Password@123"


def reset() -> None:
    from sqlalchemy import text

    init_db()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.execute(text("DROP TABLE IF EXISTS apscheduler_jobs"))
        conn.execute(text("PRAGMA foreign_keys=ON"))


def seed() -> dict[str, str]:
    reset()
    pw = hash_password(PASSWORD)
    with session_scope() as s:

        def user(email: str, name: str, role: str, department: str, title: str | None = None, phone: str | None = None) -> User:
            u = User(email=email, name=name, role=role, department=department, title=title, phone=phone, password_hash=pw)
            s.add(u)
            s.flush()
            return u

        # Doctor — also listed in the provider directory so the Scheduling service can book follow-ups with them
        doctor = user("ananya.rao@carexhealth.health", "Dr. Ananya Rao", "DOCTOR", "Orthopedics", "Consultant Orthopedic Surgeon", "+91 98450 11201")
        s.add(
            Provider(
                user_id=doctor.id, name=doctor.name, organization="CareXHealth Hospital — Orthopedics OPD", type="DOCTOR", specialties="orthopedics,joint replacement,trauma",
                location="Block A, 2nd floor", rating=4.9, work_start_hour=10, work_end_hour=16, slot_minutes=20, work_days="1,2,3,4,5,6",
            )
        )  # fmt: skip
        nurse = user("priya.nair@carexhealth.health", "Priya Nair", "NURSE", "Orthopedics", "Senior Staff Nurse — Ortho Ward", "+91 98450 22301")
        # Second nurse — takes over when Priya is released from a patient (nurse handover flow)
        nurse2 = user("rahul.verma@carexhealth.health", "Rahul Verma", "NURSE", "Orthopedics", "Staff Nurse — Ortho Ward", "+91 98450 22302")
        # Specialist doctor who RECEIVES referrals (doctor-to-doctor)
        physio = user("kavya.menon@carexhealth.health", "Dr. Kavya Menon", "DOCTOR", "Physiotherapy", "Consultant Physiotherapist", "+91 98860 33401")
        s.add(
            Provider(
                user_id=physio.id, name=physio.name, organization="CareXHealth Hospital — Physiotherapy & Rehabilitation", type="DOCTOR",
                specialties="physiotherapy,rehabilitation,orthopedic rehab", location="Block C, Ground floor", phone="+91 98860 33401", rating=4.9,
                work_start_hour=8, work_end_hour=18, slot_minutes=45, work_days="1,2,3,4,5,6",
            )
        )  # fmt: skip
        # Test center — required for investigations and the lab-report flow
        lab = user("reports@citydiagnostics.in", "City Diagnostics Lab", "TEST_CENTER", "Laboratory", "Test Center", "+91 80 4110 2200")
        s.add(
            Provider(
                user_id=lab.id, name="City Diagnostics", organization="City Diagnostics", type="TEST_CENTER", specialties="laboratory,pathology,radiology",
                location="MG Road, Bengaluru", rating=4.8, work_start_hour=7, work_end_hour=19, slot_minutes=15, work_days="0,1,2,3,4,5,6",
            )
        )  # fmt: skip
        admin = user("admin@carexhealth.health", "Hospital Admin", "ADMIN", "Administration", "System Administrator", "+91 80 4000 0000")
        # Patient — still admitted: no care plan, tasks, observations, alerts or documents
        pu = user("arjun.sharma@example.com", "Arjun Sharma", "PATIENT", "Orthopedics", None, "+91 99000 10001")
        s.add(
            Patient(
                user_id=pu.id, mrn="CB-240117", date_of_birth=datetime(1962, 4, 12), gender="Male", blood_group="B+", diagnosis="Primary osteoarthritis, right knee",
                procedure="Right total knee replacement", allergies="Penicillin", comorbidities="Hypertension", admission_date=datetime.now() - timedelta(days=4),
                status="ADMITTED", address="12 Lavelle Road, Bengaluru", emergency_contact="Sunita Sharma (wife) +91 99000 10002", doctor_id=doctor.id, nurse_id=nurse.id,
            )
        )  # fmt: skip
        return {"Doctor": doctor.email, "Nurse": nurse.email, "Nurse (takes over on handover)": nurse2.email, "Patient": pu.email, "Specialist (Physiotherapy)": physio.email, "Test center": lab.email, "Admin": admin.email}


if __name__ == "__main__":
    accounts = seed()
    print(f"Clean database ready. Password for every account: {PASSWORD}")
    for role, email in accounts.items():
        print(f"  {role:<34} {email}")
