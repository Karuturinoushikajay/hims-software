from __future__ import annotations

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def seeded_db(db, settings):
    settings.DEBUG = True
    if not settings.DEMO_SEED_PASSWORD:
        settings.DEMO_SEED_PASSWORD = "ChangeMeDemo!2026"
    call_command("seed_demo", force=True)

