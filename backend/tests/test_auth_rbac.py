from __future__ import annotations

import pytest
from django.contrib.auth.hashers import identify_hasher

from apps.accounts.models import User
from apps.organizations.models import Facility


@pytest.mark.django_db
def test_password_uses_argon2(seeded_db):
    user = User.objects.get(username="facadmin")
    assert identify_hasher(user.password).algorithm == "argon2"


@pytest.mark.django_db
def test_login_and_me(api_client, seeded_db, settings):
    settings.DEMO_SEED_PASSWORD = settings.DEMO_SEED_PASSWORD or "ChangeMeDemo!2026"
    password = settings.DEMO_SEED_PASSWORD
    res = api_client.post(
        "/api/v1/auth/login",
        {"username": "facadmin", "password": password},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["username"] == "facadmin"
    assert res.data["active_facility_id"]

    me = api_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert "FACILITY_ADMIN" in me.data["roles"]


@pytest.mark.django_db
def test_login_throttle(api_client, seeded_db, settings):
    settings.LOGIN_THROTTLE_LIMIT = 3
    for _ in range(3):
        api_client.post(
            "/api/v1/auth/login",
            {"username": "facadmin", "password": "wrong"},
            format="json",
        )
    res = api_client.post(
        "/api/v1/auth/login",
        {"username": "facadmin", "password": "wrong"},
        format="json",
    )
    assert res.status_code == 429
    assert res.data["code"] == "login_throttled"


@pytest.mark.django_db
def test_receptionist_forbidden_on_user_admin(api_client, seeded_db, settings):
    password = settings.DEMO_SEED_PASSWORD
    login = api_client.post(
        "/api/v1/auth/login",
        {"username": "receptionist", "password": password},
        format="json",
    )
    assert login.status_code == 200
    res = api_client.get("/api/v1/users")
    assert res.status_code == 403


@pytest.mark.django_db
def test_cannot_read_other_facility_settings(api_client, seeded_db, settings):
    from apps.organizations.models import FacilitySettings, Organization

    password = settings.DEMO_SEED_PASSWORD
    api_client.post(
        "/api/v1/auth/login",
        {"username": "facadmin", "password": password},
        format="json",
    )
    org = Organization.objects.get(code="DHG")
    other = Facility.objects.create(
        organization=org,
        code="OTHER",
        name="Other Facility",
        state_code="36",
        bed_capacity=50,
    )
    FacilitySettings.objects.create(facility=other, require_2fa_roles=["SUPER_ADMIN", "DOCTOR"])
    res = api_client.get(f"/api/v1/facilities/{other.id}/settings")
    assert res.status_code == 403


@pytest.mark.django_db
def test_doctor_pending_2fa_setup_flag(api_client, seeded_db, settings):
    password = settings.DEMO_SEED_PASSWORD
    res = api_client.post(
        "/api/v1/auth/login",
        {"username": "doctor", "password": password},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["pending_2fa_setup"] is True
    assert res.data["totp_enabled"] is False
