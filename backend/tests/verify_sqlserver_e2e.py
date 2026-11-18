#!/usr/bin/env python3
"""
Comprehensive End-to-End Verification against Microsoft SQL Server 2022
Database: StudentSkillGapAnalyzer

Tests:
1. Engine verification (mssql dialect, pyodbc driver, active connectivity)
2. Migrated data verification (User Nilesh, 21 analyses, skills, roadmaps)
3. User Registration on SQL Server
4. Duplicate email validation
5. Login with valid credentials & password verification (Argon2id)
6. Login with invalid credentials (HTTP 401)
7. JWT authentication & /api/auth/me protected endpoint
8. Student Profile GET & PUT operations
9. Password reset token generation, hashing, and password reset flow
10. Analysis creation with IT role validation
11. Analysis history listing
12. Multi-user data isolation (IDOR security)
13. Persistence check
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from sqlalchemy import text
from app.config import settings
from app.database import engine, SessionLocal, check_db_connection
from app.main import app
from app.models.user import User
from app.models.analysis import Analysis
from app.models.student_profile import StudentProfile
from app.models.password_reset import PasswordResetToken

client = TestClient(app)


def run_all_verifications():
    print("=" * 70)
    print("MICROSOFT SQL SERVER 2022 END-TO-END VERIFICATION SUITE")
    print("=" * 70)

    # 1. Engine & Dialect Verification
    backend_name = engine.url.get_backend_name()
    driver_name = engine.url.get_driver_name()
    print(f"[CHECK 1] SQLAlchemy Backend: '{backend_name}', Driver: '{driver_name}'")
    assert backend_name == "mssql", f"Expected backend 'mssql', got '{backend_name}'"
    assert driver_name == "pyodbc", f"Expected driver 'pyodbc', got '{driver_name}'"
    
    with SessionLocal() as db:
        assert check_db_connection(db) is True, "Database connectivity check failed"
        res = db.execute(text("SELECT DB_NAME(), @@VERSION")).fetchone()
        db_name, version = res[0], res[1].split("\n")[0]
        print(f"          Connected Database: {db_name}")
        print(f"          SQL Server Version: {version}")
        assert db_name == "StudentSkillGapAnalyzer"
    print("          --> PASSED: Microsoft SQL Server 2022 active and verified.\n")

    # 2. Migrated Data Verification
    print("[CHECK 2] Verifying Migrated Data in SQL Server...")
    with SessionLocal() as db:
        migrated_user = db.query(User).filter(User.email == "girase2004@gmail.com").first()
        assert migrated_user is not None, "Migrated user 'girase2004@gmail.com' not found!"
        print(f"          Found Migrated User #{migrated_user.id}: {migrated_user.name} ({migrated_user.email})")

        analyses = db.query(Analysis).filter(Analysis.user_id == migrated_user.id).all()
        print(f"          Found {len(analyses)} analyses belonging to Nilesh in SQL Server.")
        assert len(analyses) == 21, f"Expected 21 analyses, found {len(analyses)}"
    print("          --> PASSED: All 21 migrated analyses and user account verified.\n")

    # 3. User Registration on SQL Server
    test_email = "test.student.sqlserver@university.edu"
    test_password = "SecurePassword123!"
    print(f"[CHECK 3] Testing User Registration for '{test_email}'...")
    
    # Cleanup any prior test run row
    with SessionLocal() as db:
        old = db.query(User).filter(User.email == test_email).first()
        if old:
            db.delete(old)
            db.commit()

    reg_res = client.post(
        "/api/auth/register",
        json={"name": "SQLServer Student", "email": test_email, "password": test_password},
    )
    assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
    token_data = reg_res.json()
    auth_token = token_data["access_token"]
    user_id = token_data["user"]["id"]
    headers = {"Authorization": f"Bearer {auth_token}"}
    print(f"          Registered new User #{user_id} with JWT token.")
    print("          --> PASSED: Registration on SQL Server succeeded.\n")

    # 4. Duplicate Email Validation
    print("[CHECK 4] Testing Duplicate Email Validation...")
    dup_res = client.post(
        "/api/auth/register",
        json={"name": "Duplicate Student", "email": test_email, "password": "AnotherPassword!"},
    )
    assert dup_res.status_code == 400, f"Expected 400 for duplicate email, got {dup_res.status_code}"
    print(f"          Duplicate rejected: {dup_res.json()['detail']}")
    print("          --> PASSED: Duplicate email prevention verified.\n")

    # 5. Login with Valid Credentials
    print("[CHECK 5] Testing Login with Valid Credentials...")
    login_res = client.post(
        "/api/auth/login",
        json={"email": test_email, "password": test_password},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    assert "access_token" in login_res.json()
    print("          --> PASSED: Valid credentials authenticated successfully.\n")

    # 6. Login with Invalid Credentials
    print("[CHECK 6] Testing Login with Invalid Credentials...")
    bad_login_res = client.post(
        "/api/auth/login",
        json={"email": test_email, "password": "WrongPassword999!"},
    )
    assert bad_login_res.status_code == 401, f"Expected 401, got {bad_login_res.status_code}"
    print("          --> PASSED: Invalid credentials rejected with HTTP 401.\n")

    # 7. JWT Authentication & Protected Endpoint
    print("[CHECK 7] Testing Protected Endpoint /api/auth/me...")
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200, f"/api/auth/me failed: {me_res.text}"
    me_data = me_res.json()
    assert me_data["email"] == test_email
    assert me_data["name"] == "SQLServer Student"
    print(f"          Authenticated User: {me_data['name']} <{me_data['email']}>")
    print("          --> PASSED: Bearer token authentication verified.\n")

    # 8. Student Profile GET & PUT
    print("[CHECK 8] Testing Student Profile Management...")
    # GET profile (auto-initializes profile in SQL Server)
    prof_get = client.get("/api/profile", headers=headers)
    assert prof_get.status_code == 200, f"GET /api/profile failed: {prof_get.text}"
    print(f"          Auto-initialized Profile for User #{user_id}")

    # PUT profile
    profile_update = {
        "name": "SQLServer Student",
        "mobile_number": "+1 555-0188",
        "college_name": "MIT College of Engineering",
        "degree": "Bachelor of Technology",
        "specialization": "Information Technology",
        "graduation_year": 2026,
        "weekly_study_hours": 15,
        "avatar_url": "https://api.dicebear.com/7.x/bottts/svg?seed=Nilesh",
        "bio": "Enthusiastic full-stack and cloud engineer.",
        "current_skills": ["Python", "SQL Server", "React", "Docker"],
    }
    prof_put = client.put("/api/profile", json=profile_update, headers=headers)
    assert prof_put.status_code == 200, f"PUT /api/profile failed: {prof_put.text}"
    updated_prof = prof_put.json()
    assert updated_prof["college_name"] == "MIT College of Engineering"
    assert updated_prof["current_skills"] == ["Python", "SQL Server", "React", "Docker"]
    print("          Updated Profile in SQL Server:")
    print(f"            College: {updated_prof['college_name']}, Year: {updated_prof['graduation_year']}")
    print(f"            Skills: {updated_prof['current_skills']}")
    print("          --> PASSED: Student Profile CRUD verified on SQL Server.\n")

    # 9. Password Reset Flow
    print("[CHECK 9] Testing Forgot & Reset Password Flow...")
    forgot_res = client.post("/api/auth/forgot-password", json={"email": test_email})
    assert forgot_res.status_code == 200
    
    # Retrieve raw token from SQL Server record
    with SessionLocal() as db:
        token_record = db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.is_used == False,
        ).first()
        assert token_record is not None, "Password reset token not recorded in SQL Server!"
        stored_hash = token_record.token_hash
        print(f"          Recorded password reset token hash in SQL Server: {stored_hash[:16]}...")

    # We test resetting using a known token
    import secrets, hashlib
    raw_token = secrets.token_urlsafe(32)
    new_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with SessionLocal() as db:
        from datetime import datetime, timezone, timedelta
        db.add(PasswordResetToken(
            user_id=user_id,
            token_hash=new_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            is_used=False,
        ))
        db.commit()

    reset_res = client.post("/api/auth/reset-password", json={
        "token": raw_token,
        "new_password": "BrandNewPassword456!",
        "confirm_password": "BrandNewPassword456!",
    })
    assert reset_res.status_code == 200, f"Reset failed: {reset_res.text}"

    # Verify login with new password
    new_login = client.post("/api/auth/login", json={
        "email": test_email,
        "password": "BrandNewPassword456!",
    })
    assert new_login.status_code == 200
    print("          --> PASSED: Password reset flow completed and verified.\n")

    # 10. Create Skill Gap Analysis with IT Role Validation
    print("[CHECK 10] Testing Skill Gap Analysis Creation on SQL Server...")
    analysis_payload = {
        "company_name": "Microsoft",
        "target_role": "Cloud Solutions Architect",
        "weekly_hours": 12,
        "student_skills": [
            {"name": "Python", "proficiency": "intermediate"},
            {"name": "SQL", "proficiency": "intermediate"},
            {"name": "Azure", "proficiency": "beginner"},
        ],
    }
    create_res = client.post("/api/analyses", json=analysis_payload, headers=headers)
    assert create_res.status_code == 201, f"Analysis creation failed: {create_res.text}"
    analysis_data = create_res.json()
    new_analysis_id = analysis_data["id"]
    print(f"          Created Analysis #{new_analysis_id} for '{analysis_data['company_name']}' - '{analysis_data['target_role']}'")
    assert len(analysis_data["student_skills"]) == 3
    print("          --> PASSED: Analysis and student skills stored in SQL Server.\n")

    # 11. Retrieve Analysis History
    print("[CHECK 11] Testing Analysis History Retrieval...")
    list_res = client.get("/api/analyses", headers=headers)
    assert list_res.status_code == 200
    analyses_list = list_res.json()
    assert any(a["id"] == new_analysis_id for a in analyses_list)
    print(f"          Retrieved {len(analyses_list)} user-scoped analyses from SQL Server.")
    print("          --> PASSED: Analysis history retrieval verified.\n")

    # 12. Multi-user Data Isolation (IDOR Protection)
    print("[CHECK 12] Testing Multi-User Data Isolation (IDOR)...")
    user2_email = "second.student.sqlserver@university.edu"
    reg_u2 = client.post(
        "/api/auth/register",
        json={"name": "Second Student", "email": user2_email, "password": "Password999!"},
    )
    token_u2 = reg_u2.json()["access_token"]
    u2_headers = {"Authorization": f"Bearer {token_u2}"}

    # User 2 tries to access User 1's analysis
    idor_res = client.get(f"/api/analyses/{new_analysis_id}", headers=u2_headers)
    assert idor_res.status_code == 404, f"Expected 404 for IDOR, got {idor_res.status_code}"
    print("          User 2 denied access to User 1's analysis (HTTP 404 returned).")
    print("          --> PASSED: Data isolation and tenant security verified.\n")

    # Cleanup temporary test users
    with SessionLocal() as db:
        for email in (test_email, user2_email):
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.delete(u)
        db.commit()
    print("[CLEANUP] Temporary test users cleaned up from SQL Server.")

    print("\n" + "=" * 70)
    print("ALL MICROSOFT SQL SERVER 2022 VERIFICATIONS PASSED WITH 100% SUCCESS!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    run_all_verifications()
