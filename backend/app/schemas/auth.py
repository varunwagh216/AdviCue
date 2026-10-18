from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserInfo(BaseModel):
    id: str
    name: str
    email: str
    role: str


class AuthResponse(BaseModel):
    user: UserInfo
    csrf_token: str
