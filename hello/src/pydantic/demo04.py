from typing import Generic, TypeVar

from pydantic import BaseModel


class Address(BaseModel):
    street: str
    city: str
    zipcode: str


class UserProfile(BaseModel):
    name: str
    age: int
    address: Address
    address_list: list[Address]


# test
raw_dict = {
    "name": "Alice",
    "age": 30,
    "address": {"street": "123 Main St", "city": "New York", "zipcode": "10001"},
    "address_list": [
        {"street": "456 Oak Ave", "city": "Los Angeles", "zipcode": "90210"}
    ],
}
user = UserProfile.model_validate(raw_dict)
print(user)


# 范型 T
T = TypeVar("T")
# T=list [int]


class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    # data 的类型由具体的泛型参数决定（可以为 None）
    data: T | None = None


print("-------------------")
user_response = ApiResponse[UserProfile].model_validate(raw_dict)
print(user_response)
print("----------------------")
list_response = ApiResponse[list[Address]].model_validate(raw_dict)
print(list_response)
