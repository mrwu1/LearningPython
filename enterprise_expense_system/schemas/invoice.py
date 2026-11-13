from typing import Literal

from pydantic import BaseModel, Field

from schemas.enums import EmployeeTier, InvoiceCategory


class InvoiceItem(BaseModel):
    invoice_id: str = Field(...,description="发票唯一号码")
    employee_id:str = Field(...,description="员工工号")
    employee_name:str = Field(...,description="员工姓名")
    tier:EmployeeTier = Field(...,description="员工职级")
    department:str =  Field(...,description="所属部门")
    city:str = Field(...,description="消费城市")
    category:InvoiceCategory = Field(...,description="消费类目")
    amount:float = Field(...,gt=0,description="开票金额")
    date:str = Field(...,description="开票日期")

    is_weekend:bool = Field(default=False,description="是否周末消费")
    # 风控字段
    has_overtime_approval:bool = Field(default=False,description="周末消费是否附带加班审批")

    # 🌟 新增：非结构化报销事由与消费明细（大模型语义风控的核心审计对象）
    description:str = Field(default="日常因公差旅消费",description="报销事由或发票商品明细说明")

# 人工审核输入不可信
class ManagerDecision(BaseModel):
    status: Literal["approved", "rejected"] = Field(..., description="审批动作: approved 或 rejected")
    reason: str = Field(default="主管未填写具体意见", description="审批批注原因")
