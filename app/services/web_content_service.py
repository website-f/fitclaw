from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from pathlib import Path
import re
import socket
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.services.attachment_service import AttachmentService
from app.services.command_result import CommandResult
from app.services.llm_service import LLMService

settings = get_settings()


@dataclass(slots=True)
class CrawledLink:
    original_url: str
    final_url: str
    mime_type: str
    status_code: int
    title: str | None
    extracted_text: str
    error: str | None = None


class WebContentService:
    URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)

    @staticmethod
    def try_handle(
        text: str,
        prompt_messages: list[dict[str, str]],
        active_provider: str,
        active_model: str,
    ) -> CommandResult | None:
        urls = WebContentService.extract_urls(text)
        if not urls:
            return None

        crawled: list[CrawledLink] = []
        for url in urls[: settings.web_crawl_max_links]:
            crawled.append(WebContentService._crawl(url))

        successful = [item for item in crawled if not item.error]
        failed = [item for item in crawled if item.error]
        if not successful:
            lines = ["I could not read the provided link(s):"]
            for item in failed:
                lines.append(f"- {item.original_url}: {item.error}")
            return CommandResult(reply="\n".join(lines), provider="web-crawl")

        request_text = WebContentService._strip_urls(text).strip() or (
            "Summarize what these links contain, what was actually crawled, and the key takeaways."
        )
        prompt_blocks = []
        for index, item in enumerate(successful, start=1):
            prompt_blocks.append(
                "\n".join(
                    [
                        f"Link {index}: {item.original_url}",
                        f"Final URL: {item.final_url}",
                        f"HTTP status: {item.status_code}",
                        f"MIME type: {item.mime_type}",
                        f"Title: {item.title or '(no title detected)'}",
                        "Extracted content:",
                        item.extracted_text,
                    ]
                )
            )

        augmented_messages = list(prompt_messages)
        augmented_messages[-1] = {
            "role": "user",
            "content": (
                f"{request_text}\n\n"
                "Please explain clearly what was crawled from the supplied links and summarize the important findings.\n\n"
                + "\n\n---\n\n".join(prompt_blocks)
            ),
        }

        try:
            reply, provider = LLMService.generate_reply(
                augmented_messages,
                active_provider=active_provider,
                active_model=active_model,
            )
        except Exception:
            reply = WebContentService._build_fallback_summary(successful, failed)
            provider = "web-crawl"

        if failed:
            reply = reply.rstrip() + "\n\nSome links could not be crawled:\n" + "\n".join(
                f"- {item.original_url}: {item.error}" for item in failed
            )
        return CommandResult(reply=reply, provider=provider)

    @staticmethod
    def extract_urls(text: str) -> list[str]:
        seen: set[str] = set()
        results: list[str] = []
        for match in WebContentService.URL_PATTERN.findall(text or ""):
            cleaned = match.rstrip(").,]")
            if cleaned not in seen:
                results.append(cleaned)
                seen.add(cleaned)
        return results

    @staticmethod
    def _strip_urls(text: str) -> str:
        return WebContentService.URL_PATTERN.sub("", text or "")

    @staticmethod
    def _crawl(url: str) -> CrawledLink:
        try:
            WebContentService._validate_url(url)
        except ValueError as exc:
            return CrawledLink(
                original_url=url,
                final_url=url,
                mime_type="",
                status_code=0,
                title=None,
                extracted_text="",
                error=str(exc),
            )

        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=settings.web_crawl_timeout_seconds,
                headers={
                    "User-Agent": "FitClaw-AIOps/1.0 (+self-hosted web crawler)",
                    "Accept": "text/html,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,*/*",
                },
            ) as client:
                response = client.get(url)
                response.raise_for_status()
        except Exception as exc:
            return CrawledLink(
                original_url=url,
                final_url=url,
                mime_type="",
                status_code=0,
                title=None,
                extracted_text="",
                error=str(exc),
            )

        raw = response.content
        if len(raw) > settings.upload_max_bytes:
            return CrawledLink(
                original_url=url,
                final_url=str(response.url),
                mime_type=response.headers.get("content-type", ""),
                status_code=response.status_code,
                title=None,
                extracted_text="",
                error=f"content is too large ({len(raw)} bytes); limit is {settings.upload_max_bytes} bytes",
            )

        mime_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        final_url = str(response.url)
        filename = WebContentService._guess_filename(final_url, mime_type)
        try:
            extracted_text = AttachmentService.extract_text_from_bytes(filename, mime_type, raw)
        except Exception as exc:
            return CrawledLink(
                original_url=url,
                final_url=final_url,
                mime_type=mime_type,
                status_code=response.status_code,
                title=None,
                extracted_text="",
                error=f"unable to extract readable content: {exc}",
            )

        title = None
        first_line = extracted_text.splitlines()[0].strip() if extracted_text.splitlines() else ""
        if first_line.lower().startswith("title:"):
            title = first_line.split(":", 1)[1].strip() or None

        return CrawledLink(
            original_url=url,
            final_url=final_url,
            mime_type=mime_type or "application/octet-stream",
            status_code=response.status_code,
            title=title,
            extracted_text=extracted_text,
        )

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse((url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Safe crawl only allows http:// or https:// URLs.")
        if not parsed.hostname:
            raise ValueError("The crawl target is missing a valid hostname.")
        if parsed.username or parsed.password:
            raise ValueError("Safe crawl does not allow URLs with embedded credentials.")

        hostname = parsed.hostname.strip().lower()
        if hostname == "localhost" or hostname.endswith(".local"):
            raise ValueError("Safe crawl blocks localhost and local-network hostnames.")

        try:
            candidate_ip = ipaddress.ip_address(hostname)
        except ValueError:
            candidate_ip = None

        if candidate_ip is not None:
            if WebContentService._is_private_target(candidate_ip):
                raise ValueError("Safe crawl blocks private, loopback, multicast, and link-local IP addresses.")
            return

        try:
            resolved = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except socket.gaierror:
            return

        for item in resolved:
            address = item[4][0]
            try:
                candidate_ip = ipaddress.ip_address(address)
            except ValueError:
                continue
            if WebContentService._is_private_target(candidate_ip):
                raise ValueError("Safe crawl blocks hosts that resolve to private or loopback network addresses.")

    @staticmethod
    def _is_private_target(address: ipaddress._BaseAddress) -> bool:
        return bool(
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )

    @staticmethod
    def _guess_filename(url: str, mime_type: str) -> str:
        path = urlparse(url).path
        name = Path(path).name or "link"
        if Path(name).suffix:
            return name
        if "pdf" in mime_type:
            return f"{name}.pdf"
        if "html" in mime_type:
            return f"{name}.html"
        if "wordprocessingml" in mime_type:
            return f"{name}.docx"
        if "spreadsheetml" in mime_type:
            return f"{name}.xlsx"
        if "excel" in mime_type:
            return f"{name}.xls"
        if mime_type.startswith("text/"):
            return f"{name}.txt"
        return f"{name}.bin"

    @staticmethod
    def _build_fallback_summary(successful: list[CrawledLink], failed: list[CrawledLink]) -> str:
        lines = ["I crawled these links and extracted the following:"]
        for item in successful:
            excerpt = item.extracted_text[:480].strip()
            lines.append(
                f"- {item.final_url}\n"
                f"  MIME: {item.mime_type}\n"
                f"  Title: {item.title or '(none detected)'}\n"
                f"  Preview: {excerpt or '(no text extracted)'}"
            )
        if failed:
            lines.append("")
            lines.append("Some links failed:")
            for item in failed:
                lines.append(f"- {item.original_url}: {item.error}")
        return "\n".join(lines)
