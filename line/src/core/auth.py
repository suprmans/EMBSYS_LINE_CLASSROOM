import os

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer()


def require_lecturer(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
):
    token = os.environ.get("LECTURER_TOKEN", "")
    if not token or credentials.credentials != token:
        raise HTTPException(status_code=401, detail="Invalid or missing lecturer token")
    return credentials.credentials
