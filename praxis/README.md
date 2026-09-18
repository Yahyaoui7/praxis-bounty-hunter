# Praxis — Bounty Hunter Arena (Phase 1 POC)

A local web application for the **1337 Integration Week** bounty-hunting competition.

Teams of students log in, progress through levels of bugs, earn points, and unlock the next level after solving all 5 bugs in the current level.

> **This is a Phase 1 POC.** It runs locally with fake authentication and simulated bug checking. The future architecture will integrate GitLab, CI/CD, Docker environments, and Kubernetes.

---

## What the POC Does

```text
Student opens http://localhost:8000
        │
        ▼
    Login Page  ──→  POST /login  ──→  Session cookie set
        │
        ▼
    Dashboard  ──→  Team name, Level 0, 0/5 bugs, Score 0
        │
        ▼
  "Start Challenge"
        │
        ▼
  Challenge Page  ──→  5 bugs for the current level
        │
        ▼
  "Check Solution"  ──→  POST /challenge/check/{bug_id}
        │
        ├── Bug solved ✅  →  +100 points
        │
        └── 5/5 bugs solved?  →  Level up! Unlock next level
```

---

## Levels

| Level | Name                    | Bugs | Points |
|-------|-------------------------|------|--------|
| 0     | Introduction / Tutorial | 5    | 500    |
| 1     | The Basics              | 5    | 500    |
| 2     | Getting Harder          | 5    | 500    |
| 3     | The Final Boss          | 5    | 500    |
| **Total** |                     | **20** | **2000** |

- Every team starts at **Level 0** with **score 0**.
- Solve all 5 bugs in a level → automatically advance to the next level.
- After completing Level 3 → "Congratulations! You completed all levels."
- There is no Level 4.

---

## Project Architecture

```text
praxis/
├── app/                        # Backend (FastAPI + SQLAlchemy)
│   ├── __init__.py
│   ├── main.py                 # App entry point, routes, startup
│   ├── database.py             # SQLite engine, sessions, seed data
│   ├── models.py               # Team, Level, Bug, TeamBug models
│   └── routes/
│       ├── __init__.py
│       ├── auth.py             # Login / logout / session cookies
│       ├── dashboard.py        # Team dashboard (progress, score)
│       └── challenges.py       # Bug list + solve bugs + level up
│
├── templates/                  # Frontend (Jinja2 HTML templates)
│   ├── base.html               # Shared layout (navbar, footer)
│   ├── login.html              # Login form
│   ├── dashboard.html          # Team progress dashboard
│   └── challenge.html          # Bug list with "Check Solution" buttons
│
├── static/                     # Static assets
│   ├── css/style.css           # Dark hacker-themed stylesheet
│   └── js/app.js               # AJAX bug checking, UI updates
│
├── tests/
│   └── test_app.py             # Full test suite (pytest)
│
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker support
├── .env.example                # Example environment variables
├── .gitignore
└── README.md                   # This file
```

---

## How to Run Locally

### 1. Create a virtual environment

```bash
cd praxis
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the application

```bash
uvicorn app.main:app --reload
```

### 4. Open the application

Go to: **http://localhost:8000**

### 5. Log in

| Username | Password      |
|----------|---------------|
| team01   | password123   |
| team02   | password123   |

---

## How to Run with Docker

```bash
docker build -t praxis .
docker run -p 8000:8000 praxis
```

Then open: **http://localhost:8000**

---

## How to Deploy to Kubernetes (Production)

Praxis is fully configured to run on a Kubernetes cluster (like the 1337 infrastructure). It uses PostgreSQL for persistence, K8s Jobs for evaluations, and Ingress for stable routing.

### 1. Configure Secrets and Environment
Edit `k8s/secret.yaml` and `k8s/configmap.yaml` to set your passwords, GitLab tokens, and OAuth keys.
Ensure `INTRA_REDIRECT_URI` in the ConfigMap matches your Ingress hostname (e.g., `https://praxis.1337.ma/auth/callback`).

### 2. Apply Manifests
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/networkpolicy.yaml
```

### 3. Build and Push the Evaluator Image
If you haven't already, push the evaluator image to your cluster's registry:
```bash
cd docker/evaluator
docker build -t praxis-evaluator:latest .
# Tag and push to your registry
# docker tag praxis-evaluator:latest your-registry/praxis-evaluator:latest
# docker push your-registry/praxis-evaluator:latest
```
*(Make sure to update `EVALUATOR_IMAGE` in `k8s/configmap.yaml` if you push it somewhere else).*

---

## How to Run Tests

```bash
cd praxis
pytest tests/ -v
```

The test suite covers:
- Initial state (Level 0, score 0 for all teams)
- Authentication (login, logout, access control)
- Bug solving (solve → +100 points)
- Duplicate prevention (same bug twice → no extra points)
- Level protection (cannot solve bugs from another level)
- Level progression (5/5 → advance to next level)
- Final level (complete Level 3 → no Level 4)
- Team isolation (one team's progress doesn't affect another)

---

## Authentication (POC)

The POC uses **fake local authentication**:
- Credentials are stored in SQLite with SHA-256 hashed passwords.
- Sessions use signed cookies via `itsdangerous`.
- Two functions are designed to be easily replaced:
  - `verify_credentials()` — swap with LDAP/OAuth.
  - `get_current_team()` — swap with JWT/token verification.

**This is NOT production-ready authentication.** It exists only to simulate the login flow.

---

## How Levels and Bugs Work

1. Each level has exactly **5 bugs**.
2. When a team clicks "Check Solution" on a bug:
   - The server verifies the bug belongs to the team's current level.
   - The server checks the bug hasn't already been solved.
   - If valid, the bug is marked as solved and **100 points** are awarded.
3. When all 5 bugs in a level are solved:
   - `current_level` increments by 1.
   - The team sees the next level's bugs.
4. After completing Level 3:
   - `current_level` is set to 4 (beyond the max).
   - The dashboard and challenge page show a "Congratulations" message.

### Security

- The **server is the source of truth** for level and score.
- Students cannot skip levels, solve bugs from other levels, or earn double points.
- A `UniqueConstraint` on `(team_id, bug_id)` prevents duplicate records.

---

## Database Design

```text
Team                    Level                  Bug
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ id           │       │ id           │       │ id           │
│ name         │       │ number       │       │ level_id ────┼──→ Level.id
│ username     │       │ name         │       │ title        │
│ password_hash│       │ description  │       │ description  │
│ current_level│       │ required_bugs│       └──────────────┘
│ score        │       └──────────────┘
└──────────────┘

