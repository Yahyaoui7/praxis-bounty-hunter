"""
Tests for the GitLab integration (Phase 2 Foundation).

Uses mocks for all GitLab API calls — no real GitLab account needed.
Reuses the same test database setup from test_app.py.
"""

import pytest
import os

os.environ["ADMIN_PASSWORD"] = "test-admin-password"

from fastapi.testclient import TestClient

from app.models import Team
from app.services.gitlab_service import GitLabServiceError
from app.main import app

# Reuse the same test database infrastructure from test_app
from tests.test_app import (
    TestSession,
    test_engine,
    override_get_db,
    Base,
)
from app.database import get_db, seed_data

# Ensure the override is set (test_app sets it too, but be explicit)
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database():
    """Reset the database before each test."""
    client.cookies.clear()
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestSession()
    seed_data(db)
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


# ===================================================================
# 1. ADMIN TEAM CREATION
# ===================================================================
class TestAdminTeamCreation:
    """Test team creation via the admin interface."""

    def test_admin_page_loads(self):
        response = client.get("/admin/team/new")
        assert response.status_code == 200
        assert "Create New Team" in response.text

    def test_create_team_success(self, monkeypatch):
        """Successful team creation with mocked GitLab API."""

        def mock_create_repo(team_name):
            return {
                "id": 12345,
                "web_url": "https://gitlab.com/ns/test-team-bounty-hunter",
                "path_with_namespace": "ns/test-team-bounty-hunter",
            }

        monkeypatch.setattr(
            "app.services.gitlab_service.create_team_repository", mock_create_repo
        )

        response = client.post(
            "/admin/team/new",
            data={
                "admin_password": "test-admin-password",
                "team_name": "Test Team",
                "username": "testteam",
                "password": "mypassword",
            },
        )

        assert response.status_code == 200
        assert "successfully" in response.text

        # Verify database state
        db = TestSession()
        team = db.query(Team).filter(Team.username == "testteam").first()
        assert team is not None
        assert team.gitlab_project_id == 12345
        assert team.gitlab_project_url == "https://gitlab.com/ns/test-team-bounty-hunter"
        assert team.gitlab_project_path == "ns/test-team-bounty-hunter"
        db.close()

    def test_create_team_gitlab_failure_rollback(self, monkeypatch):
        """If GitLab API fails, the team must NOT be saved in the DB."""

        def mock_create_repo_fail(team_name):
            raise GitLabServiceError("API token invalid")

        monkeypatch.setattr(
            "app.services.gitlab_service.create_team_repository", mock_create_repo_fail
        )

        response = client.post(
            "/admin/team/new",
            data={
                "admin_password": "test-admin-password",
                "team_name": "Fail Team",
                "username": "failteam",
                "password": "mypassword",
            },
        )

        assert response.status_code == 200
        assert "GitLab repository creation failed" in response.text

        # Verify that the team was NOT created (rollback worked)
        db = TestSession()
        team = db.query(Team).filter(Team.username == "failteam").first()
        assert team is None
        db.close()

    def test_create_team_invalid_admin_password(self):
        """Invalid admin password should be rejected."""
        response = client.post(
            "/admin/team/new",
            data={
                "admin_password": "wrong-password",
                "team_name": "Wrong Team",
                "username": "wrongteam",
                "password": "mypassword",
            },
        )
        assert response.status_code == 200
        assert "Invalid admin password" in response.text

    def test_create_team_duplicate_username(self, monkeypatch):
        """Cannot create a team with a username that already exists."""
        response = client.post(
            "/admin/team/new",
            data={
                "admin_password": "test-admin-password",
                "team_name": "Team 01 Duplicate",
                "username": "team01",  # Already exists from seed data
                "password": "mypassword",
            },
        )
        assert response.status_code == 200
        assert "already exists" in response.text

    def test_existing_seeded_teams_still_work(self):
        """Phase 1 seeded teams (team01, team02) must still exist."""
        db = TestSession()
        team01 = db.query(Team).filter(Team.username == "team01").first()
        team02 = db.query(Team).filter(Team.username == "team02").first()
        assert team01 is not None
        assert team02 is not None
        assert team01.current_level == 0
        assert team01.score == 0
        # Seeded teams have no GitLab project (Phase 1)
        assert team01.gitlab_project_id is None
        db.close()


# ===================================================================
# 3. SECURITY
# ===================================================================
class TestGitLabSecurity:
    """Ensure GitLab tokens are never exposed."""

    def test_gitlab_token_not_in_dashboard(self):
        """The GitLab token must never appear in the dashboard HTML."""
        response = client.post(
            "/login",
            data={"username": "team01", "password": "password123"},
            follow_redirects=True,
        )
        assert "PRIVATE-TOKEN" not in response.text
        assert "change-me" not in response.text

    def test_gitlab_token_not_in_admin_page(self):
        """The GitLab token must never appear in the admin page."""
        response = client.get("/admin/team/new")
        assert "PRIVATE-TOKEN" not in response.text
