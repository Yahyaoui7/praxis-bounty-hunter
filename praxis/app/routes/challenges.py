"""
Challenge routes for the Praxis POC.

Handles:
    GET  /challenge              — Show bugs for the team's current level
    POST /challenge/check/{id}   — Solve a bug (deterministic in Phase 1)

Security enforced on every request:
    1. User must be authenticated.
    2. The bug must exist.
    3. The bug must belong to the team's CURRENT level (no skipping).
    4. The bug must not already be solved (no duplicate points).

Phase 1 vs Future:
    Phase 1:  Clicking "Check Solution" always solves the bug instantly.
    Future:   Student pushes code → GitLab CI → Tests → Praxis receives result.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Team, Level, Bug, TeamBug, Evaluation
from app.routes.auth import get_current_team
from app.services.evaluation_service import evaluate_submission

router = APIRouter()

# Points awarded per solved bug
POINTS_PER_BUG = 100

# The highest level number (Level 3)
MAX_LEVEL = 3


# ---------------------------------------------------------------------------
# GET /challenge — Show the bug list
# ---------------------------------------------------------------------------
@router.get("/challenge")
def challenge_page(request: Request, db: Session = Depends(get_db)):
    """
    Display the bugs for the team's current level.
    """
    # --- Authentication ---
    team = get_current_team(request, db)
    if not team:
        return RedirectResponse(url="/login", status_code=302)

    # --- All levels completed? ---
    if team.current_level > MAX_LEVEL:
        from app.main import templates
        return templates.TemplateResponse("challenge.html", {
            "request": request,
            "team": team,
            "current_level": None,
            "bugs": [],
            "bugs_solved": 0,
            "required_bugs": 5,
            "all_completed": True,
        })

    # --- Get current level ---
    current_level = db.query(Level).filter(
        Level.number == team.current_level
    ).first()

    if not current_level:
        return RedirectResponse(url="/dashboard", status_code=302)

    # --- Get bugs for this level ---
    bugs = db.query(Bug).filter(Bug.level_id == current_level.id).all()

    # --- Get which bugs this team has solved ---
    solved_bug_ids = {
        tb.bug_id
        for tb in db.query(TeamBug).filter(
            TeamBug.team_id == team.id,
            TeamBug.solved == True,
        ).all()
    }

    # Build the bug list with status
    bug_list = [
        {
            "id": bug.id,
            "title": bug.title,
            "description": bug.description,
            "solved": bug.id in solved_bug_ids,
        }
        for bug in bugs
    ]

    bugs_solved = sum(1 for b in bug_list if b["solved"])

    from app.main import templates
    return templates.TemplateResponse("challenge.html", {
        "request": request,
        "team": team,
        "current_level": current_level,
        "bugs": bug_list,
        "bugs_solved": bugs_solved,
        "required_bugs": current_level.required_bugs,
        "all_completed": False,
    })


# ---------------------------------------------------------------------------
# POST /challenge/check/{bug_id} — Solve a bug
# ---------------------------------------------------------------------------
@router.post("/challenge/check/{bug_id}")
def check_bug(bug_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Attempt to solve a bug by evaluating the submitted code from GitLab.
    """

    # --- 1. Authentication ---
    team = get_current_team(request, db)
    if not team:
        return JSONResponse(status_code=401, content={
            "success": False, "message": "Not authenticated",
        })

    # --- 2. Bug exists? ---
    bug = db.query(Bug).filter(Bug.id == bug_id).first()
    if not bug:
        return JSONResponse(status_code=404, content={
            "success": False, "message": "Bug not found",
        })

    # --- 3. Bug belongs to current level? ---
    current_level = db.query(Level).filter(
        Level.number == team.current_level
    ).first()

    if not current_level or bug.level_id != current_level.id:
        return JSONResponse(status_code=403, content={
            "success": False,
            "message": "This bug does not belong to your current level",
        })

    # --- 4. Run Evaluation ---
    eval_result = evaluate_submission(team, bug, current_level)
    
    # Store Evaluation in DB
    new_eval = Evaluation(
        team_id=team.id,
        bug_id=bug.id,
        commit_sha=eval_result.commit_sha,
        status=eval_result.status,
        passed=eval_result.passed,
        score=eval_result.score,
        exit_code=eval_result.exit_code,
        stdout=eval_result.stdout,
        stderr=eval_result.stderr,
        execution_time=eval_result.execution_time
    )
    db.add(new_eval)
    
    if not eval_result.passed:
        db.commit()
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": "Evaluation failed or timed out.",
            "evaluation": {
                "status": eval_result.status,
                "passed": eval_result.passed,
                "exit_code": eval_result.exit_code,
                "stdout": eval_result.stdout,
                "stderr": eval_result.stderr,
                "execution_time": eval_result.execution_time,
                "commit_sha": eval_result.commit_sha,
            }
        })

    # --- 5. Already solved? (Award points only once) ---
    existing = db.query(TeamBug).filter(
        TeamBug.team_id == team.id,
        TeamBug.bug_id == bug.id,
    ).first()

    if existing and existing.solved:
        db.commit()
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": "Bug already solved, but evaluation passed again.",
            "already_solved": True,
            "evaluation": {
                "status": eval_result.status,
                "passed": eval_result.passed,
                "exit_code": eval_result.exit_code,
                "stdout": eval_result.stdout,
                "stderr": eval_result.stderr,
                "execution_time": eval_result.execution_time,
                "commit_sha": eval_result.commit_sha,
            }
        })

    # --- 6. Mark as solved and award points ---
    if existing:
        existing.solved = True
        existing.solved_at = datetime.now(timezone.utc)
    else:
        db.add(TeamBug(
            team_id=team.id,
            bug_id=bug.id,
            solved=True,
            solved_at=datetime.now(timezone.utc),
        ))

    team.score += POINTS_PER_BUG
    db.flush()

    # --- Check level completion (5/5 bugs?) ---
    bugs_solved_count = (
        db.query(TeamBug)
        .join(Bug)
        .filter(
            TeamBug.team_id == team.id,
            Bug.level_id == current_level.id,
            TeamBug.solved == True,
        )
        .count()
    )

    level_completed = bugs_solved_count >= current_level.required_bugs
    all_completed = False

    if level_completed:
        if team.current_level < MAX_LEVEL:
            team.current_level += 1
        else:
            team.current_level = MAX_LEVEL + 1
            all_completed = True

    db.commit()

    if all_completed:
        message = "🎉 Congratulations! You completed all levels!"
    elif level_completed:
        message = (
            f"🎉 Level {current_level.number} completed! "
            f"Welcome to Level {team.current_level}!"
        )
    else:
        message = "Bug solved! ✅"

    return JSONResponse(status_code=200, content={
        "success": True,
        "message": message,
        "bug_solved": True,
        "score": team.score,
        "bugs_solved": bugs_solved_count,
        "required_bugs": current_level.required_bugs,
        "level_completed": level_completed,
        "all_completed": all_completed,
        "new_level": team.current_level,
        "evaluation": {
            "status": eval_result.status,
            "passed": eval_result.passed,
            "exit_code": eval_result.exit_code,
            "stdout": eval_result.stdout,
            "stderr": eval_result.stderr,
            "execution_time": eval_result.execution_time,
            "commit_sha": eval_result.commit_sha,
        }
    })
