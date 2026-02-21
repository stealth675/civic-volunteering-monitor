from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs_dict = dict(attrs)
            self._href = attrs_dict.get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


def extract_links(base_url: str, html: str) -> list[tuple[str, str]]:
    parser = LinkParser()
    parser.feed(html)
    out = []
    for href, text in parser.links:
        if not href or href.startswith("#"):
            continue
        out.append((urljoin(base_url, href), text))
    return out


def html_looks_js_driven(html: str) -> bool:
    text = re.sub(r"<[^>]+>", " ", html)
    text_len = len(" ".join(text.split()))
    scripts = html.lower().count("<script")
    return text_len < 200 and scripts > 5
