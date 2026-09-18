"""
Tests for the Praxis POC.

Test categories:
    1. Initial state    — Both teams start at Level 0, score 0
    2. Authentication   — Login, logout, access control
    3. Bug solving      — Solve bugs, earn points
    4. Duplicate guard  — No double points for the same bug
    5. Level protection — Cannot solve bugs from another level
    6. Level progression — 5/5 bugs → advance to next level
    7. Final level      — Complete Level 3 → no Level 4

Uses an in-memory SQLite database (via StaticPool) so tests are
fast, isolated, and don't affect the real database.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import the shared Base from models (single source of truth)
from app.models import Base, Team, Level, Bug, TeamBug
from app.database import get_db, seed_data
from app.main import app


# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------
# StaticPool makes all connections share the SAME in-memory database.
# Without this, each connection would get a separate empty database.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Provide a test database session to route handlers."""
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


# Override the production database with the test database
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def reset_database():
    """
    Reset the database before each test.
    Creates fresh tables and seeds example data.
    """
    # Clear any session cookies from previous tests
    client.cookies.clear()
    Base.metadata.create_all(bind=test_engine)
    db = TestSession()
    seed_data(db)
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


# Test client (reused across all tests)
client = TestClient(app)


# ---------------------------------------------------------------------------
# Helper: log in and return cookies
# ---------------------------------------------------------------------------
def login(username="team01", password="password123"):
    """Log in and return the session cookies for authenticated requests."""
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    return response.cookies


# ---------------------------------------------------------------------------
# Helper: get bug IDs for a specific level number
# ---------------------------------------------------------------------------
def get_bug_ids_for_level(level_number: int) -> list[int]:
    """Return the bug IDs belonging to a given level number."""
    db = TestSession()
    level = db.query(Level).filter(Level.number == level_number).first()
    bugs = db.query(Bug).filter(Bug.level_id == level.id).all()
    bug_ids = [b.id for b in bugs]
    db.close()
    return bug_ids


# ===================================================================
# 1. INITIAL STATE
# ===================================================================
class TestInitialState:
    """Both teams must start at Level 0 with score 0."""

    def test_team01_starts_at_level_0(self):
        db = TestSession()
        team = db.query(Team).filter(Team.username == "team01").first()
        assert team.current_level == 0
        assert team.score == 0
        db.close()

    def test_team02_starts_at_level_0(self):
        db = TestSession()
        team = db.query(Team).filter(Team.username == "team02").first()
        assert team.current_level == 0
        assert team.score == 0
        db.close()

    def test_four_levels_exist(self):
        db = TestSession()
        levels = db.query(Level).all()
        assert len(levels) == 4
        numbers = sorted([l.number for l in levels])
        assert numbers == [0, 1, 2, 3]
        db.close()

    def test_each_level_has_5_bugs(self):
        db = TestSession()
        for level in db.query(Level).all():
            bug_count = db.query(Bug).filter(Bug.level_id == level.id).count()
            assert bug_count == 5, f"Level {level.number} should have 5 bugs, got {bug_count}"
        db.close()

    def test_total_20_bugs(self):
        db = TestSession()
        assert db.query(Bug).count() == 20
        db.close()


