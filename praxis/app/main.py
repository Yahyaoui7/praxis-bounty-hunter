"""
Praxis POC — Main Application Entry Point

This file creates the FastAPI application and wires everything together:
    1. Static file serving  (CSS, JS)
    2. Jinja2 templates     (HTML pages)
    3. Route registration   (auth, dashboard, challenges)
    4. Database init        (create tables + seed data on startup)

Run locally:
    uvicorn app.main:app --reload

Run with Docker:
    docker build -t praxis .
    docker run -p 8000:8000 praxis
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file before anything else
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Create the FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Praxis — Bounty Hunter Arena",
    description="A bounty-hunting platform for 1337 students (Phase 1 POC)",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Paths — resolve relative to the project root (one level up from app/)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # praxis/

# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript)
# Served at /static/css/style.css, /static/js/app.js, etc.
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ---------------------------------------------------------------------------
# Jinja2 templates
# Used by routes to render HTML: templates.TemplateResponse("login.html", ...)
# ---------------------------------------------------------------------------
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ---------------------------------------------------------------------------
# Register route modules
# Each module adds its own endpoints to the application.
# ---------------------------------------------------------------------------
from app.routes import auth, dashboard, challenges, admin  # noqa: E402

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(challenges.router)
app.include_router(admin.router)


# ---------------------------------------------------------------------------
# Startup event — initialize the database
# ---------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    """
    Called once when the application starts.
    - Creates database tables and seeds example data if the DB is empty.
    - Validates Intra 42 OAuth configuration and logs status (no secrets printed).
    """
    from app.database import init_db
    from app.services.intra_service import validate_intra_config

    init_db()

    # Validate OAuth config at startup.
    # Warns if INTRA_REDIRECT_URI is localhost (breaks multi-PC LAN usage).
    # Logs presence of credentials without printing secret values.
    validate_intra_config()
