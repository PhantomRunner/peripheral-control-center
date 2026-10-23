"""Browser-origin and short-lived session protection for local API mutations."""

import hashlib
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


class LocalSession(BaseModel):
    token: str
    expires_in_seconds: int


@dataclass(frozen=True)
class _Session:
    origin: str
    expires: float


class SessionStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()
        self.lifetime_seconds = 1800

    def issue(self, origin: str) -> LocalSession:
        token = secrets.token_urlsafe(32)
        with self._lock:
            now = self._clock()
            self._sessions = {key: value for key, value in self._sessions.items() if value.expires > now}
            if len(self._sessions) >= 128:
                del self._sessions[next(iter(self._sessions))]
            self._sessions[self._key(token)] = _Session(origin, now + self.lifetime_seconds)
        return LocalSession(token=token, expires_in_seconds=self.lifetime_seconds)

    def valid(self, token: str, origin: str) -> bool:
        if not 1 <= len(token) <= 128:
            return False
        with self._lock:
            session = self._sessions.get(self._key(token))
            return session is not None and session.origin == origin and session.expires > self._clock()

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


def local_origin(request: Request, *, required: bool) -> str:
    # Use the actual Host forwarded unchanged by Vite, never X-Forwarded-Host.
    origin = f"http://{request.headers.get('host', '')}"
    supplied = request.headers.get("origin")
    if supplied != origin and (required or supplied is not None):
        raise HTTPException(403, "A same-origin request is required.")
    if request.headers.get("sec-fetch-site", "same-origin") != "same-origin":
        raise HTTPException(403, "A same-origin request is required.")
    if request.headers.get("x-pcc-client") != "web":
        raise HTTPException(403, "A local API client header is required.")
    return origin


class LocalSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, sessions: SessionStore) -> None:
        super().__init__(app)
        self.sessions = sessions

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        api = request.url.path == "/api" or request.url.path.startswith("/api/")
        if api and request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                origin = local_origin(request, required=True)
                if not self.sessions.valid(request.headers.get("x-pcc-session", ""), origin):
                    raise HTTPException(401, "Local session is missing or expired.")
                if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                    raise HTTPException(415, "An application/json request is required.")
            except HTTPException as error:
                return JSONResponse({"detail": error.detail}, status_code=error.status_code, headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        if api:
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response
