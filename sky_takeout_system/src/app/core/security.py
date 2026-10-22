from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt

from app.core.config import settings


def get_password_hash(password:str)->str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(plain_password, hashed_password):

    try:
        pwd_bytes = plain_password.encode("utf-8")
        salt_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, salt_bytes)
    except:
        return False

def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
            生成带有签名和有效期的 JWT Bearer Token。
            标准载荷包含：sub (用户标识/ID), role (角色), exp (过期时间戳), iss (签发方)。
            """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "iss": settings.APP_NAME
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt

def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithm=[settings.JWT_ALGORITHM]
    )
