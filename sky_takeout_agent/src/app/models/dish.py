from decimal import Decimal

from sqlalchemy import BigInteger, String, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Dish(Base):
    """
            苍穹外卖真实菜品表映射
            对标 Java: @Entity @Table(name = "dish")
    """
    __tablename__ = "dish"

    id:Mapped[int] = mapped_column(BigInteger,primary_key=True,autoincrement=True)
    # 菜品名称
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 价格 (精确金额推荐用 Numeric)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # 状态: 1 在售 0 停售
    status: Mapped[int] = mapped_column(Integer, default=1)
    # 分类 ID
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    def __repr__(self) -> str:
        # print in the dashboard / console
        return f"<Dish(id={self.id}, name={self.name!r}, price={self.price}, status={self.status})>"