import os
import hashlib

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Team
from app.services import gitlab_service
from app.services.gitlab_service import GitLabServiceError
from app.routes.auth import get_current_team

router = APIRouter()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin-poc-password")

@router.get("/admin/team/new")
def new_team_page(request: Request, db: Session = Depends(get_db)):
    """Show the admin page to create a new team."""
    # Ensure current team is logged in as an "admin" 
    # For POC, we just use a simple page with an admin password field.
    from app.main import templates
    return templates.TemplateResponse("admin_create_team.html", {
        "request": request,
        "error": None,
        "success": None
    })


@router.post("/admin/team/new")
def create_new_team(
    request: Request,
    admin_password: str = Form(...),
    team_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle the creation of a new team and its GitLab repository."""
    from app.main import templates
    
    if admin_password != ADMIN_PASSWORD:
        return templates.TemplateResponse("admin_create_team.html", {
            "request": request,
            "error": "Invalid admin password.",
            "success": None
        })
        
    # Check if username already exists
    existing_team = db.query(Team).filter(Team.username == username).first()
    if existing_team:
        return templates.TemplateResponse("admin_create_team.html", {
            "request": request,
            "error": f"Team with username '{username}' already exists.",
            "success": None
        })
        
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    # 1. Create team in DB (but don't commit yet)
    new_team = Team(
        name=team_name,
        username=username,
        password_hash=password_hash,
        current_level=0,
        score=0
    )
    db.add(new_team)
    # Flush to get the team ID and ensure DB constraints are met before hitting GitLab
    try:
        db.flush()
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("admin_create_team.html", {
            "request": request,
            "error": f"Database error: {str(e)}",
            "success": None
        })

    # 2. Call GitLab API
    try:
        repo_data = gitlab_service.create_team_repository(team_name)
        
        # 3. Update team with GitLab details
        new_team.gitlab_project_id = repo_data["id"]
        new_team.gitlab_project_url = repo_data["web_url"]
        new_team.gitlab_project_path = repo_data["path_with_namespace"]
        
        # 4. Commit everything
        db.commit()
        
        return templates.TemplateResponse("admin_create_team.html", {
            "request": request,
            "error": None,
            "success": f"Team '{team_name}' created successfully with GitLab repository!"
        })
        
    except GitLabServiceError as e:
        # 5. Rollback on GitLab failure
        db.rollback()
        return templates.TemplateResponse("admin_create_team.html", {
            "request": request,
            "error": f"GitLab repository creation failed: {str(e)}. The team was NOT created.",
            "success": None
        })
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("admin_create_team.html", {
            "request": request,
            "error": f"An unexpected error occurred: {str(e)}",
            "success": None
        })
