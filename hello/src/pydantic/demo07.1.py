from pydantic import BaseModel, computed_field


class OrderItem(BaseModel):
    price: float
    quantity: int

    @computed_field
    def subtotal(self) -> float:
        """这个属性不需要外部传参，自动由 price * quantity 算出"""
        return self.price * self.quantity


# test

order_item = OrderItem(price=10.0, quantity=5)
print(order_item.subtotal)
