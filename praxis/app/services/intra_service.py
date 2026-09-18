"""
Intra 42 OAuth Service for Praxis.

IMPORTANT — Why localhost must NOT be used as redirect_uri in this deployment:
==============================================================================
"localhost" resolves to the machine where the BROWSER is running, not the server.

Deployment topology:
    Praxis server: 10.12.1.10:8000   ← uvicorn runs here, handles callbacks
    Student PC A:  10.12.9.2        ← only a browser, NO web server
    Student PC B:  10.12.9.3        ← only a browser, NO web server

If we configured redirect_uri=http://localhost:8000/auth/callback:
    1. Student on 10.12.9.2 clicks "Login with Intra"
    2. Intra 42 redirects their browser to: http://localhost:8000/auth/callback
    3. "localhost" for that student = 10.12.9.2 — which has NO server listening!
    4. Browser shows: "Connection refused". OAuth fails.

The correct redirect_uri=http://10.12.1.10:8000/auth/callback:
    1. Student on 10.12.9.2 clicks "Login with Intra"
    2. Intra 42 redirects their browser to: http://10.12.1.10:8000/auth/callback
    3. Browser connects to the Praxis server over the LAN — where Praxis is listening!
    4. Callback is handled. OAuth succeeds.

Future-proofing:
    Simply change INTRA_REDIRECT_URI in .env to:
        https://praxis.1337.ma/auth/callback
    No Python code needs to change.
"""

import os
import logging
import httpx
from urllib.parse import quote

logger = logging.getLogger(__name__)


class IntraServiceError(Exception):
    """Exception raised for errors during Intra 42 API calls."""
    pass


def validate_intra_config() -> bool:
    """
    Validate that all required Intra 42 OAuth environment variables are set.
    Called at application startup to catch misconfigurations early.

    Logs the configuration status WITHOUT printing secret values.

    Returns True if all required variables are present, False otherwise.
    """
    client_id = os.getenv("INTRA_CLIENT_ID")
    client_secret = os.getenv("INTRA_CLIENT_SECRET")
    redirect_uri = os.getenv("INTRA_REDIRECT_URI")

    missing = []
    if not client_id:
        missing.append("INTRA_CLIENT_ID")
    if not client_secret:
        missing.append("INTRA_CLIENT_SECRET")
    if not redirect_uri:
        missing.append("INTRA_REDIRECT_URI")

    if missing:
        logger.warning(
            "Intra 42 OAuth is NOT fully configured. Missing variables: %s. "
            "Login with Intra 42 will be unavailable.",
            ", ".join(missing)
        )
        return False

    # Log presence/value of redirect_uri (NOT a secret — it's the public callback URL)
    logger.info("Intra 42 OAuth configured. Redirect URI: %s", redirect_uri)

    # Warn if using an IP address or localhost - in Kubernetes this will break when pods move
    import re
    if "localhost" in redirect_uri or "127.0.0.1" in redirect_uri or re.search(r'\d+\.\d+\.\d+\.\d+', redirect_uri):
        logger.warning(
            "INTRA_REDIRECT_URI contains an IP address or localhost. "
            "In Kubernetes, this will BREAK OAuth when the pod is rescheduled to a different node. "
            "Set it to the public Ingress hostname, e.g.: https://praxis.1337.ma/auth/callback"
        )

    # Log that secrets are present but never log their values
    logger.info(
        "INTRA_CLIENT_ID: configured (length=%d). INTRA_CLIENT_SECRET: configured.",
        len(client_id)
    )
    return True


def get_intra_authorization_url() -> str:
    """
    Returns the URL to redirect the user to for Intra 42 OAuth authorization.

    The redirect_uri must point to the Praxis SERVER (e.g. http://10.12.1.10:8000/auth/callback),
    NOT to localhost. See module docstring for the full explanation.
    """
    client_id = os.getenv("INTRA_CLIENT_ID")
    redirect_uri = os.getenv("INTRA_REDIRECT_URI")

    if not client_id or not redirect_uri:
        raise IntraServiceError("Intra 42 OAuth credentials are not configured.")

    # URL-encode the redirect_uri to ensure it is safely embedded in the query string.
    # Without this, characters like ':' and '/' in the URI could be misinterpreted
    # by the Intra 42 authorization endpoint.
    encoded_redirect_uri = quote(redirect_uri, safe="")

    return (
        f"https://api.intra.42.fr/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={encoded_redirect_uri}"
        f"&response_type=code"
    )


def get_intra_token(code: str) -> str:
    """
    Exchanges the authorization code for an access token.

    The redirect_uri here MUST match exactly what was sent in the authorization request.
    Intra 42 uses it as a security check. We read it from INTRA_REDIRECT_URI.
    """
    client_id = os.getenv("INTRA_CLIENT_ID")
    client_secret = os.getenv("INTRA_CLIENT_SECRET")
    redirect_uri = os.getenv("INTRA_REDIRECT_URI")

    if not client_id or not client_secret or not redirect_uri:
        raise IntraServiceError("Intra 42 OAuth credentials are not configured.")

    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        # Must exactly match the redirect_uri registered in the Intra 42 app
        # and the one sent in the authorization request.
        "redirect_uri": redirect_uri,
    }

    try:
        with httpx.Client() as client:
            response = client.post(
                "https://api.intra.42.fr/oauth/token",
                data=payload,
                timeout=10.0,
            )
            if response.status_code == 200:
                return response.json().get("access_token")
            else:
                raise IntraServiceError(
                    f"Failed to get token (Status {response.status_code}): {response.text}"
                )
    except httpx.RequestError as e:
        raise IntraServiceError(f"HTTP Request failed: {str(e)}")


def get_intra_user_profile(access_token: str) -> dict:
    """Fetches the user's profile from Intra 42 using the access token."""
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        with httpx.Client() as client:
            response = client.get(
                "https://api.intra.42.fr/v2/me",
                headers=headers,
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "id": data.get("id"),
                    "login": data.get("login"),
                    "email": data.get("email"),
                    "first_name": data.get("first_name"),
                    "last_name": data.get("last_name"),
                }
            else:
                raise IntraServiceError(
                    f"Failed to fetch profile (Status {response.status_code}): {response.text}"
                )
    except httpx.RequestError as e:
        raise IntraServiceError(f"HTTP Request failed: {str(e)}")
