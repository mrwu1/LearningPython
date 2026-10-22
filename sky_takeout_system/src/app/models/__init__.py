


from app.models.base import BaseModel

from app.models.dish import Dish

from app.models.order import Order

from app.models.refund_ledger import RefundLedger

from app.models.user import User  # 👈 新增这一行

from app.core.database import Base

# 为了让 Alembic 能够一次性感知到所有模型
__all__ = ["Base", "BaseModel", "Dish", "Order", "RefundLedger", "User"]
