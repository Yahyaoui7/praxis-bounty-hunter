# Bounty Hunter Arena — Technical POC

## 1. Goal

The goal of this project is to build a small technical system for the Praxis / Integration Week.

Students will receive a buggy project and work in teams to fix bugs.

The technical system should simulate a real software project:

```text
Student
   │
   ▼
Git Repository
   │
   ▼
Push
   │
   ▼
CI Pipeline
   │
   ▼
Docker
   │
   ▼
Automated Tests
   │
   ▼
PASS / FAIL
```

The first goal is **not** to build the complete competition system.

The first goal is to prove that:

```text
Git → CI → Docker → Tests → Result
```

works correctly.

---

# 2. Development Plan

## Phase 1 — Local POC

First, build and test everything on your own computer.

### Objectives

* Create a small application.
* Create automated tests.
* Create a Docker image.
* Run the tests inside Docker.
* Create a CI configuration.
* Push the project to GitLab.
* Make the CI pipeline run automatically.

### Expected result

When you push:

```bash
git push
```

the system should automatically:

```text
1. Receive the commit
2. Start CI
3. Build/test the project
4. Run automated tests
5. Return PASS or FAIL
```

---

# 3. Project Architecture

Start with this structure:

```text
bounty-hunter-poc/
│
├── app/
│   ├── __init__.py
│   └── main.py
│
├── tests/
│   └── test_main.py
│
├── Dockerfile
├── .gitignore
├── .gitlab-ci.yml
└── README.md
```

Later, the architecture can become bigger.

---

# 4. File Responsibilities

## `app/main.py`

This is the application code.

For the first POC, keep it very simple.

Example:

```python
def add(a, b):
    return a + b
```

The important thing is not the application itself.

The important part is the **workflow around the application**.

---

## `tests/test_main.py`

This contains automated tests.

Example:

```python
from app.main import add


def test_add():
    assert add(2, 3) == 5
```

The test should fail if the application contains a bug.

For example:

```python
def add(a, b):
    return a - b
```

Then:

```text
TEST FAILED
```

This is exactly what you need for the Bounty Hunter system.

---

# 5. Dockerfile

The Dockerfile defines the environment used to run the project.

Example:

```dockerfile
FROM python:3.12

WORKDIR /app

COPY . .

RUN pip install pytest

CMD ["pytest", "-v"]
```

The important idea is:

```text
Dockerfile
    │
    ▼
Docker Image
    │
    ▼
Container
    │
    ▼
Tests
```

---

# 6. Build the Docker Image

From the project directory:

```bash
docker build -t bounty-hunter-poc .
```

Check the image:

```bash
docker images
```

You should see:

```text
bounty-hunter-poc
```

---

# 7. Run the Tests with Docker

Run:

```bash
docker run --rm bounty-hunter-poc
```

You should see something similar to:

```text
================ test session starts ================

tests/test_main.py PASSED

================ 1 passed ================
```

This proves:

```text
Application
    ↓
Tests
    ↓
Docker
    ↓
PASS
```

---

# 8. Test a Failure

Change the application:

```python
def add(a, b):
    return a - b
```

Run:

```bash
docker build -t bounty-hunter-poc .
docker run --rm bounty-hunter-poc
```

Now the test should fail.

This is important because your competition needs both:

```text
PASS
FAIL
```

---

# 9. Git

Initialize Git:

```bash
git init
```

Add the files:

```bash
git add .
```

Create the first commit:

```bash
git commit -m "Initial POC"
```

Check the history:

```bash
git log --oneline
```

---

# 10. GitLab

Create a GitLab repository for the POC.

Then connect your local project:

```bash
git remote add origin <YOUR_GITLAB_REPOSITORY>
```

Push:

```bash
git branch -M main
git push -u origin main
```

Do not worry about the 1337 cluster yet.

First prove that GitLab receives your project.

---

# 11. GitLab CI

Create:

```text
.gitlab-ci.yml
```

Initial version:

```yaml
test:
  image: python:3.12

  script:
    - pip install pytest
    - pytest -v
```

The workflow becomes:

```text
git push
   │
   ▼
GitLab
   │
   ▼
CI Pipeline
   │
   ▼
Python Environment
   │
   ▼
pytest
   │
   ├── PASS
   │
   └── FAIL
```

---

# 12. Important: CI Runner

A CI configuration alone is not enough.

GitLab needs a machine that executes the CI job.

That machine is called a:

```text
GitLab Runner
```

Think about it like this:

```text
GitLab
  │
  │ "Run this pipeline"
  ▼
GitLab Runner
  │
  ├── Download project
  ├── Install dependencies
  ├── Run tests
  └── Return result
```

Before installing your own Runner, find out what infrastructure 1337 already provides.

Ask the school/infrastructure team:

> Do we have access to a GitLab Runner or CI infrastructure that can be used for a student project?

Also ask:

> Do we have access to a Kubernetes cluster for student projects?

Do **not** assume that the 1337 cluster is Kubernetes.

---

