import unittest

from app.services.web_content_service import WebContentService


class WebContentServiceTests(unittest.TestCase):
    def test_validate_url_blocks_localhost(self) -> None:
        with self.assertRaisesRegex(ValueError, "localhost"):
            WebContentService._validate_url("http://localhost:8000/private")

    def test_validate_url_blocks_private_ip(self) -> None:
        with self.assertRaisesRegex(ValueError, "private"):
            WebContentService._validate_url("http://192.168.1.10/admin")

    def test_validate_url_allows_public_host(self) -> None:
        WebContentService._validate_url("https://example.com/products")


if __name__ == "__main__":
    unittest.main()
