from typing import Any, Dict
from urllib.parse import urljoin, urlparse


def get_cleaned_url(url: str, info: Dict[str, Any]) -> str:
    t_url = url.lower()

    if "vm.tiktok.com" in t_url and "webpage_url" in info:
        # remove the share tracking from the tiktok video
        # by extracting the pure URL
        new_url = info["webpage_url"]
        return urljoin(new_url, urlparse(new_url).path)
    else:
        p = urlparse(url)
        if any(map(lambda s: s in p.netloc.lower(), ["instagram", "twitter", "tiktok"])):
            return urljoin(url, p.path)

    return url
