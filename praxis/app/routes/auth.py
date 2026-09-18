"""
Authentication routes for the Praxis POC.

POC Implementation:
    - Username/password login against the local SQLite database.
    - Sessions managed via signed cookies (itsdangerous).

Future Implementation:
    - Replace verify_credentials() with 1337 LDAP/Active Directory lookup.
    - Replace cookie sessions with OAuth2 tokens or JWT.
    - The route structure (GET /login, POST /login, GET /logout) stays the same.

Design decision:
    Authentication logic is isolated in verify_credentials() and get_current_team().
    When switching to 1337 auth, only these two functions need to change.
"""

import os
import hashlib

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from itsdangerous import URLSafeSerializer

from app.database import get_db
from app.models import Team
from app.services import intra_service
from app.services.intra_service import IntraServiceError

router = APIRouter()

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
# Secret key for signing cookies. Loaded from env (production) or default (POC).
SECRET_KEY = os.getenv("SECRET_KEY", "praxis-poc-secret-key-change-me")
serializer = URLSafeSerializer(SECRET_KEY)


def get_current_team(request: Request, db: Session) -> Team | None:
    """
    Extract the logged-in team from the session cookie.

    Returns the Team object if the cookie is valid, None otherwise.

    FUTURE: Replace with OAuth2/JWT token verification.
    """
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return None

    try:
        data = serializer.loads(session_cookie)
        team_id = data.get("team_id")
        if team_id is None:
            return None
        return db.query(Team).filter(Team.id == team_id).first()
    except Exception:
        # Cookie was tampered with or expired
        return None


def verify_credentials(username: str, password: str, db: Session) -> Team | None:
    """
    Verify login credentials against the database.

    POC:    Compares SHA-256 hash of the password.
    FUTURE: Replace this function body with an LDAP bind or OAuth call.

    Returns the Team if credentials match, None otherwise.
    """
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return db.query(Team).filter(
        Team.username == username,
        Team.password_hash == password_hash,
    ).first()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/")
def root():
    """Redirect the root URL to the login page."""
    return RedirectResponse(url="/login", status_code=302)


@router.get("/login")
def login_page(request: Request, error: str = None, db: Session = Depends(get_db)):
    """
    Show the login page.
    If already logged in, skip straight to the dashboard.
    """
    team = get_current_team(request, db)
    if team:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Import templates here to avoid circular imports
    # (main.py creates templates, routes are imported by main.py)
    from app.main import templates
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
    })


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Handle login form submission.

    Success → set signed session cookie → redirect to /dashboard
    Failure → re-render login page with error message
    """
    team = verify_credentials(username, password, db)

    if team is None:
        from app.main import templates
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password",
        })

    # Create a signed cookie containing the team's database ID
    session_token = serializer.dumps({"team_id": team.id})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="session",
        value=session_token,
        httponly=True,   # JavaScript cannot read this cookie (security)
        max_age=3600 * 8,  # 8 hours
    )
    return response


@router.get("/logout")
def logout():
    """Clear the session cookie and redirect to the login page."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response


# ---------------------------------------------------------------------------
# Team Registration (Intra 42 Flow)
# ---------------------------------------------------------------------------
@router.get("/login/intra")
def login_intra():
    """Redirect to the Intra 42 OAuth authorization page."""
    try:
        url = intra_service.get_intra_authorization_url()
        return RedirectResponse(url=url, status_code=302)
    except IntraServiceError as e:
        # If not configured, just redirect to login with an error
        return RedirectResponse(url="/login?error=Intra+42+not+configured", status_code=302)

