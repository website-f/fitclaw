import unittest

from app.services.attachment_service import AttachmentService


class AttachmentServiceTests(unittest.TestCase):
    def test_recent_assets_support_marketplace_follow_up(self) -> None:
        self.assertTrue(AttachmentService.should_use_recent_assets("find Shopee links for this"))
        self.assertTrue(AttachmentService.should_use_recent_assets("where can I buy this"))

    def test_empty_image_message_offers_concierge(self) -> None:
        self.assertTrue(AttachmentService._should_offer_image_concierge(""))
        self.assertTrue(AttachmentService._should_offer_image_concierge("look at this"))
        self.assertFalse(AttachmentService._should_offer_image_concierge("what is this"))

    def test_extract_json_dict_handles_code_fences(self) -> None:
        parsed = AttachmentService._extract_json_dict(
            "```json\n{\"identified_item\":\"Wireless mouse\",\"search_query\":\"wireless bluetooth mouse\"}\n```"
        )
        self.assertEqual(parsed.get("identified_item"), "Wireless mouse")


if __name__ == "__main__":
    unittest.main()
