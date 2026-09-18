"""
Tests for the Intra 42 OAuth flow.

Key invariants tested:
    1. The configured INTRA_REDIRECT_URI is used (not localhost).
    2. The authorization URL sent to Intra contains the LAN redirect URI.
    3. The callback route is /auth/callback — the path registered in the Intra app.
    4. Existing OAuth flows (callback → register, callback → login) still work.

LAN deployment note:
    Tests use INTRA_REDIRECT_URI=http://10.12.9.5:8000/auth/callback (the real LAN value).
    Using localhost here would be incorrect: in production, 'localhost' resolves to
    each student's own PC — which has no web server listening. Only the Praxis server
    machine (10.12.9.5) runs uvicorn and handles OAuth callbacks.
"""

import pytest
import os
from urllib.parse import urlparse, parse_qs, unquote
from fastapi.testclient import TestClient

# Must be set before importing the app.
# Use the real LAN redirect URI — NOT localhost.
# localhost would only work from the server machine itself (10.12.9.5),
# and would break OAuth for all other student PCs on the LAN.
os.environ["INTRA_CLIENT_ID"] = "test-client-id"
os.environ["INTRA_CLIENT_SECRET"] = "test-client-secret"
os.environ["INTRA_REDIRECT_URI"] = "http://10.12.1.10:8000/auth/callback"

from app.main import app
from app.models import Team
from app.services.intra_service import IntraServiceError, get_intra_authorization_url

from tests.test_app import (
    TestSession,
    test_engine,
    override_get_db,
    Base,
)
from app.database import get_db, seed_data

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database():
    client.cookies.clear()
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = TestSession()
    seed_data(db)
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


# ---------------------------------------------------------------------------
# LAN / Redirect URI correctness tests
# ---------------------------------------------------------------------------

def test_redirect_uri_is_not_localhost():
    """
    The configured INTRA_REDIRECT_URI must NOT be localhost or 127.0.0.1.

    Reason: 'localhost' resolves to the machine running the browser (the student's PC),
    not the Praxis server. Intra 42 would redirect the browser to localhost on the
    student's machine, where no web server is listening, causing a connection error.

    For a LAN deployment, INTRA_REDIRECT_URI must point to the Praxis server's LAN IP,
    e.g. http://10.12.9.5:8000/auth/callback.
    """
    redirect_uri = os.environ["INTRA_REDIRECT_URI"]
    assert "localhost" not in redirect_uri, (
        "INTRA_REDIRECT_URI must not use 'localhost'. "
        "Use the server's LAN IP (e.g. http://10.12.9.5:8000/auth/callback). "
        "See app/services/intra_service.py module docstring for details."
    )
    assert "127.0.0.1" not in redirect_uri, (
        "INTRA_REDIRECT_URI must not use '127.0.0.1'. "
        "Use the server's LAN IP (e.g. http://10.12.9.5:8000/auth/callback)."
    )


def test_redirect_uri_is_in_authorization_url():
    """
    The OAuth authorization URL sent to Intra 42 must contain the configured
    INTRA_REDIRECT_URI — not a hardcoded localhost fallback.

    This test verifies that get_intra_authorization_url() respects the
    INTRA_REDIRECT_URI environment variable and properly encodes it in the URL.
    """
    auth_url = get_intra_authorization_url()
    parsed = urlparse(auth_url)
    query_params = parse_qs(parsed.query)

    # The redirect_uri param must be present
    assert "redirect_uri" in query_params, "Authorization URL is missing 'redirect_uri' parameter"

    # Decode the URI (it may be URL-encoded in the query string)
    actual_redirect_uri = unquote(query_params["redirect_uri"][0])
    expected_redirect_uri = os.environ["INTRA_REDIRECT_URI"]

    assert actual_redirect_uri == expected_redirect_uri, (
        f"Authorization URL uses redirect_uri='{actual_redirect_uri}' "
        f"but expected '{expected_redirect_uri}'. "
        "The configured INTRA_REDIRECT_URI must be passed unchanged to Intra 42."
    )

    # Extra safety: must not contain localhost
    assert "localhost" not in actual_redirect_uri, (
        "The redirect_uri in the authorization URL must not use 'localhost'."
    )


