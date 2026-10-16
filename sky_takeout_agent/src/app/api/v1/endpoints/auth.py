from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.api.deps import UserDep
from app.core.security import create_access_token

router = APIRouter(tags=["认证中心"])

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login", summary="用户登录签发 Token")
async def login(req: LoginRequest):
    # 模拟外卖平台两类用户验证：管理员与普通骑手
    if req.username == "admin" and req.password == "admin123":
        user_role = "ADMIN"
    elif req.username == "rider" and req.password == "rider123":
        user_role = "RIDER"
    else:
        raise HTTPException(status_code=400, detail="用户名或密码错误")

    token = create_access_token({"sub": req.username, "username": req.username, "role": user_role})
    return {"access_token": token, "token_type": "bearer", "role": user_role}

@router.get("/me", summary="获取当前登录用户信息")
async def read_current_user(user: UserDep):
    return {"message": "认证成功", "current_user": user}
