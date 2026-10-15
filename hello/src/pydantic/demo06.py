from pydantic import BaseModel, field_validator


class UserRegister(BaseModel):
    username: str
    # 1. 装饰器指定针对哪个字段生效（必须是 @classmethod）

    @field_validator("username", mode="after")
    @classmethod
    def sanitize_username(cls, v: str) -> str:
        cleaned = v.strip()  # v - 传入的原始值
        if len(cleaned) < 3:
            raise ValueError("Username must be at least 3 characters long")
        return cleaned.lower()  # 统一转小写后返回（清洗并归一化）


# ⚠️ 注意：在实际应用中，你可能还需要对其他字段进行类似的验证和清洗
# ⚠️ 注意：1. 校验器方法必须返回一个值！返回的值将作为该字段最终赋给对象的值（所以它既是“校验器”，更是“清洗器”！）。
#   │ 2. 如果校验失败，直接抛出普通的 ValueError 或 AssertionError 即可，
#           Pydantic 底层会自动将其捕获并包装成标准的ValidationError。
#   │ 3. Pydantic V1 的 @validator 在 V2 中已废弃，必须使用 @field_validator。

# test
row_dict = {"username": "  JohnDoe  "}
user1 = UserRegister.model_validate(row_dict)
print(user1)

row_dict = '{"username": "  JohnDoe  "}'
user2 = UserRegister.model_validate_json(row_dict)
print(user2)

row_dict = {"username": "  Jo  "}
user3 = UserRegister.model_validate(row_dict)
print(user3)
