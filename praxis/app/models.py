"""
Database models for the Praxis POC.

Models:
    Team    — A student team (login credentials + progress)
    Level   — A difficulty level (0, 1, 2, 3)
    Bug     — A single bug within a level
    TeamBug — Tracks which team solved which bug (junction table)

Architecture note:
    In the future, Team authentication will be replaced by 1337 LDAP/OAuth.
    The Team model will then store only team metadata and progress,
    and password_hash will no longer be needed.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship, declarative_base

# Base class for all models — shared across the application
Base = declarative_base()


class Team(Base):
    """
    A student team.

    current_level: The level number (0–3) the team is currently working on.
                   This is the server's source of truth — students cannot skip levels.
    score:         Total points earned. Only the server can increase this.

    Authentication (POC only):
        password_hash stores a SHA-256 hash. In production, replace with
        bcrypt/argon2 or remove entirely if using external auth (LDAP/OAuth).
    """
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)                       # "Team 01"
    username = Column(String, unique=True, nullable=False)      # "team01"
    password_hash = Column(String, nullable=False)              # SHA-256 (POC)
    current_level = Column(Integer, default=0, nullable=False)  # 0, 1, 2, 3, or 4 (done)
    score = Column(Integer, default=0, nullable=False)          # Total points

    # Intra 42 Integration (Phase 2)
    # The intra login of the user who created this team. Nullable so Phase 1 dummy teams still work.
    leader_intra_login = Column(String, unique=True, index=True, nullable=True)

    # GitLab Integration (Phase 2)
    gitlab_project_id = Column(Integer, nullable=True)
    gitlab_project_url = Column(String, nullable=True)
    gitlab_project_path = Column(String, nullable=True)

    # Relationship: all TeamBug records for this team
    solved_bugs = relationship("TeamBug", back_populates="team")


class Level(Base):
    """
    A difficulty level in the challenge.

    number:        The level number displayed to students (0, 1, 2, 3).
    required_bugs: How many bugs must be solved to complete this level (always 5).
    """
    __tablename__ = "levels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    number = Column(Integer, unique=True, nullable=False)  # 0, 1, 2, 3
    name = Column(String, nullable=False)
    description = Column(String)
    required_bugs = Column(Integer, default=5, nullable=False)

    # Relationship: all bugs in this level
    bugs = relationship("Bug", back_populates="level")


class Bug(Base):
    """
    A single bug within a level.

    In Phase 1, bugs are simulated — clicking "Check Solution" always solves them.
    In the future, bug resolution will come from GitLab CI test results:
        Student pushes fix → CI runs tests → Praxis receives PASS/FAIL → updates TeamBug
    """
    __tablename__ = "bugs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level_id = Column(Integer, ForeignKey("levels.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String)

    # Relationships
    level = relationship("Level", back_populates="bugs")
    team_solutions = relationship("TeamBug", back_populates="bug")


class TeamBug(Base):
    """
    Junction table: tracks which team solved which bug.

    The UniqueConstraint on (team_id, bug_id) prevents a team from
    receiving duplicate points for the same bug. This is enforced at
    the database level as a safety net.

    The server also checks for duplicates before inserting (belt and suspenders).
    """
    __tablename__ = "team_bugs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    bug_id = Column(Integer, ForeignKey("bugs.id"), nullable=False)
    solved = Column(Boolean, default=False, nullable=False)
    solved_at = Column(DateTime, nullable=True)

    # IMPORTANT: Prevent duplicate (team, bug) pairs at the database level
    __table_args__ = (
        UniqueConstraint("team_id", "bug_id", name="uq_team_bug"),
    )

    # Relationships
    team = relationship("Team", back_populates="solved_bugs")
    bug = relationship("Bug", back_populates="team_solutions")


class Evaluation(Base):
    """
    A record of a code evaluation execution.
    """
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    bug_id = Column(Integer, ForeignKey("bugs.id"), nullable=False)
    
    # Git commit evaluated
    commit_sha = Column(String, nullable=True)
    
    # Status can be: 'queued', 'running', 'passed', 'failed', 'timeout', 'error'
    status = Column(String, nullable=False, default="queued")
    passed = Column(Boolean, default=False, nullable=False)
    score = Column(Integer, default=0, nullable=False)
    
    # Execution metrics
    exit_code = Column(Integer, nullable=True)
    stdout = Column(String, nullable=True)
    stderr = Column(String, nullable=True)
    execution_time = Column(Integer, nullable=True) # or Float
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    team = relationship("Team", backref="evaluations")
    bug = relationship("Bug", backref="evaluations")
