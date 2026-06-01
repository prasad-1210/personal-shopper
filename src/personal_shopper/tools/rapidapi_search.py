"""
Unified multi-retailer product search via RapidAPI real-time-product-search.
Covers: Walmart, Target, Costco, Amazon, Best Buy, and many others.
Powered by Google Shopping — catalog data, not store-level inventory.
Same interface as kroger.py so graph.py can swap with no other changes.

Register free at rapidapi.com:
  Search "real-time-product-search" by letscrape-6bRBa3QguO5
  Subscribe to Basic plan (free tier available)
  Same RAPIDAPI_KEY used for all RapidAPI-hosted APIs.

Supported store values (pass as store parameter):
  walmart, target, costco, amazon, bestbuy, ebay
  omit store for best match across all retailers
"""
import os
import re
from typing import Any

import httpx
from langchain_core.tools import tool

RAPID_HOST = "real-time-product-search.p.rapidapi.com"
RAPID_BASE = f"https://{RAPID_HOST}"

# Map normalised retailer names to store filter values the API accepts
STORE_MAP = {
    "walmart":  "walmart",
    "target":   "target",
    "costco":   "costco",
    "amazon":   "amazon",
    "bestbuy":  "bestbuy",
    "best buy": "bestbuy",
}

# Human-readable retailer names for display
RETAILER_DISPLAY = {
    "walmart": "Walmart",
    "target":  "Target",
    "costco":  "Costco",
    "amazon":  "Amazon",
    "bestbuy": "Best Buy",
}

# Retailers where we cannot confirm store-level availability
CATALOG_ONLY_NOTE = (
    "Catalog price via Google Shopping — "
    "in-store availability not confirmed."
)


def _headers() -> dict[str, str]:
    key = os.environ.get("RAPIDAPI_KEY", "")
    if not key:
        raise OSError(
            "RAPIDAPI_KEY not set. "
            "Register free at rapidapi.com → real-time-product-search"
        )
    return {
        "x-rapidapi-host": RAPID_HOST,
        "x-rapidapi-key": key,
    }


def _parse_price(price_str: str | None) -> float | None:
    """Extract float from strings like '$2.98', 'USD 2.98', 'From $1.99'."""
    if not price_str:
        return None
    match = re.search(r"\d+\.\d{2}", str(price_str))
    return float(match.group()) if match else None


def _normalise_retailer(retailer: str) -> str:
    """Normalise retailer string to a known store key or empty string."""
    return STORE_MAP.get(retailer.lower().strip(), "")