# 13. Phase 2 — Understand 1337 Infrastructure

After the local POC works, investigate the real school infrastructure.

You need to discover:

```text
GitLab
   │
   ├── Repository
   │
   └── CI Runner
          │
          └── Where does it execute?
```

Possible infrastructure:

### Option A — GitLab Runner

```text
GitLab
   │
   ▼
GitLab Runner
   │
   ▼
Docker
   │
   ▼
Tests
```

### Option B — Kubernetes

```text
GitLab
   │
   ▼
GitLab Runner
   │
   ▼
Kubernetes
   │
   ▼
Pod
   │
   ▼
Tests
```

### Option C — Other 1337 infrastructure

Use whatever infrastructure the school actually provides.

Do not build your architecture around an infrastructure you have not confirmed.

---

# 14. Phase 3 — Move the POC to the 1337 Infrastructure

Once you know how the school infrastructure works:

```text
Student Computer
       │
       │ git push
       ▼
     GitLab
       │
       ▼
   CI Runner
       │
       ▼
 Docker / Kubernetes
       │
       ▼
 Automated Tests
       │
       ▼
   PASS / FAIL
```

The goal is to make the same POC work remotely.

---

# 15. Phase 4 — Create the Real Competition Project

After the POC works, create the real architecture.

Recommended structure:

```text
bounty-hunter-arena/
│
├── game/
│   ├── src/
│   ├── tests/
│   ├── Dockerfile
│   └── README.md
│
├── ci/
│   └── templates/
│       └── test.yml
│
├── dashboard/
│   ├── backend/
│   └── frontend/
│
├── infrastructure/
│   ├── docker/
│   └── kubernetes/
│
├── scripts/
│   ├── setup.sh
│   └── reset.sh
│
├── .gitlab-ci.yml
└── README.md
```

Do **not** create all these directories now.

They belong to the later stages.

---

# 16. Dashboard — Later

A dashboard can eventually show:

```text
┌─────────────────────────────────────┐
│          BOUNTY HUNTER ARENA             │
├──────────┬──────────┬───────────────┤
│ Team     │ Status   │ Tests         │
├──────────┼──────────┼───────────────┤
│ Team 01  │ PASS     │ 15 / 15       │
│ Team 02  │ FAIL     │ 12 / 15       │
│ Team 03  │ RUNNING  │ ...           │
│ Team 04  │ PASS     │ 15 / 15       │
└──────────┴──────────┴───────────────┘
```

The dashboard should consume information from the CI system.

Do not build the dashboard before the CI pipeline works.

---

# 17. Final Architecture

The final system can look like:

```text
                         1337 INFRASTRUCTURE
                                  │
                                  ▼
                             ┌─────────┐
                             │ GitLab  │
                             └────┬────┘
                                  │
                              git push
                                  │
                                  ▼
                           ┌─────────────┐
                           │ CI Runner   │
                           └──────┬──────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │ Docker / K8s   │
                         └───────┬────────┘
                                 │
                                 ▼
                         ┌────────────────┐
                         │ Automated Tests│
                         └───────┬────────┘
                                 │
                         ┌───────┴───────┐
                         ▼               ▼
                       PASS             FAIL
                         │               │
                         └───────┬───────┘
                                 ▼
                            Dashboard
```

---

# 18. Development Order

Follow this exact order.

### Step 1

Create:

```text
bounty-hunter-poc/
```

### Step 2

Create:

```text
app/main.py
tests/test_main.py
```

### Step 3

Make the tests work locally:

```bash
pytest
```

### Step 4

Create:

```text
Dockerfile
```

### Step 5

Test with Docker:

```bash
docker build -t bounty-hunter-poc .
docker run --rm bounty-hunter-poc
```

### Step 6

Create the Git repository:

```bash
git init
git add .
git commit -m "Initial POC"
```

### Step 7

Push to GitLab.

### Step 8

Create:

```text
.gitlab-ci.yml
```

### Step 9

Verify that the CI pipeline runs.

### Step 10

Understand which Runner executes the pipeline.

### Step 11

Ask 1337 about the available cluster / CI infrastructure.

### Step 12

Move the POC to the 1337 infrastructure.

### Step 13

Only then build the real Bounty Hunter Arena.

### Step 14

Add dashboard / monitoring.

---

# 19. What NOT to Do Yet

Do not start with:

```text
❌ Kubernetes
❌ Complex dashboard
❌ Authentication system
❌ Scoring system
❌ Multiple servers
❌ Microservices
❌ Custom CI Runner
```

First prove:

```text
Git
 ↓
CI
 ↓
Docker
 ↓
Tests
 ↓
PASS / FAIL
```

If this works, you have the foundation of the whole system.

---

# 20. First Milestone

The first milestone is:

> **A student pushes code to GitLab and automatically receives a PASS or FAIL result from automated tests.**

When this works reliably, the next question is:

> **Where should the CI Runner execute — local machine, 1337 infrastructure, Docker server, or Kubernetes?**

That decision should be based on the infrastructure provided by 1337.
