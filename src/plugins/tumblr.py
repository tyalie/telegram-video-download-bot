from urllib.request import urlopen, Request
from urllib.parse import urlparse
from typing import Optional
from pathlib import Path
import re
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import random_user_agent, ExtractorError
from bs4 import BeautifulSoup


class TumblrIE(InfoExtractor):
    _VALID_URL = r'https?://(?P<blog_name>[^/?#&]+)\.tumblr\.com/(?:post|video)/(?P<id>[0-9]+)(?:$|[/?#])'
    _NETRC_MACHINE = 'tumblr'

    @staticmethod
    def _load_bf_from_url(url: str, user_agent: str, referer: Optional[str] = None) -> BeautifulSoup:
        r = Request(url)
        r.add_header("User-Agent", user_agent)
        if referer:
            r.add_header("Referer", referer)

        page = urlopen(r)
        html = page.read().decode("utf-8")
        return BeautifulSoup(html, "html.parser")

    @staticmethod
    def extract_post_id(url: str) -> Optional[str]:
        m = re.search(TumblrIE._VALID_URL, url)
        if m is None:
            return None
        return m.group("id")

    def _get_valid_page(self, url, user_agent):
        """
        Retrieve video url from post url 
        :returns Tuple[str, str,str] Tuple with post_id, video url and video type
        """
        soup = self._load_bf_from_url(url, user_agent)

        post_id = self.extract_post_id(url)
        if post_id is None:
            raise ExtractorError("Failure extracting post id from url ({url})", expected=True)

        articles = soup.find_all('article', attrs={'class': f"post-{post_id}"})

        if len(articles) == 0:
            # in this case the old layout is used. Old layout doesn't have "more videos"
            base = soup
        else:
            if len(articles) != 1:
                raise ExtractorError(f"Found {len(articles)} articles on page with matching post-id. Expected 1", expected=True)

            article = articles[0]

            # check if iframe exist and load that
            iframes = list(filter(
                lambda a: a.has_attr("src"), 
                article.find_all("iframe", attrs={"class": "tumblr_video_iframe"})
            ))

            if len(iframes) > 0:
                if len(iframes) != 1:
                    raise ExtractorError("Expect one iframe. Found {len(iframes)}", expected=True)

                article = self._load_bf_from_url(
                    iframes[0]["src"], user_agent, referer=urlparse(url).netloc
                )

            base = article

        return post_id, base

    def _real_extract(self, url):
        random_agent = random_user_agent()
        post_id, base = self._get_valid_page(url, random_agent)

        # extract video url from article
        videos = base.find_all('video')
        if len(videos) != 1:
            raise ExtractorError(f"Expected one video in article, found {len(videos)}", expected=True)

        video = videos[0]

        sources = list(filter(lambda a: a.has_attr("src") and a.has_attr("type"), video.find_all("source")))
        if len(sources) == 0:
            raise ExtractorError("Found no sources with 'src' attr in video tag", expected=True)

        video_url = sources[0]["src"]
        video_ext = Path(video_url).suffix[1:]
        formats = [{
            'url': video_url,
            'ext': video_ext,
            'format_id': "sd",
            'height': None,
            'quality': 1
        }]

        return {
            "id": post_id,
            "title": "tumblr_video",
            "formats": formats
        }
