from __future__ import annotations

from urllib.parse import quote_plus


class MarketplaceSearchService:
    MARKETPLACE_URLS = (
        ("Shopee", "https://shopee.com.my/search?keyword={query}"),
        ("Lazada", "https://www.lazada.com.my/catalog/?q={query}"),
        ("Google Shopping", "https://www.google.com/search?tbm=shop&q={query}"),
    )
    SEARCH_HINTS = (
        "shopee",
        "lazada",
        "marketplace",
        "seller",
        "sell this",
        "buy this",
        "where can i buy",
        "where to buy",
        "shopping link",
        "product link",
        "find similar",
        "similar item",
        "search this product",
        "price check",
        "compare price",
    )

    @staticmethod
    def looks_like_marketplace_request(text: str) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return False
        return any(token in lowered for token in MarketplaceSearchService.SEARCH_HINTS)

    @staticmethod
    def normalize_query(text: str, fallback: str = "product") -> str:
        cleaned = " ".join((text or "").replace("\n", " ").split()).strip(" .,:;|-")
        if not cleaned:
            cleaned = fallback
        if len(cleaned) > 120:
            cleaned = cleaned[:120].rstrip()
        return cleaned

    @staticmethod
    def build_marketplace_links(query: str) -> list[dict[str, str]]:
        normalized = MarketplaceSearchService.normalize_query(query)
        encoded = quote_plus(normalized)
        return [
            {"label": label, "url": template.format(query=encoded)}
            for label, template in MarketplaceSearchService.MARKETPLACE_URLS
        ]
