import re
from urllib.parse import urlsplit

from rest_framework.exceptions import ValidationError


LINK = re.compile(
    r"(?:(?:[a-z][a-z0-9+.-]*:)?//(?:\[[^\s<>\"'()]*|[^\s<>\"'\[\]()]+)"
    r"|(?<![\w@./-])(?:[\w-]+\.)+(?:[^\W\d_]{2,}|xn--[\w-]+)"
    r"(?::\d+)?(?:[/\?#][^\s<>\"'\[\]()]*)?)",
    re.IGNORECASE,
)


def validate_youtube_url(value):
    try:
        url = urlsplit(value, scheme="https")
        host = (url.hostname or "").removesuffix(".")
    except ValueError as error:
        raise ValidationError("Укажите корректную ссылку на youtube.com.") from error
    if (
        url.scheme not in ("http", "https")
        or "\\" in url.netloc
        or not (host == "youtube.com" or host.endswith(".youtube.com"))
    ):
        raise ValidationError("В материалах разрешены только ссылки на youtube.com.")


def validate_youtube_links(value):
    """Check each web link embedded in a title or description."""
    for match in LINK.finditer(value):
        link = match.group().rstrip(".,;!:?")
        if "://" not in link and not link.startswith("//"):
            link = f"//{link}"
        validate_youtube_url(link)