@router.get("/auth/callback")
def auth_callback(request: Request, code: str = None, error: str = None, db: Session = Depends(get_db)):
    """Handle the OAuth callback from Intra 42."""
    from app.main import templates
    
    if error:
        return RedirectResponse(url=f"/login?error=Intra+42+Login+Failed", status_code=302)
        
    if not code:
        return RedirectResponse(url="/login?error=No+authorization+code+provided", status_code=302)
        
    try:
        # 1. Exchange code for token
        token = intra_service.get_intra_token(code)
        
        # 2. Get user profile
        profile = intra_service.get_intra_user_profile(token)
        intra_login = profile.get("login")
        
        if not intra_login:
            raise IntraServiceError("Could not retrieve intra login from profile.")
            
        # 3. Check if this intra user already has a team
        team = db.query(Team).filter(Team.leader_intra_login == intra_login).first()
        
        if team:
            # Login successful
            session_token = serializer.dumps({"team_id": team.id})
            response = RedirectResponse(url="/dashboard", status_code=302)
            response.set_cookie(
                key="session",
                value=session_token,
                httponly=True,
                max_age=3600 * 8,
            )
            return response
        else:
            # New user! Redirect to registration page, passing their intra_login securely.
            # We use a temporary signed cookie to pass the intra login so they can't tamper with it.
            temp_token = serializer.dumps({"pending_intra_login": intra_login})
            response = RedirectResponse(url="/register/intra", status_code=302)
            response.set_cookie(
                key="pending_intra",
                value=temp_token,
                httponly=True,
                max_age=600, # Only valid for 10 minutes
            )
            return response
            
    except IntraServiceError as e:
        return RedirectResponse(url=f"/login?error={str(e)}", status_code=302)


@router.get("/register/intra")
def register_intra_page(request: Request):
    """Show the team registration page for Intra users."""
    pending_cookie = request.cookies.get("pending_intra")
    if not pending_cookie:
        return RedirectResponse(url="/login?error=Session+expired.+Please+login+with+Intra+again.", status_code=302)
        
    try:
        data = serializer.loads(pending_cookie)
        intra_login = data.get("pending_intra_login")
    except Exception:
        return RedirectResponse(url="/login?error=Invalid+session", status_code=302)
        
    from app.main import templates
    return templates.TemplateResponse("register_intra.html", {
        "request": request,
        "intra_login": intra_login,
        "error": None
    })

@router.post("/register/intra")
def register_intra(
    request: Request,
    team_name: str = Form(...),
    db: Session = Depends(get_db),
):
    """Handle Intra team creation."""
    from app.main import templates
    from app.services.gitlab_service import create_team_repository, GitLabServiceError
    
    pending_cookie = request.cookies.get("pending_intra")
    if not pending_cookie:
        return RedirectResponse(url="/login?error=Session+expired", status_code=302)
        
    try:
        data = serializer.loads(pending_cookie)
        intra_login = data.get("pending_intra_login")
    except Exception:
        return RedirectResponse(url="/login?error=Invalid+session", status_code=302)
        
    # Check if team name already exists (username is no longer used, so we use team_name as username for compatibility, safely formatted)
    safe_username = team_name.lower().replace(" ", "")
    
    existing = db.query(Team).filter(Team.username == safe_username).first()
    if existing:
        return templates.TemplateResponse("register_intra.html", {
            "request": request,
            "intra_login": intra_login,
            "error": f"Team name '{team_name}' is too similar to an existing team. Choose another."
        })
        
    # Check if user already registered (double submit)
    existing_intra = db.query(Team).filter(Team.leader_intra_login == intra_login).first()
    if existing_intra:
        return RedirectResponse(url="/login", status_code=302)

    # Create the team
    new_team = Team(
        name=team_name,
        username=safe_username,
        password_hash="", # No password needed for intra users
        leader_intra_login=intra_login,
        current_level=0,
        score=0,
    )
    db.add(new_team)

    try:
        db.flush()
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("register_intra.html", {
            "request": request,
            "intra_login": intra_login,
            "error": f"Could not create team: {str(e)}"
        })

    # Call GitLab API to create the repository
    try:
        repo_data = create_team_repository(team_name)
        new_team.gitlab_project_id = repo_data["id"]
        new_team.gitlab_project_url = repo_data["web_url"]
        new_team.gitlab_project_path = repo_data["path_with_namespace"]
        db.commit()
    except GitLabServiceError as e:
        db.rollback()
        return templates.TemplateResponse("register_intra.html", {
            "request": request,
            "intra_login": intra_login,
            "error": f"GitLab repository creation failed: {str(e)}. Team was NOT created."
        })
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("register_intra.html", {
            "request": request,
            "intra_login": intra_login,
            "error": f"Unexpected error: {str(e)}"
        })

    # Auto-login
    session_token = serializer.dumps({"team_id": new_team.id})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="session",
        value=session_token,
        httponly=True,
        max_age=3600 * 8,
    )
    response.delete_cookie("pending_intra")
    return response

