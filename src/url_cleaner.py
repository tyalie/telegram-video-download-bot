from typing import Any, Dict
from urllib.parse import urljoin, urlsplit, urlencode, parse_qs, urlunsplit


def get_cleaned_url(url: str, info: Dict[str, Any]) -> str:
    t_url = url.lower()

    if "vm.tiktok.com" in t_url and "webpage_url" in info:
        # remove the share tracking from the tiktok video
        # by extracting the pure URL
        new_url = info["webpage_url"]
        return urljoin(new_url, urlsplit(new_url).path)
    else:
        p = urlsplit(url)
        if any(map(lambda s: s in p.netloc.lower(), ["instagram", "twitter", "tiktok"])):
            return urljoin(url, p.path)
        elif any(map(lambda s: s in p.netloc.lower(), ["youtube", "youtu.be"])):
            # remove share identifier from url

            querys = parse_qs(p.query)
            if "si" in querys:
                del querys["si"]
            p = p._replace(query=urlencode(querys, doseq=True))
            return urlunsplit(p)

    return url
