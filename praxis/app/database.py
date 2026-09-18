"""
Database configuration for the Praxis POC.

Uses SQLite for simplicity. In production, replace with PostgreSQL
by changing the DATABASE_URL environment variable.

Key components:
    engine       — SQLAlchemy engine connected to SQLite
    SessionLocal — Session factory for creating database sessions
    get_db()     — FastAPI dependency that provides a database session per request
    init_db()    — Creates tables and seeds initial data on first run
"""

import os
import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import Base from models (single source of truth for the declarative base)
from app.models import Base, Team, Level, Bug, Evaluation

# ---------------------------------------------------------------------------
# Database URL — defaults to a SQLite file in the project directory.
# Override via environment variable for testing or production.
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./praxis.db")

# Create the SQLAlchemy engine
# check_same_thread=False is required for SQLite with FastAPI's async workers
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Session factory — each HTTP request gets its own session via get_db()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
def get_db():
    """
    Provide a database session to route handlers via FastAPI's Depends().

    Usage:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            teams = db.query(Team).all()

    The session is automatically closed when the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
def init_db():
    """
    Create all tables and seed example data if the database is empty.

    Called once when the FastAPI application starts up.
    In production, you would use Alembic migrations instead of create_all().
    """
    Base.metadata.create_all(bind=engine)

    # Only seed if the database has no levels yet (first run)
    db = SessionLocal()
    try:
        if db.query(Level).count() == 0:
            seed_data(db)
    finally:
        db.close()


def seed_data(db):
    """
    Populate the database with example teams, levels, and bugs.

    Creates:
        2 teams  — team01, team02 (both at Level 0, score 0)
        4 levels — Level 0 through Level 3
        20 bugs  — 5 per level, with meaningful titles

    All teams start from exactly the same state.
    """

    # ----- Teams -----
    # Passwords are hashed with SHA-256 (simple and sufficient for the POC).
    # FUTURE: Use bcrypt/argon2, or remove passwords entirely with 1337 OAuth.
    pw_hash = hashlib.sha256("password123".encode()).hexdigest()

    teams = [
        Team(name="Team 01", username="team01",
             password_hash=pw_hash, current_level=0, score=0),
        Team(name="Team 02", username="team02",
             password_hash=pw_hash, current_level=0, score=0),
    ]
    db.add_all(teams)

    # ----- Levels -----
    levels = [
        Level(number=0, name="Introduction / Tutorial",
              description="Welcome to Praxis! Fix these simple bugs to learn the workflow.",
              required_bugs=5),
        Level(number=1, name="The Basics",
              description="Now that you know the workflow, tackle some fundamental bugs.",
              required_bugs=5),
        Level(number=2, name="Getting Harder",
              description="These bugs require more careful analysis and debugging.",
              required_bugs=5),
        Level(number=3, name="The Final Boss",
              description="The hardest bugs await. Good luck!",
              required_bugs=5),
    ]
    db.add_all(levels)
    db.flush()  # Flush so level.id is available for bugs

    # ----- Bugs -----
    # Each level has 5 bugs with meaningful titles and descriptions.
    bugs_by_level = {
        0: [
            ("Fix the missing return statement",
             "The function calculates the result but forgets to return it."),
            ("Fix the wrong variable name",
             "A variable is misspelled, causing a NameError."),
            ("Fix the off-by-one error",
             "The loop iterates one too many or one too few times."),
            ("Fix the missing import",
             "A required module is not imported at the top of the file."),
            ("Fix the incorrect string format",
             "The f-string has a syntax error in the format expression."),
        ],
        1: [
            ("Fix the broken loop condition",
             "The while loop never terminates because the condition is wrong."),
            ("Fix the null reference error",
             "The code accesses an attribute on a None value."),
            ("Fix the array index out of bounds",
             "The code tries to access an index beyond the list length."),
            ("Fix the incorrect type conversion",
             "A string is used where an integer is expected."),
            ("Fix the missing error handling",
             "The function crashes on invalid input instead of handling it gracefully."),
        ],
        2: [
            ("Fix the race condition",
             "Two threads modify a shared counter without proper synchronization."),
            ("Fix the memory leak",
             "Objects are created in a loop but never released or garbage collected."),
            ("Fix the deadlock scenario",
             "Two locks are acquired in opposite order, causing a deadlock."),
            ("Fix the buffer overflow",
             "Data is written beyond the allocated buffer size."),
            ("Fix the SQL injection vulnerability",
             "User input is concatenated directly into a raw SQL query string."),
        ],
        3: [
            ("Fix the distributed consensus bug",
             "Nodes disagree on the leader after a network partition heals."),
            ("Fix the cache invalidation issue",
             "Stale data is served because the cache is never refreshed on writes."),
            ("Fix the authentication bypass",
             "A missing authorization check allows access without valid credentials."),
            ("Fix the data corruption bug",
             "Concurrent writes to the same record silently overwrite each other."),
            ("Fix the cascading failure",
             "One failed microservice brings down the entire system due to missing circuit breakers."),
        ],
    }

    for level in levels:
        for title, description in bugs_by_level[level.number]:
            db.add(Bug(
                level_id=level.id,
                title=title,
                description=description,
            ))

    db.commit()
