from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import AuthUserResponse, LoginRequest, LogoutResponse
from app.schemas.user import UserPublic
from app.services.auth_service import AuthError, AuthService


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=AuthUserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthUserResponse:
    service = AuthService(db)
    try:
        user, token = service.login(payload.email, payload.password, request)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_hours * 3600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    return AuthUserResponse(user=UserPublic.model_validate(user))


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="integrer_session"),
) -> LogoutResponse:
    AuthService(db).logout(session_token, request)
    response.delete_cookie(key=get_settings().auth_cookie_name, httponly=True, samesite="lax")
    return LogoutResponse(status="ok")


@router.get("/me", response_model=AuthUserResponse)
def me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    return AuthUserResponse(user=UserPublic.model_validate(current_user))

