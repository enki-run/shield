from fastapi import Request, HTTPException
from app.middleware.cf_access import validate_cf_access_token
from app.core.config import get_settings


async def get_current_user(request: Request) -> dict:
    settings = get_settings()
    dev_mode = settings.environment != "production"
    token = request.cookies.get("CF_Authorization")
    try:
        claims = validate_cf_access_token(
            token,
            dev_mode=dev_mode,
            audience=settings.cf_access_aud,
            team_domain=settings.cf_access_team_domain,
        )
        return {"email": claims.get("email", "unknown"), "sub": claims.get("sub", "")}
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
