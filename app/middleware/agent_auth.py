from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.status import HTTP_401_UNAUTHORIZED

from app.core.security import is_valid_agent_basic_auth


class AgentBasicAuthMiddleware(BaseHTTPMiddleware):
    protected_prefixes = ("/api/v1/agents", "/api/v1/agent-tasks", "/api/v1/agent-control")

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(self.protected_prefixes):
            if not is_valid_agent_basic_auth(request.headers.get("Authorization")):
                return JSONResponse(
                    status_code=HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or missing agent credentials."},
                    headers={"WWW-Authenticate": "Basic"},
                )

        return await call_next(request)
