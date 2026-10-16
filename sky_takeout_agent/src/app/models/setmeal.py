from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Setmeal(Base):
    """
    外卖套餐表 (模拟业务新需求上线)
    """
    __tablename__ = "setmeal_test"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="套餐名称")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="套餐价格")
    status: Mapped[int] = mapped_column(Integer, default=1, comment="1起售 0停售")

    deleted: Mapped[int] = mapped_column(Integer,default=0,comment="1:del 0:not del")