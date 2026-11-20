from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_session, require_admin
from app.core.config import get_settings
from app.db.models import User, UserSession
from app.db.session import get_db
from app.schemas.auth import AuthenticatedUser, AuthUserResponse, ImpersonationRequest, LoginRequest, LogoutResponse
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
    return AuthUserResponse(user=AuthenticatedUser.model_validate(user))


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
def me(session: UserSession = Depends(get_current_session)) -> AuthUserResponse:
    impersonating = session.impersonated_user_id is not None
    account = session.impersonated_user if impersonating else session.user
    if account is None:
        raise HTTPException(status_code=403, detail="Customer account is unavailable")
    user = AuthenticatedUser.model_validate(account)
    user.impersonating = impersonating
    if impersonating:
        # Keep the return control reachable if the customer is disabled or changes role.
        # Data endpoints still validate the customer's active status and role.
        user.role = "user"
    return AuthUserResponse(user=user)


@router.post("/impersonation", response_model=AuthUserResponse)
def start_impersonation(
    payload: ImpersonationRequest, request: Request,
    db: Session = Depends(get_db),
    session: UserSession = Depends(get_current_session),
    _: User = Depends(require_admin),
) -> AuthUserResponse:
    try:
        target = AuthService(db).start_impersonation(session, payload.userId, request)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = AuthenticatedUser.model_validate(target)
    user.impersonating = True
    return AuthUserResponse(user=user)


@router.delete("/impersonation", response_model=AuthUserResponse)
def stop_impersonation(
    request: Request, db: Session = Depends(get_db),
    session: UserSession = Depends(get_current_session),
) -> AuthUserResponse:
    try:
        admin = AuthService(db).stop_impersonation(session, request)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return AuthUserResponse(user=AuthenticatedUser.model_validate(admin))

