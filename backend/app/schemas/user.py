from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPublic(BaseModel):
    id: UUID
    email: EmailStr
    username: str
    role: str
    status: str
    balance: Decimal
    payer_company_name: str | None = Field(default=None, alias="payerCompanyName")
    payer_address_info: str | None = Field(default=None, alias="payerAddressInfo")
    last_login_at: datetime | None = Field(default=None, alias="lastLoginAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UserListResponse(BaseModel):
    items: list[UserPublic]

    model_config = ConfigDict(populate_by_name=True)


class UserCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class UserStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


class UserPasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class UserPayerUpdateRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=255, alias="companyName")
    address_info: str = Field(min_length=1, max_length=2000, alias="addressInfo")

    model_config = ConfigDict(populate_by_name=True)


class UserDeleteResponse(BaseModel):
    status: str