def test_callback_route_is_correct():
    """
    The OAuth callback route must be /auth/callback.

    This path must exactly match what is registered in the Intra 42 application
    settings (api.intra.42.fr → your application → redirect URI).

    The route must respond (not 404) when a valid code or error is provided.
    """
    # With a missing code, we should get a redirect — not a 404
    response = client.get("/auth/callback?error=access_denied", follow_redirects=False)
    assert response.status_code == 302, (
        "The /auth/callback route must exist and handle OAuth error responses."
    )
    # Must not 404
    assert response.status_code != 404, "The /auth/callback route does not exist!"


# ---------------------------------------------------------------------------
# Existing OAuth flow tests (must still pass)
# ---------------------------------------------------------------------------

def test_login_intra_redirects_to_42():
    response = client.get("/login/intra", follow_redirects=False)
    assert response.status_code == 302
    assert "api.intra.42.fr/oauth/authorize" in response.headers["location"]


def test_auth_callback_new_user_redirects_to_register(monkeypatch):
    """A new intra user should be redirected to choose a team name."""

    def mock_get_intra_token(code):
        return "mocked-access-token"

    def mock_get_intra_user_profile(token):
        return {"login": "new_intra_user"}

    monkeypatch.setattr("app.services.intra_service.get_intra_token", mock_get_intra_token)
    monkeypatch.setattr("app.services.intra_service.get_intra_user_profile", mock_get_intra_user_profile)

    response = client.get("/auth/callback?code=mockcode", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/register/intra"
    assert "pending_intra" in response.headers.get("set-cookie", "")


def test_auth_callback_existing_user_logs_in(monkeypatch):
    """An existing intra user should be logged in immediately."""

    # First, create a team linked to an intra account
    db = TestSession()
    team = Team(
        name="Intra Team",
        username="intrateam",
        password_hash="",
        leader_intra_login="existing_intra_user",
        current_level=0,
        score=0,
    )
    db.add(team)
    db.commit()
    db.close()

    def mock_get_intra_token(code):
        return "mocked-access-token"

    def mock_get_intra_user_profile(token):
        return {"login": "existing_intra_user"}

    monkeypatch.setattr("app.services.intra_service.get_intra_token", mock_get_intra_token)
    monkeypatch.setattr("app.services.intra_service.get_intra_user_profile", mock_get_intra_user_profile)

    response = client.get("/auth/callback?code=mockcode", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "session" in response.headers.get("set-cookie", "")


def test_register_intra_creates_team(monkeypatch):
    """Test the full flow: callback → register → dashboard."""

    # 1. Mock the GitLab repo creation
    def mock_create_repo(team_name):
        return {
            "id": 555,
            "web_url": "https://gitlab.com/ns/intra-team",
            "path_with_namespace": "ns/intra-team",
        }
    monkeypatch.setattr("app.services.gitlab_service.create_team_repository", mock_create_repo)

    # 2. Mock Intra OAuth
    def mock_get_intra_token(code): return "token"
    def mock_get_intra_user_profile(token): return {"login": "new_intra_user"}
    monkeypatch.setattr("app.services.intra_service.get_intra_token", mock_get_intra_token)
    monkeypatch.setattr("app.services.intra_service.get_intra_user_profile", mock_get_intra_user_profile)

    # Simulate Intra redirecting back to our app
    callback_response = client.get("/auth/callback?code=mockcode", follow_redirects=False)
    assert callback_response.status_code == 302

    # Check that we can hit the register page
    register_page = client.get("/register/intra")
    assert register_page.status_code == 200
    assert "new_intra_user" in register_page.text

    # Post the team name
    post_response = client.post(
        "/register/intra",
        data={"team_name": "The Intra Hackers"},
        follow_redirects=False,
    )

    # Should redirect to dashboard
    assert post_response.status_code == 302
    assert post_response.headers["location"] == "/dashboard"

    # Verify DB
    db = TestSession()
    team = db.query(Team).filter(Team.leader_intra_login == "new_intra_user").first()
    assert team is not None
    assert team.name == "The Intra Hackers"
    assert team.username == "theintrahackers"  # lowercase without spaces
    assert team.gitlab_project_id == 555
    db.close()
