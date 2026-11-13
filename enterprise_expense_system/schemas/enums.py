from enum import StrEnum


# StrEnum 的成员本身就是 str 的子类，json.dumps 会把它当普通字符串处理，

# 发票类型
class InvoiceCategory(StrEnum):
    HOTEL = "HOTEL"
    MEAL = "MEAL"
    TAXI = "TAXI"
    FLIGHT = "FLIGHT"
    TRAIN = "TRAIN"

# 员工职级
class EmployeeTier(StrEnum):
    JUNIOR = "JUNIOR"
    SENIOR = "SENIOR"
    MANAGER = "MANAGER"
    DIRECTOR = "DIRECTOR"