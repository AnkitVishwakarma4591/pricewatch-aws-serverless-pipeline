"""Pure validation logic -- unit-testable without AWS."""
from decimal import Decimal

def validate_price(coin_id: str, price_data: dict) -> Decimal:
    if coin_id not in price_data:
        raise ValueError(f"No price data returned for '{coin_id}'")
    coin_info = price_data[coin_id]
    if "usd" not in coin_info:
        raise ValueError(f"No USD price found for '{coin_id}'")
    price = coin_info["usd"]
    if not isinstance(price, (int, float)) or price <= 0:
        raise ValueError(f"Invalid price for '{coin_id}': {price}")
    return Decimal(str(price))

def crossed_threshold(price: Decimal, threshold: Decimal) -> bool:
    return price >= threshold