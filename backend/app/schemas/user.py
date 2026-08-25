from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=10, max_length=128)
    full_name: str
    # Deliberately a plain str, not a Literal["buyer","finance"]: any value
    # other than "buyer"/"finance" (including "admin") is silently coerced
    # to "buyer" in auth.py::register rather than rejected with a 422 - the
    # same "never trust client input for privilege, degrade gracefully
    # instead of erroring" pattern this codebase uses elsewhere, and it
    # preserves the pre-existing self-registration contract (a client
    # requesting "admin" still gets a 201 with role="buyer", not a 422).
    role: str = "buyer"


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RoleUpdate(BaseModel):
    role: str
