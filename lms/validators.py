import re
from urllib.parse import urlsplit

from rest_framework.exceptions import ValidationError


LINK = re.compile(
    r"(?:(?:[a-z][a-z0-9+.-]*:)?//(?:\[[^\s<>\"'()]*|[^\s<>\"'\[\]()]+)"
    r"|(?<![\w@./-])(?:[\w-]+\.)+(?:[^\W\d_]{2,}|xn--[\w-]+)"
    r"(?::\d+)?(?:[/\?#][^\s<>\"'\[\]()]*)?)",
    re.IGNORECASE,
)


def validate_youtube_links(value):
    """Allow plain text and links whose hostname belongs to youtube.com."""
    for match in LINK.finditer(value):
        link = match.group().rstrip(".,;!:?")
        if "://" not in link and not link.startswith("//"):
            link = f"//{link}"
        try:
            url = urlsplit(link)
            host = (url.hostname or "").rstrip(".")
        except ValueError:
            host = ""
        if not host or url.scheme not in ("", "http", "https") or not (
            host == "youtube.com" or host.endswith(".youtube.com")
        ):
            raise ValidationError("В материалах разрешены только ссылки на youtube.com.")
