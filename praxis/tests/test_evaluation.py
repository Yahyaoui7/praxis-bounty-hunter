import pytest
import os
from unittest.mock import patch, MagicMock
from app.models import Team, Bug, Level, Evaluation
from app.services.evaluation_service import evaluate_submission, EvaluationResult

@pytest.fixture
def mock_team():
    return Team(id=1, name="Test Team", gitlab_project_id=42)

@pytest.fixture
def mock_bug():
    return Bug(id=1, title="Test Bug")

@pytest.fixture
def mock_level():
    return Level(number=0, name="Intro")

@patch("app.services.evaluation_service.get_latest_commit_sha")
@patch("app.services.evaluation_service.download_repository_archive")
@patch("app.services.evaluation_service.tarfile.open")
@patch("app.services.evaluation_service.os.path.exists")
@patch("app.services.evaluation_service.subprocess.run")
def test_evaluate_submission_success(mock_run, mock_exists, mock_tar, mock_download, mock_get_sha, mock_team, mock_bug, mock_level):
    mock_get_sha.return_value = "abcdef123456"
    mock_exists.return_value = True
    
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "Test passed"
    mock_process.stderr = ""
    mock_run.return_value = mock_process
    
    result = evaluate_submission(mock_team, mock_bug, mock_level)
    
    assert result.passed is True
    assert result.status == "passed"
    assert result.score == 100
    assert result.commit_sha == "abcdef123456"

@patch("app.services.evaluation_service.get_latest_commit_sha")
@patch("app.services.evaluation_service.download_repository_archive")
@patch("app.services.evaluation_service.tarfile.open")
@patch("app.services.evaluation_service.os.path.exists")
@patch("app.services.evaluation_service.subprocess.run")
def test_evaluate_submission_failure(mock_run, mock_exists, mock_tar, mock_download, mock_get_sha, mock_team, mock_bug, mock_level):
    mock_get_sha.return_value = "abcdef123456"
    mock_exists.return_value = True
    
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stdout = "Test failed"
    mock_process.stderr = "AssertionError"
    mock_run.return_value = mock_process
    
    result = evaluate_submission(mock_team, mock_bug, mock_level)
    
    assert result.passed is False
    assert result.status == "failed"
    assert result.score == 0
    assert result.commit_sha == "abcdef123456"

def test_evaluate_no_gitlab_repo():
    team = Team(id=2, name="No Repo Team")
    bug = Bug(id=2)
    level = Level(number=0)
    
    result = evaluate_submission(team, bug, level)
    
    assert result.passed is False
    assert result.status == "error"
    assert "does not have a GitLab repository" in result.stderr
