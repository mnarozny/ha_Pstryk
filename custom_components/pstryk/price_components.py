"""Per-hour price components from the pricing frames. No Home Assistant imports.

Buy: tge_price + dist_price + service_price = base_price, and
base_price + vat_component + excise_component = price_gross.
Sell: price_prosumer_gross = tge_price * 1.23, so only tge_price applies.
"""

BUY_COMPONENTS = ("tge_price", "dist_price", "service_price", "vat_component", "excise_component")
SELL_COMPONENTS = ("tge_price",)
FLAGS = ("is_cheap", "is_expensive")

# vat_component is base_price (5 decimals) * 0.23, so the API sends up to 7.
# Rounding to 7 keeps every digit and drops float noise like 0.6970000000000001.
COMPONENT_DECIMALS = 7


def component_keys(price_type):
    return BUY_COMPONENTS if price_type == "buy" else SELL_COMPONENTS


def entry_keys(price_type):
    return component_keys(price_type) + FLAGS


def _component_value(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), COMPONENT_DECIMALS)
    except (ValueError, TypeError):
        return None


def extract_components(pricing, price_type):
    """Components for one hour, all None while the hour is unpublished.

    An unpublished hour has tge_price null but dist_price 0.0 and
    service_price 0.08, so tge_price decides whether there is data.
    """
    keys = component_keys(price_type)
    if _component_value(pricing.get("tge_price")) is None:
        return {k: None for k in keys}
    return {k: _component_value(pricing.get(k)) for k in keys}
