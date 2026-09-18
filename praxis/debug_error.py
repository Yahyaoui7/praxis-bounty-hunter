import os
from fastapi.testclient import TestClient
from app.main import app

os.environ["INTRA_CLIENT_ID"] = "u-fake"
os.environ["INTRA_CLIENT_SECRET"] = "s-fake"
os.environ["INTRA_REDIRECT_URI"] = "http://localhost:8000/auth/callback"

client = TestClient(app)

try:
    response = client.get("/auth/callback?code=fakecode")
    print("Status:", response.status_code)
    print("Text:", response.text)
except Exception as e:
    import traceback
    traceback.print_exc()
