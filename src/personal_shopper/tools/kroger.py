"""Kroger Developer API tools for store lookup and product availability.

Requires ``KROGER_CLIENT_ID`` and ``KROGER_CLIENT_SECRET`` environment variables.
Used when ``preferred_retailer`` maps to the Kroger family (kroger, ralphs, etc.).
"""
import os
from typing import Any

from kroger_api import KrogerAPI
from langchain_core.tools import tool


def _get_kroger_client() -> KrogerAPI:
    """Build an authenticated Kroger API client from environment credentials."""
    return KrogerAPI(
        client_id=os.environ["KROGER_CLIENT_ID"],
        client_secret=os.environ["KROGER_CLIENT_SECRET"],
    )


@tool
def find_nearest_store(zip_code: str) -> dict[str, Any]:
    """Find the nearest Kroger-family store for a US zip code.

    Args:
        zip_code: Five-digit US postal code.

    Returns:
        Dict with ``location_id``, ``name``, ``address``, ``chain`` on success.
        On failure returns ``location_id: None`` and an ``error`` string.
    """
    try:
        kroger = _get_kroger_client()
        kroger.authorization.get_token_with_client_credentials("product.compact")
        result = kroger.location.search_locations(
            zip_code=zip_code, radius_in_miles=15, limit=1
        )
        locations = result.get("data", [])
        if not locations:
            return {"error": "No stores found", "location_id": None}
        loc = locations[0]
        address = loc.get("address", {})
        if isinstance(address, dict):
            address_str = ", ".join(
                filter(
                    None,
                    [
                        address.get("addressLine1"),
                        address.get("city"),
                        address.get("state"),
                        address.get("zipCode"),
                    ],
                )
            )
        else:
            address_str = str(address)
        return {
            "location_id": loc.get("locationId"),
            "name": loc.get("name"),
            "address": address_str,
            "chain": loc.get("chain"),
        }
    except Exception as e:
        return {"error": str(e), "location_id": None}


@tool
def check_product_availability(ingredient: str, location_id: str) -> dict[str, Any]:
    """Check if an ingredient is available at a specific Kroger store.

    Args:
        ingredient: Product search term (e.g. ``basil``, ``chicken breast``).
        location_id: Kroger ``locationId`` from ``find_nearest_store``.

    Returns:
        Dict with ``ingredient``, ``available`` (bool), ``product_description``,
        ``price`` (float or None), ``size``, and optional ``error``.
    """
    try:
        kroger = _get_kroger_client()
        kroger.authorization.get_token_with_client_credentials("product.compact")
        result = kroger.product.search_products(
            term=ingredient,
            location_id=location_id,
            fulfillment="ais",
            limit=3,
        )
        products = result.get("data", [])
        if not products:
            return {
                "ingredient": ingredient,
                "available": False,
                "product_description": None,
                "price": None,
                "size": None,
            }
        product = products[0]
        items = product.get("items", [])
        price = None
        size = None
        if items:
            price_info = items[0].get("price", {})
            price = price_info.get("regular") or price_info.get("promo")
            size = items[0].get("size")
        return {
            "ingredient": ingredient,
            "available": True,
            "product_description": product.get("description"),
            "price": float(price) if price is not None else None,
            "size": size,
        }
    except Exception as e:
        return {
            "ingredient": ingredient,
            "available": False,
            "product_description": None,
            "price": None,
            "size": None,
            "error": str(e),
        }
