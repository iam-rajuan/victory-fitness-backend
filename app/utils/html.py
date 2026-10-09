import html as html_lib
from html.parser import HTMLParser
import re
from urllib.parse import urlparse


ALLOWED_CONTENT_TAGS = {
    "a",
    "blockquote",
    "br",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "strong",
    "b",
    "u",
    "ul",
}

VOID_TAGS = {"br", "hr", "img"}
ALLOWED_ATTRS = {
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title"},
}
ALLOWED_LINK_SCHEMES = {"http", "https", "mailto", "tel"}
ALLOWED_IMAGE_SCHEMES = {"http", "https"}


def _safe_url(value: str, *, image: bool = False) -> str:
    normalized = html_lib.unescape(str(value or "").strip())
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if not parsed.scheme:
        return normalized if not image and normalized.startswith("/") else ""
    allowed = ALLOWED_IMAGE_SCHEMES if image else ALLOWED_LINK_SCHEMES
    return normalized if parsed.scheme.lower() in allowed else ""


class _ContentSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_CONTENT_TAGS:
            return

        clean_attrs: list[tuple[str, str]] = []
        allowed_attrs = ALLOWED_ATTRS.get(tag, set())
        for raw_name, raw_value in attrs:
            name = str(raw_name or "").strip().lower()
            if name not in allowed_attrs:
                continue
            value = str(raw_value or "").strip()
            if name in {"href", "src"}:
                value = _safe_url(value, image=(tag == "img"))
                if not value:
                    continue
            if tag == "a" and name == "target" and value != "_blank":
                continue
            clean_attrs.append((name, value))

        if tag == "a" and any(name == "target" and value == "_blank" for name, value in clean_attrs):
            attr_names = {name for name, _value in clean_attrs}
            if "rel" not in attr_names:
                clean_attrs.append(("rel", "noopener noreferrer"))

        attr_text = "".join(
            f' {name}="{html_lib.escape(value, quote=True)}"'
            for name, value in clean_attrs
        )
        self.parts.append(f"<{tag}{attr_text}>")
        if tag not in VOID_TAGS:
            self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_CONTENT_TAGS or tag in VOID_TAGS:
            return
        if tag in self.open_tags:
            while self.open_tags:
                current = self.open_tags.pop()
                self.parts.append(f"</{current}>")
                if current == tag:
                    break

    def handle_data(self, data: str) -> None:
        self.parts.append(html_lib.escape(data, quote=False))

    def close_all(self) -> None:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")


def sanitize_html_content(html_content: str) -> str:
    sanitizer = _ContentSanitizer()
    sanitizer.feed(str(html_content or ""))
    sanitizer.close()
    sanitizer.close_all()
    cleaned = "".join(sanitizer.parts)
    cleaned = re.sub(r"(?is)<(script|style|iframe|object|embed|form|input|meta|link)[^>]*>.*?</\1>", "", cleaned)
    cleaned = re.sub(r"(?i)\s+on[a-z]+\s*=", " data-removed=", cleaned)
    return cleaned.strip()


def html_to_plain_text(html_content: str) -> str:
    if not html_content:
        return ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", html_content)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</h[1-6]>", "\n\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "• ", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"(?i)</blockquote>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
