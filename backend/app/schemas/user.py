from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: str = "staff"
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str):
        value = value.strip()
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username may contain letters, numbers, hyphens and underscores")
        return value


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr | None = None


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: str


class PasswordReset(BaseModel):
    password: str = Field(min_length=10, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