# ===================================================================
# 2. AUTHENTICATION
# ===================================================================
class TestAuthentication:
    """Login, logout, and access control."""

    def test_login_page_loads(self):
        response = client.get("/login")
        assert response.status_code == 200
        assert "Welcome to Praxis" in response.text

    def test_valid_login_redirects_to_dashboard(self):
        response = client.post(
            "/login",
            data={"username": "team01", "password": "password123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/dashboard" in response.headers["location"]

    def test_invalid_login_shows_error(self):
        response = client.post(
            "/login",
            data={"username": "team01", "password": "wrong"},
        )
        assert response.status_code == 200
        assert "Invalid username or password" in response.text

    def test_dashboard_requires_login(self):
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_challenge_requires_login(self):
        response = client.get("/challenge", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_logout_clears_session(self):
        cookies = login()
        response = client.get("/logout", cookies=cookies, follow_redirects=False)
        assert response.status_code == 302
        # After logout, dashboard should redirect to login
        response2 = client.get("/dashboard", follow_redirects=False)
        assert response2.status_code == 302

    def test_root_redirects_to_login(self):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]


# ===================================================================
# 3. BUG SOLVING
# ===================================================================
class TestBugSolving:
    """Solve a bug → solved=True, score +100."""

    def test_solve_one_bug(self):
        cookies = login()
        bug_ids = get_bug_ids_for_level(0)

        response = client.post(
            f"/challenge/check/{bug_ids[0]}",
            cookies=cookies,
        )
        data = response.json()

        assert response.status_code == 200
        assert data["success"] is True
        assert data["bug_solved"] is True
        assert data["score"] == 100
        assert data["bugs_solved"] == 1

    def test_solve_bug_updates_database(self):
        cookies = login()
        bug_ids = get_bug_ids_for_level(0)

        client.post(f"/challenge/check/{bug_ids[0]}", cookies=cookies)

        # Verify the database was updated
        db = TestSession()
        team = db.query(Team).filter(Team.username == "team01").first()
        assert team.score == 100
        team_bug = db.query(TeamBug).filter(
            TeamBug.team_id == team.id,
            TeamBug.bug_id == bug_ids[0],
        ).first()
        assert team_bug is not None
        assert team_bug.solved is True
        db.close()


# ===================================================================
# 4. DUPLICATE GUARD
# ===================================================================
class TestDuplicateGuard:
    """Solving the same bug twice must NOT give double points."""

    def test_no_duplicate_points(self):
        cookies = login()
        bug_ids = get_bug_ids_for_level(0)

        # Solve bug once
        resp1 = client.post(f"/challenge/check/{bug_ids[0]}", cookies=cookies)
        assert resp1.json()["score"] == 100

        # Try to solve the same bug again
        resp2 = client.post(f"/challenge/check/{bug_ids[0]}", cookies=cookies)
        data = resp2.json()

        assert data["success"] is False
        assert data["already_solved"] is True

        # Score should still be 100, not 200
        db = TestSession()
        team = db.query(Team).filter(Team.username == "team01").first()
        assert team.score == 100
        db.close()


# ===================================================================
# 5. LEVEL PROTECTION
# ===================================================================
class TestLevelProtection:
    """Cannot solve bugs from a level the team hasn't reached yet."""

    def test_cannot_solve_level1_bug_while_on_level0(self):
        cookies = login()

        # Team is on Level 0 — try to solve a Level 1 bug
        level1_bugs = get_bug_ids_for_level(1)
        response = client.post(
            f"/challenge/check/{level1_bugs[0]}",
            cookies=cookies,
        )
        data = response.json()

        assert response.status_code == 403
        assert data["success"] is False
        assert "current level" in data["message"].lower()

        # Score should remain 0
        db = TestSession()
        team = db.query(Team).filter(Team.username == "team01").first()
        assert team.score == 0
        db.close()

    def test_cannot_solve_level2_bug_while_on_level0(self):
        cookies = login()
        level2_bugs = get_bug_ids_for_level(2)

        response = client.post(
            f"/challenge/check/{level2_bugs[0]}",
            cookies=cookies,
        )
        assert response.status_code == 403

    def test_nonexistent_bug_returns_404(self):
        cookies = login()
        response = client.post("/challenge/check/99999", cookies=cookies)
        assert response.status_code == 404

    def test_unauthenticated_check_returns_401(self):
        bug_ids = get_bug_ids_for_level(0)
        response = client.post(f"/challenge/check/{bug_ids[0]}")
        assert response.status_code == 401


# ===================================================================
# 6. LEVEL PROGRESSION
# ===================================================================
class TestLevelProgression:
    """Solve 5 bugs in Level 0 → current_level becomes 1, score = 500."""

    def test_complete_level_0(self):
        cookies = login()
        bug_ids = get_bug_ids_for_level(0)

        # Solve all 5 bugs in Level 0
        for i, bug_id in enumerate(bug_ids):
            resp = client.post(f"/challenge/check/{bug_id}", cookies=cookies)
            data = resp.json()
            assert data["success"] is True
            assert data["score"] == (i + 1) * 100

        # The last response should indicate level completion
        assert data["level_completed"] is True
        assert data["new_level"] == 1

        # Verify database
        db = TestSession()
        team = db.query(Team).filter(Team.username == "team01").first()
        assert team.current_level == 1
        assert team.score == 500
        db.close()

    def test_after_level_0_can_solve_level_1_bugs(self):
        cookies = login()

        # Complete Level 0
        for bug_id in get_bug_ids_for_level(0):
            client.post(f"/challenge/check/{bug_id}", cookies=cookies)

        # Now Level 1 bugs should be accessible
        level1_bugs = get_bug_ids_for_level(1)
        response = client.post(
            f"/challenge/check/{level1_bugs[0]}",
            cookies=cookies,
        )
        data = response.json()
        assert data["success"] is True
        assert data["score"] == 600  # 500 from Level 0 + 100


# ===================================================================
# 7. FINAL LEVEL (Complete all levels)
# ===================================================================
class TestFinalLevel:
    """Complete all levels → no Level 4, competition completed."""

    def test_complete_all_levels(self):
        cookies = login()

        # Solve all 20 bugs across all 4 levels
        for level_num in range(4):
            for bug_id in get_bug_ids_for_level(level_num):
                resp = client.post(
                    f"/challenge/check/{bug_id}", cookies=cookies
                )
                assert resp.json()["success"] is True

        # The final response should indicate all levels completed
        data = resp.json()
        assert data["all_completed"] is True
        assert data["level_completed"] is True

        # Verify final state
        db = TestSession()
        team = db.query(Team).filter(Team.username == "team01").first()
        assert team.current_level == 4  # Beyond MAX_LEVEL (3)
        assert team.score == 2000       # 20 bugs × 100 points
        db.close()

    def test_dashboard_shows_completion(self):
        cookies = login()

        # Complete all levels
        for level_num in range(4):
            for bug_id in get_bug_ids_for_level(level_num):
                client.post(f"/challenge/check/{bug_id}", cookies=cookies)

        # Dashboard should show completion
        response = client.get("/dashboard", cookies=cookies)
        assert response.status_code == 200
        assert "Congratulations" in response.text

    def test_challenge_shows_completion(self):
        cookies = login()

        # Complete all levels
        for level_num in range(4):
            for bug_id in get_bug_ids_for_level(level_num):
                client.post(f"/challenge/check/{bug_id}", cookies=cookies)

        # Challenge page should show completion
        response = client.get("/challenge", cookies=cookies)
        assert response.status_code == 200
        assert "Congratulations" in response.text


# ===================================================================
# 8. TEAM ISOLATION
# ===================================================================
class TestTeamIsolation:
    """One team's progress should not affect another team."""

    def test_teams_have_independent_progress(self):
        cookies1 = login("team01")
        cookies2 = login("team02")

        # Team01 solves a bug
        bug_ids = get_bug_ids_for_level(0)
        client.post(f"/challenge/check/{bug_ids[0]}", cookies=cookies1)

        # Team02's score should still be 0
        db = TestSession()
        team2 = db.query(Team).filter(Team.username == "team02").first()
        assert team2.score == 0
        assert team2.current_level == 0
        db.close()
