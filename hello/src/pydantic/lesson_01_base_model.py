from pydantic import BaseModel


class User(BaseModel):
    id: int
    username: str
    nickname: str | None = None
    age: int

    tags: list[str] = []
    is_active: bool = True


raw_dict = {
    "id": "123",
    "username": "john_doe",
    "nickname": "johnny",
    "age": "22",  # "18 years old",
    "is_active": "false",
}
u1 = User.model_validate(raw_dict)
print(u1)
