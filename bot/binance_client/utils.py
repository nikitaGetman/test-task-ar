from decimal import Decimal


def round_step_size(quantity: float | Decimal, step_size: float | Decimal) -> float:
    if step_size == 0:
        return float(quantity)

    quantity = Decimal(str(quantity))
    return float(quantity - quantity % Decimal(str(step_size)))
