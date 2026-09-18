"""
Dashboard route for the Praxis POC.

Shows the team's current progress:
    - Team name
    - Current level (number + name)
    - Bugs solved in the current level  (e.g., 3 / 5)
    - Total score
    - "Start Challenge" button

If all levels (0–3) are completed, shows a congratulations message instead.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Level, Bug, TeamBug
from app.routes.auth import get_current_team

router = APIRouter()

# The highest level number in the database (Level 3 = The Final Boss)
MAX_LEVEL = 3


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Render the team dashboard.

    Logic:
        1. Check authentication (redirect to /login if not logged in).
        2. If current_level > MAX_LEVEL → all levels completed.
        3. Otherwise, query bugs solved in the current level.
        4. Render the dashboard template with progress data.
    """
    # --- Authentication ---
    team = get_current_team(request, db)
    if not team:
        return RedirectResponse(url="/login", status_code=302)

    # --- Check completion ---
    all_completed = team.current_level > MAX_LEVEL

    # --- Current level info ---
    current_level = None
    bugs_solved = 0
    required_bugs = 5

    if not all_completed:
        # Find the Level record matching the team's current_level number
        current_level = db.query(Level).filter(
            Level.number == team.current_level
        ).first()

        if current_level:
            required_bugs = current_level.required_bugs

            # Count solved bugs in this level for this team
            bugs_solved = (
                db.query(TeamBug)
                .join(Bug)
                .filter(
                    TeamBug.team_id == team.id,
                    Bug.level_id == current_level.id,
                    TeamBug.solved == True,
                )
                .count()
            )

    # --- Render ---
    from app.main import templates
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "team": team,
        "current_level": current_level,
        "bugs_solved": bugs_solved,
        "required_bugs": required_bugs,
        "all_completed": all_completed,
    })
