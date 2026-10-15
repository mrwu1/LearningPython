### 场景设定：
#  处理用户注册或大模型提取出的脏数据信息，进行字段清洗与格式统一。


from pydantic import BaseModel, ValidationError, field_validator


class UserProfileClean(BaseModel):
    username: str

    # 校验名字
    @field_validator("username")
    @classmethod
    def santize_username(cls, v: str) -> str:
        cleaned: str = v.strip()
        if len(cleaned) < 3:
            raise ValueError("Username must be at least 3 characters long")
        return cleaned.lower()

    phone: str

    # 校验电话
    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # 先自动剔除字符串中的所有空格和横杠
        cleaned: str = v.replace(" ", "").replace("-", "")
        # 再校验是否为纯数字且长度为 11 位
        if not cleaned.isdigit() or len(cleaned) != 11:
            raise ValueError("Invalid phone number: must be 11 digits")
        return cleaned

    email: str

    # 校验邮箱
    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        cleaned: str = v.strip()
        if "@" not in cleaned or "." not in cleaned:
            raise ValueError("Invalid email address: must contain '@' and '.'")
        return cleaned.lower()


# 测试 1：正常流（脏数据清洗）
print("=== 测试 1：脏数据自动清洗 ===")
dirty_data = {
    "username": "  SuperAdmin  ",
    "phone": " 138-1234-5678 ",
    "email": " MyEmail@EXAMPLE.COM ",
}
user = UserProfileClean.model_validate(dirty_data)
print("清洗后的对象:", user)
print(f"username: '{user.username}', phone: '{user.phone}', email: '{user.email}'")

# 测试 2：异常流（非法数据拦截）
print("\n=== 测试 2：非法数据拦截 ===")
bad_data = {
    "username": "SuperAdmin",
    "phone": "138-1234-",  # 只有7位数字
    "email": "invalid_email",
}
try:
    UserProfileClean.model_validate(bad_data)
except ValidationError as e:
    print("成功拦截非法输入！捕获到 ValidationError:")
    print(e)

