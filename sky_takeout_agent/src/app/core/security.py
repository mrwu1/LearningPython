from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password:str)->str:
    """使用 bcrypt 生成单向安全加盐哈希"""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes,salt).decode("utf-8")

def verify_password(plain_password:str,hashed_password:str)->bool:
    """校验明文密码与哈希值是否匹配"""
    return bcrypt.checkpw(plain_password.encode("utf-8"),hashed_password.encode("utf-8"))

def create_access_token(data:dict,expires_delta:timedelta|None = None)->str:
    """生成带有过期时间与载荷 (Payload) 的 JWT 访问令牌"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token:str)->dict:
    """解码并校验 JWT 令牌，过期或被篡改时抛出 jwt.PyJWTError"""
    return jwt.decode(token,settings.JWT_SECRET_KEY, algorithms=settings.JWT_ALGORITHM)

 # algorithms 原理解析：
 #      • jwt.encode 接收单数 algorithm="HS256"。
 #      • 但 jwt.decode 为了防范黑客伪造不加密的 "none" 算法攻击（著名的 Algorithm Confusion Attack），强制要求传入复数
 #      algorithms，且值必须是列表（白名单）！