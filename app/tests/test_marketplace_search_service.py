import unittest

from app.services.marketplace_search_service import MarketplaceSearchService


class MarketplaceSearchServiceTests(unittest.TestCase):
    def test_detects_marketplace_prompts(self) -> None:
        self.assertTrue(MarketplaceSearchService.looks_like_marketplace_request("find shopee links for this"))
        self.assertTrue(MarketplaceSearchService.looks_like_marketplace_request("where can I buy this"))
        self.assertFalse(MarketplaceSearchService.looks_like_marketplace_request("summarize this image"))

    def test_build_marketplace_links(self) -> None:
        links = MarketplaceSearchService.build_marketplace_links("wireless gaming mouse")
        self.assertEqual(links[0]["label"], "Shopee")
        self.assertIn("wireless+gaming+mouse", links[0]["url"])
        self.assertEqual(len(links), 3)


if __name__ == "__main__":
    unittest.main()