TeamBug (junction table)
┌──────────────────────────────┐
│ id                           │
│ team_id ──→ Team.id          │
│ bug_id  ──→ Bug.id           │
│ solved                       │
│ solved_at                    │
│ UNIQUE(team_id, bug_id)      │
└──────────────────────────────┘
```

---

## What Will Be Added Later

The following features belong to **Phase 2+** and are NOT implemented in this POC:

| Feature | Description |
|---------|-------------|
| **GitLab** | Each team gets a Git repository with the buggy project. |
| **GitLab CI** | Pipelines run automatically on `git push`. |
| **GitLab Runner** | Executes CI jobs (tests) for each team's submission. |
| **Docker environments** | Isolated containers per team for running code. |
| **Kubernetes** | Orchestrates team environments at scale. |
| **1337 authentication** | LDAP/Active Directory integration for real student login. |

## Automated Code Evaluation (Phase 3 POC)

We have implemented an initial automated code evaluation system without requiring Kubernetes.

### Architecture
```text
Student PC
    ↓
Praxis Web App (Submit Solution)
    ↓
Praxis Evaluation Service
    ↓
GitLab (fetch latest commit archive)
    ↓
Docker (isolated transient container)
    ↓
Run deterministic pytest on code
    ↓
Praxis DB (store Evaluation result + score)
```

### Security Model
The student's code runs in a Docker container with strict constraints:
- `cap-drop=ALL` and strict PIDs limits (e.g. 50).
- Limited CPU (`0.5`) and Memory (`128m`).
- Network disabled (`--network none`).
- Read-only workspace and official tests directories.
- Strict 15-second execution timeout.
- Host processes (`subprocess.run`) never use `shell=True`.

### How to test locally and on LAN
1. Build the evaluator image:
   ```bash
   cd docker/evaluator
   docker build -t praxis-evaluator:latest .
   ```
2. Start the server (bind to `0.0.0.0` for LAN access):
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
3. The server can be accessed by any other PC on the LAN (e.g., `http://10.12.1.10:8000`).

### Current Limitations
- Single concurrency (evaluations run synchronously via FastAPI request). In the future, this will be offloaded to an asynchronous task queue (e.g., Celery) and eventually Kubernetes.
- Does not yet use AI for ambiguous test results.

### Evaluation Execution Flow

- Local Dev (`EVAL_BACKEND=docker`): Uses local `docker run` synchronously.
- Production (`EVAL_BACKEND=kubernetes`): Spawns a Kubernetes `Job` dynamically via the Python K8s Client.

### Future flow

```text
Student pushes code
      ↓
GitLab receives commit
      ↓
CI Pipeline triggers
      ↓
GitLab Runner executes tests
      ↓
Praxis receives PASS/FAIL result
      ↓
Update TeamBug (solved = true/false)
      ↓
5/5 bugs solved? → Unlock next level
```

## GitLab Integration — Phase 2 Foundation

This project includes the foundation for Phase 2: Automatic GitLab Repository Creation.

When a team is registered through the secure admin interface (`/admin/team/new`), Praxis will automatically call the GitLab API to provision a dedicated, **private** repository for that team.

### Why this approach?
- **No Client Setup:** Students do not need to install GitLab Runner on their machines.
- **Isolation:** Each team gets their own repository. GitLab's permissions ensure that Team A cannot access Team B's repository.
- **Security:** The GitLab access token is stored **only** on the backend (`.env`), never exposed to the frontend browser.

### How it works
1. **Admin Creation:** An admin fills out the `/admin/team/new` form.
2. **Praxis (Backend):** Creates the database record and sends a secure API request to GitLab.
3. **GitLab API:** Provisions the private repository and returns the Project ID and URL.
4. **Praxis (Backend):** Stores the Project ID in the SQLite database and displays the link on the team's dashboard.

### Future CI/CD Flow
While currently only the repository creation is implemented, this sets the stage for the full automated testing loop:
`Student -> git push -> GitLab CI -> GitLab Runner -> Docker -> Tests -> Praxis -> Score`

---

## Design Decisions

1. **SQLite for POC** — No external database server needed. Easy to switch to PostgreSQL later by changing `DATABASE_URL`.
2. **Signed cookies** — Simpler than JWT for a local POC. Provides session security without extra infrastructure.
3. **Deterministic bug solving** — "Check Solution" always succeeds in Phase 1. This makes testing predictable.
4. **Level number as integer** — `current_level` stores 0–3 (or 4 for completion). Simple and efficient.
5. **AJAX bug checking** — The challenge page doesn't reload when solving a bug. Better user experience.
