from yt_dlp import YoutubeDL
from yt_dlp.compat import compat_basestring
from yt_dlp.utils import sanitized_Request


def _custom_urlopen(original):

    def _open(self, req):
        """ Start an HTTP download """
        if isinstance(req, compat_basestring):
            req = sanitized_Request(req)

        if self.params.get("http_headers"):
            # stolen from YoutubeDLHandler.http_request
            for h, v in self.params.get("http_headers").items():
                if h.capitalize() not in req.headers:
                    req.update(headers={h: v})

        return original(self, req)

    return _open

YoutubeDL2 = YoutubeDL
original_open = YoutubeDL2.urlopen
YoutubeDL2.urlopen = _custom_urlopen(original_open)
