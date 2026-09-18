import os
import httpx


class GitLabServiceError(Exception):
    """Exception raised for errors during GitLab API calls."""

    pass


def create_team_repository(team_name: str) -> dict:
    """
    Creates a private GitLab repository for the team using the GitLab API.

    Args:
        team_name: The name of the team (used to generate project name)

    Returns:
        dict: Contains 'id', 'web_url', and 'path_with_namespace' of the new project.

    Raises:
        GitLabServiceError: If the API call fails or configuration is missing.
    """
    gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com").rstrip("/")
    gitlab_token = os.getenv("GITLAB_TOKEN")
    namespace_id = os.getenv("GITLAB_NAMESPACE_ID")

    if not gitlab_token or gitlab_token == "change-me":
        raise GitLabServiceError(
            "GitLab token is not configured or is invalid."
        )

    headers = {
        "PRIVATE-TOKEN": gitlab_token,
        "Content-Type": "application/json",
    }

    # Safe project name generation (e.g. "Team 01" -> "team-01-bounty-hunter")
    safe_name = team_name.lower().replace(" ", "-")
    project_name = f"{safe_name}-bounty-hunter"

    payload = {"name": project_name, "visibility": "private"}

    if namespace_id:
        payload["namespace_id"] = namespace_id

    api_endpoint = f"{gitlab_url}/api/v4/projects"

    try:
        # Use httpx to make the synchronous HTTP request
        with httpx.Client() as client:
            response = client.post(
                api_endpoint, headers=headers, json=payload, timeout=10.0
            )

            if response.status_code == 201:
                data = response.json()
                return {
                    "id": data.get("id"),
                    "web_url": data.get("web_url"),
                    "path_with_namespace": data.get("path_with_namespace"),
                }
            else:
                error_detail = response.text
                try:
                    error_detail = response.json().get(
                        "message", response.text
                    )
                except Exception:
                    pass
                raise GitLabServiceError(
                    f"GitLab API error (Status {response.status_code}): {error_detail}"
                )

    except httpx.RequestError as e:
        raise GitLabServiceError(f"HTTP Request failed: {str(e)}")


def get_latest_commit_sha(project_id: int, branch: str = "main") -> str:
    """
    Fetches the latest commit SHA for a project.
    """
    gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com").rstrip("/")
    gitlab_token = os.getenv("GITLAB_TOKEN")

    headers = (
        {"PRIVATE-TOKEN": gitlab_token}
        if gitlab_token and gitlab_token != "change-me"
        else {}
    )

    api_endpoint = f"{gitlab_url}/api/v4/projects/{project_id}/repository/commits/{branch}"

    try:
        with httpx.Client() as client:
            response = client.get(api_endpoint, headers=headers, timeout=10.0)
            if response.status_code == 200:
                return response.json().get("id")
            raise GitLabServiceError(
                f"GitLab API error (Status {response.status_code}): {response.text}"
            )
    except httpx.RequestError as e:
        raise GitLabServiceError(f"HTTP Request failed: {str(e)}")


def download_repository_archive(project_id: int, sha: str, dest_path: str):
    """
    Downloads the repository archive for a specific commit SHA to the dest_path.
    """
    gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com").rstrip("/")
    gitlab_token = os.getenv("GITLAB_TOKEN")

    headers = (
        {"PRIVATE-TOKEN": gitlab_token}
        if gitlab_token and gitlab_token != "change-me"
        else {}
    )

    api_endpoint = f"{gitlab_url}/api/v4/projects/{project_id}/repository/archive.tar.gz?sha={sha}"

    try:
        with httpx.Client() as client:
            with client.stream(
                "GET", api_endpoint, headers=headers, timeout=30.0
            ) as response:
                if response.status_code == 200:
                    with open(dest_path, "wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)
                else:
                    raise GitLabServiceError(
                        f"GitLab API error (Status {response.status_code}): {response.text}"
                    )
    except httpx.RequestError as e:
        raise GitLabServiceError(f"HTTP Request failed: {str(e)}")
