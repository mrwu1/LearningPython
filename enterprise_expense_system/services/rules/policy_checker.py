# ：我们在函数内部查一个 Python 业务规则表，几行逻辑算出是否超标；
from typing import Literal

from loguru import logger

from schemas.enums import EmployeeTier, InvoiceCategory
from schemas.invoice import InvoiceItem

# 制定企业差旅标准常量（PEP 8: 模块级常量统一采用 UPPER_SNAKE_CASE）
SUPER_CITIES = {"北京", "上海", "广州", "深圳"}

HOTEL_STANDARD = {
    "super": {
        "JUNIOR": 450,
        "SENIOR": 650,
        "MANAGER": 900,
        "DIRECTOR": 1500
    },
    "normal": {
        "JUNIOR": 350,
        "SENIOR": 500,
        "MANAGER": 700,
        "DIRECTOR": 1000
    }
}
# • 餐饮伙食标准（每日上限）：
MEAL_STANDARD = {
    "work_day": 100,
    "weekend": 150  # (如果 is_weekend == True 但 has_overtime_approval == False，直接判定为违规，禁止报销！)
}
# 市内交通/打车标准：
TRAFFIC_STANDARD = {
    "amount": 150
}
# 城际长途交通标准（机票/高铁单程上限，按职级）：
TRAVEL_TRANSPORT_STANDARD = {
    "JUNIOR": 1000,
    "SENIOR": 1500,
    "MANAGER": 2000,
    "DIRECTOR": 3500
}


# 获取当前员工住宿的可申请金额
def get_limit_hotel(amount: float, city: str, tier: EmployeeTier) -> dict:
    city_tier = "super" if city in SUPER_CITIES else "normal"
    if city_tier in HOTEL_STANDARD:
        max_allowed = HOTEL_STANDARD[city_tier][tier]
        if amount > max_allowed:
            return {
                "is_compliant": False,
                "is_hard_violation": False,
                "over_amount": amount - max_allowed,
                "max_allowed": max_allowed,
                "violation_reason": "报销金额超出住宿最大上限"
            }
        return {
            "is_compliant": True,
            "is_hard_violation": False,
            "over_amount": 0.0,
            "max_allowed": max_allowed,
            "violation_reason": ""
        }
    return {
        "is_compliant": False,
        "is_hard_violation": True,  # 违规
        "over_amount": 0.0,
        "max_allowed": 0.0,
        "violation_reason": "当前城市异常，无法报销，请检查所在城市"
    }


# 获取当前员工可报销的餐饮上限
def get_limit_meal(amount: float, is_weekend: bool, has_overtime_approval: bool) -> dict:
    max_allowed: float
    if is_weekend:
        # (如果 is_weekend == True 但 has_overtime_approval == False，直接判定为违规，禁止报销！)
        if not has_overtime_approval:
            return {
                "is_compliant": False,
                "is_hard_violation": True,
                "over_amount": amount,
                "max_allowed": 0.0,
                "violation_reason": "周末加班没有加班审批单，所以本次报销属于违规，禁止报销！"
            }
        max_allowed = MEAL_STANDARD["weekend"]  # 有加班单：使用周末上限 150
    else:
        max_allowed = MEAL_STANDARD["work_day"]  # 工作日：使用工作日上限 100
    if amount > max_allowed:
        return {
            "is_compliant": False,
            "is_hard_violation": False,
            "over_amount": amount - max_allowed,
            "max_allowed": max_allowed,
            "violation_reason": "报销金额超出餐饮最大上限"
        }
    return {
        "is_compliant": True,
        "is_hard_violation": False,
        "over_amount": 0.0,
        "max_allowed": max_allowed,
        "violation_reason": ""
    }


# 获取交通上限
def get_limit_traffic(amount: float) -> dict:
    max_allowed = TRAFFIC_STANDARD["amount"]
    if amount > max_allowed:
        return {
            "is_compliant": False,
            "is_hard_violation": False,
            "over_amount": amount - max_allowed,
            "max_allowed": max_allowed,
            "violation_reason": "报销金额超出交通最大上限"
        }
    return {
        "is_compliant": True,
        "is_hard_violation": False,
        "over_amount": 0.0,
        "max_allowed": max_allowed,
        "violation_reason": ""
    }


def get_limit_long_distance(amount: float, tier: EmployeeTier) -> dict:
    max_allowed = TRAVEL_TRANSPORT_STANDARD[tier]
    if amount > max_allowed:
        return {
            "is_compliant": False,
            "is_hard_violation": False,
            "over_amount": amount - max_allowed,
            "max_allowed": max_allowed,
            "violation_reason": "报销金额超出城际长途交通（机票/高铁）最大上限"
        }
    return {
        "is_compliant": True,
        "is_hard_violation": False,
        "over_amount": 0.0,
        "max_allowed": max_allowed,
        "violation_reason": ""
    }
#❌ Pydantic 的 InvoiceItem 对象没有 .get() 方法，
# 现在一运行就会在 111 行抛 AttributeError: 'InvoiceItem' object has no  attribute 'get'。
# ✅ 必须全部改成 invoice.category、invoice.amount。
def check_expense_policy(invoice:InvoiceItem)->dict:
    """
    输入强类型 InvoiceItem 对象，比对公司制度，输出合规核验结论字典。
    """
    logger.info(f"check_expense_policy - 正在校验发票: {invoice.invoice_id}")
    category = invoice.category
    amount = invoice.amount
    is_weekend = invoice.is_weekend
    city = invoice.city
    tier = invoice.tier
    has_overtime_approval = invoice.has_overtime_approval
    if category== InvoiceCategory.HOTEL:
        return get_limit_hotel(amount,city,tier)
    elif category== InvoiceCategory.MEAL:
        return get_limit_meal(amount,is_weekend,has_overtime_approval)
    elif category in (InvoiceCategory.FLIGHT, InvoiceCategory.TRAIN):
        return get_limit_long_distance(amount, tier)
    else:
        return get_limit_traffic(amount)

    # return {
    #     "is_compliant": is_compliant,  # 是否完全合规（没有超标，且无违规项）
    #     "max_allowed": max_allowed,  # 该职级/城市允许报销的最高上限
    #     "over_amount": over_amount,  # 超标金额（若未超标则为 0.0）
    #     "violation_reason": violation_reason  # 违规/超标原因说明（若合规可为空字符串 ""）
    #     "is_hard_violation":boolean # 是否符合公司要求，违规与否
    # }