def _extract_products(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull product list from known RapidAPI response shapes."""
    if not isinstance(data, dict):
        return []
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("products", "product_offers", "results", "items"):
            items = inner.get(key)
            if isinstance(items, list) and items:
                return items
    for key in ("products", "product_offers", "results", "items"):
        items = data.get(key)
        if isinstance(items, list) and items:
            return items
    return []


def _product_fields(product: dict[str, Any]) -> tuple[str, str | None, str, str]:
    """Return (title, price_raw, store_name, url) from a product dict."""
    offer_raw = product.get("offer")
    offer: dict[str, Any] = offer_raw if isinstance(offer_raw, dict) else {}

    title = (
        product.get("product_title")
        or product.get("title")
        or product.get("name")
        or ""
    )
    price_raw = (
        product.get("product_price")
        or offer.get("price")
        or product.get("price")
        or product.get("offer_price")
    )
    if not price_raw:
        price_range = product.get("typical_price_range")
        if isinstance(price_range, list) and price_range:
            price_raw = price_range[0]

    store_name = (
        product.get("store")
        or offer.get("store_name")
        or product.get("seller")
        or ""
    )
    url = (
        product.get("product_page_url")
        or offer.get("offer_page_url")
        or product.get("product_url")
        or product.get("link")
        or ""
    )
    return title, price_raw, store_name, url


def _http_error_message(status: int, body: dict[str, Any] | str) -> str:
    """Human-readable errors for common RapidAPI failures."""
    msg = ""
    if isinstance(body, dict):
        msg = str(body.get("message") or body.get("error") or "")
    elif body:
        msg = str(body)[:200]

    if status == 403:
        return (
            "RAPIDAPI_KEY is not subscribed to 'real-time-product-search'. "
            "Open https://rapidapi.com/letscrape-6bRBa3QguO5/api/real-time-product-search "
            "→ Subscribe (Basic/free) → use that app's key in RAPIDAPI_KEY."
            + (f" API says: {msg}" if msg else "")
        )
    if status == 429:
        return (
            "RapidAPI rate limit (429). Wait a minute or upgrade your plan."
            + (f" {msg}" if msg else "")
        )
    return msg or f"HTTP {status}"


@tool
def find_nearest_store(zip_code: str) -> dict[str, Any]:
    """Find a store for a given US zip code.
    For non-Kroger retailers (Walmart, Target, Costco, Amazon) this API
    provides catalog-only search — no official store locator is available.
    Returns a generic entry so the graph can continue.
    The retailer is determined by the preferred_retailer in the request,
    not by this function. location_id carries the retailer key.
    """
    # The real-time-product-search API has no store locator.
    # We return a placeholder so find_store node can pass location_id
    # downstream to check_product_availability as the store filter key.
    # The actual retailer value is resolved in graph.py via _get_retailer().
    return {
        "location_id": f"rapidapi-{zip_code}",
        "name": f"Nearby store (near {zip_code})",
        "address": f"Near zip code {zip_code}",
        "chain": "Multi-retailer",
        "note": CATALOG_ONLY_NOTE,
    }


@tool
def check_product_availability(
    ingredient: str,
    location_id: str,
    store: str = "",
) -> dict[str, Any]:
    """Search for an ingredient across major retailers via Google Shopping.
    Returns the best-match product with title, price, store name, and URL.

    store: optional retailer filter — walmart, target, costco, amazon, bestbuy
           leave empty to search all retailers and return best match.
    location_id: accepted for interface compatibility, not used by this API.

    Note: catalog data only — prices may vary, in-store availability
    not confirmed. Data powered by Google Shopping.
    """
    store_key = _normalise_retailer(store) if store else ""

    params: dict[str, str | int] = {
        "q": ingredient,
        "country": "us",
        "language": "en",
        "limit": 5,
    }
    # API docs: filter param is "stores" (comma-separated), not "store"
    if store_key:
        params["stores"] = store_key

    try:
        r = httpx.get(
            f"{RAPID_BASE}/search",
            headers=_headers(),
            params=params,
            timeout=45,
        )
        if r.status_code >= 400:
            try:
                body = r.json()
            except Exception:
                body = r.text
            return {
                "ingredient": ingredient,
                "available": False,
                "error": _http_error_message(r.status_code, body),
                "http_status": r.status_code,
                "source": "rapidapi_google_shopping",
                "store_filter": store_key or "any",
            }

        data = r.json()
        products = _extract_products(data)

        if not products:
            return {
                "ingredient": ingredient,
                "available": False,
                "products": [],
                "error": "No products in API response (check subscription and query).",
                "source": "rapidapi_google_shopping",
                "store_filter": store_key or "any",
            }

        best = products[0]
        title, price_raw, store_name, url = _product_fields(best)
        store_name = store_name or RETAILER_DISPLAY.get(store_key, "Online")

        return {
            "ingredient": ingredient,
            "available": True,
            "product_description": title,
            "price": _parse_price(price_raw),
            "store": store_name,
            "link": url,
            "source": "rapidapi_google_shopping",
            "note": CATALOG_ONLY_NOTE,
        }

    except Exception as e:
        return {
            "ingredient": ingredient,
            "available": False,
            "error": str(e),
            "source": "rapidapi_google_shopping",
            "store_filter": store_key or "any",
        }
