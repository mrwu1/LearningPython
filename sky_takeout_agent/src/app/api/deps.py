from typing import AsyncGenerator, Annotated

import jwt
from fastapi import HTTPException,status
from fastapi.params import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token


async def get_db()->AsyncGenerator[AsyncSession,None]:
    """
            依赖注入：获取数据库异步会话，请求结束自动释放/回滚
            对标 Spring 的 @Transactional + 自动归还 HikariCP 连接
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise

# ➡️  导出类型别名 ‼️‼️
SessionDep = Annotated[AsyncSession,Depends(get_db)]
# 使用 Annotated 包装依赖，使得 Controller 层无需再反复写 Depends(get_current_user)

# 自动从 HTTP 请求头的 Authorization: Bearer <token> 中提取凭证
bearer_scheme = HTTPBearer()

async def get_current_user(credentials:HTTPAuthorizationCredentials=Depends(bearer_scheme))->dict:
    """
            依赖注入：从 Header 提取并解码 JWT，获取当前登录用户信息
            对标 Spring Security 的 OncePerRequestFilter -> SecurityContextHolder
    """
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id:str = payload.get("sub")
        role: str = payload.get("role")
        if not user_id or not role:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的身份凭证 (Missing Claims)")
        return {"user_id": user_id, "username": payload.get("username"), "role": role}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌已过期，请重新登录")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

# ➡️ 导出用户依赖类型别名 ‼️‼️
UserDep = Annotated[dict,Depends(get_current_user)]

# 使用 Annotated 包装依赖，使得 Controller 层无需再反复写 Depends(get_current_user)

# 这是整个设计中最精妙的地方，它对标 Spring 的 @PreAuthorize  ✅✅✅
def check_role(required_role: str):
    """
        高阶依赖工厂：RBAC 权限守卫
        对标 Spring Security 的 @PreAuthorize("hasRole('ADMIN')")
        return: 接收目标角色，返回一个具体的依赖校验协程
    """

    async def role_evaluator(current_user: UserDep) -> dict:
        if current_user.get("role") != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权操作：需要 [{required_role}] 权限角色"
            )
        return current_user

    return role_evaluator

class RequestContext:
        """请求上下文门面：聚合当前请求所需的所有核心基建资源"""
        def __init__(
            self,
            user: UserDep,
            session: SessionDep,
            # redis: RedisDep (若需要也可塞进来)
        ):
            self.user = user
            self.session = session
# 导出这个门面上下文类型
ContextDep = Annotated[RequestContext, Depends(RequestContext)]