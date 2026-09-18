import os
import tarfile
import tempfile
import subprocess
import shutil
import time
from dataclasses import dataclass
from typing import Optional

from app.models import Team, Bug, Level
from app.services.gitlab_service import get_latest_commit_sha, download_repository_archive

@dataclass
class EvaluationResult:
    status: str
    passed: bool
    score: int
    exit_code: Optional[int]
    stdout: str
    stderr: str
    execution_time: float
    commit_sha: Optional[str]

class EvaluationError(Exception):
    pass

def evaluate_submission(team: Team, bug: Bug, level: Level) -> EvaluationResult:
    """
    Evaluates a team's submission for a given bug.
    Designed so it can be called synchronously now, or by an async Celery worker later.
    """
    # 1. Fetch latest commit SHA
    if not team.gitlab_project_id:
        return _fail_result("Team does not have a GitLab repository linked.", status="error")
        
    try:
        commit_sha = get_latest_commit_sha(team.gitlab_project_id)
    except Exception as e:
        return _fail_result(f"Failed to fetch commit from GitLab: {e}", status="error")
        
    if not commit_sha:
        return _fail_result("No commits found in the repository.", status="error")

    start_time = time.time()
    
    # 2. Setup temporary workspace
    with tempfile.TemporaryDirectory() as workspace_dir:
        archive_path = os.path.join(workspace_dir, "repo.tar.gz")
        extract_path = os.path.join(workspace_dir, "student_code")
        
        try:
            download_repository_archive(team.gitlab_project_id, commit_sha, archive_path)
        except Exception as e:
            return _fail_result(f"Failed to download repository: {e}", status="error", commit_sha=commit_sha)
            
        os.makedirs(extract_path, exist_ok=True)
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=extract_path)
            # GitLab tarball often contains a top-level directory (project-name-commit-sha)
            # Find the actual code directory
            extracted_dirs = os.listdir(extract_path)
            if len(extracted_dirs) == 1 and os.path.isdir(os.path.join(extract_path, extracted_dirs[0])):
                student_code_dir = os.path.join(extract_path, extracted_dirs[0])
            else:
                student_code_dir = extract_path
        except Exception as e:
            return _fail_result(f"Failed to extract repository: {e}", status="error", commit_sha=commit_sha)

        # 3. Prepare tests
        # In a real scenario, tests would be completely separate.
        # For the POC, we look in tests/evaluation/level_X/test_bug_Y.py
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        official_tests_dir = os.path.join(project_root, "tests", "evaluation", f"level_{level.number}")
        
        if not os.path.exists(official_tests_dir):
            return _fail_result(f"Official tests not found for level {level.number}", status="error", commit_sha=commit_sha)
            
        # We'll map the tests dir into the container.
        
        # 4. Run Docker container
        python_image = os.getenv("EVALUATOR_IMAGE", "praxis-evaluator:latest")
        
        # Ensure we don't use shell=True. The command is a list of arguments.
        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--cpus", "0.5",
            "-m", "128m",
            "--pids-limit", "50",
            "--cap-drop=ALL",
            "--read-only",
            "--tmpfs", "/tmp",
            "-v", f"{student_code_dir}:/workspace:ro",
            "-v", f"{official_tests_dir}:/tests:ro",
            python_image,
            "pytest", f"/tests/test_bug_{bug.id}.py"
        ]
        
        try:
            # Run the command with a strict timeout
            process = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=15.0, # 15 seconds max
                shell=False   # STRICT: Do not use shell=True
            )
            
            execution_time = time.time() - start_time
            passed = process.returncode == 0
            
            return EvaluationResult(
                status="passed" if passed else "failed",
                passed=passed,
                score=100 if passed else 0,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                execution_time=execution_time,
                commit_sha=commit_sha
            )
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            return EvaluationResult(
                status="timeout",
                passed=False,
                score=0,
                exit_code=124, # Standard timeout exit code
                stdout=e.stdout.decode() if e.stdout and isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=e.stderr.decode() if e.stderr and isinstance(e.stderr, bytes) else (e.stderr or "Execution timed out."),
                execution_time=execution_time,
                commit_sha=commit_sha
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return _fail_result(f"Docker execution error: {e}", status="error", commit_sha=commit_sha, exec_time=execution_time)


def _fail_result(msg: str, status: str = "failed", commit_sha: Optional[str] = None, exec_time: float = 0.0) -> EvaluationResult:
    return EvaluationResult(
        status=status,
        passed=False,
        score=0,
        exit_code=1,
        stdout="",
        stderr=msg,
        execution_time=exec_time,
        commit_sha=commit_sha
    )
