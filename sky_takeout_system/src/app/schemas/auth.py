from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username:str = Field(...,description="Username")
    password:str = Field(...,description="Password")

class TokenResponse(BaseModel):
    access_token:str
    token_type:str
    role:str
    user_identifier:str