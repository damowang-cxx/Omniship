from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserPublic


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthUserResponse(BaseModel):
    user: UserPublic


class LogoutResponse(BaseModel):
    status: str

