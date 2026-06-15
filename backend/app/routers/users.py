from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.user import (
    UserCreateRequest,
    UserDeleteResponse,
    UserListResponse,
    UserPasswordResetRequest,
    UserPublic,
    UserStatusUpdateRequest,
)
from app.services.user_service import UserService


router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("", response_model=UserListResponse)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserListResponse:
    return UserListResponse(
        items=[UserPublic.model_validate(user) for user in UserService(db).list_users()]
    )


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserPublic:
    try:
        user = UserService(db).create_user(
            actor=current_user,
            email=payload.email,
            username=payload.username,
            password=payload.password,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return UserPublic.model_validate(user)


@router.patch("/{user_id}", response_model=UserPublic)
def update_user_status(
    user_id: UUID,
    payload: UserStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserPublic:
    try:
        user = UserService(db).update_status(
            actor=current_user,
            user_id=user_id,
            status=payload.status,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return UserPublic.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=UserPublic)
def reset_password(
    user_id: UUID,
    payload: UserPasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserPublic:
    try:
        user = UserService(db).reset_password(
            actor=current_user,
            user_id=user_id,
            password=payload.password,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return UserPublic.model_validate(user)


@router.delete("/{user_id}", response_model=UserDeleteResponse)
def delete_user(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserDeleteResponse:
    try:
        UserService(db).delete_user(
            actor=current_user,
            user_id=user_id,
            request=request,
        )
    except ValueError as exc:
        error_detail = str(exc)
        error_status = (
            status.HTTP_404_NOT_FOUND
            if error_detail == "User not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=error_status, detail=error_detail) from exc
    return UserDeleteResponse(status="deleted")
