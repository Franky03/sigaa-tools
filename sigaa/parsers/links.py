"""Keep hyperlink targets when SIGAA rich text is flattened to plain text.

Teachers write links as ``<a href="https://forms.gle/...">clique aqui</a>``;
plain text extraction would keep "clique aqui" and drop the only part that
matters.
"""

from __future__ import annotations

import re

_EXTERNAL_SCHEMES = ("http://", "https://")
_BARE_URL_RE = re.compile(r"https?://[^\s<>\"')]+")
_BLOCK_TAGS = ["p", "li", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"]


def inline_link_targets(element) -> list[str]:
    """Append each external href after its anchor text, in place.

    Returns the external hrefs found, in document order and without repeats.
    An href already written out as the anchor text is not appended twice.
    """
    hrefs: list[str] = []
    for anchor in element.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith(_EXTERNAL_SCHEMES):
            continue
        if href not in hrefs:
            hrefs.append(href)
        if href not in anchor.get_text():
            anchor.append(f" ({href})")
    return hrefs


def text_and_links(element) -> tuple[str, list[str]]:
    """Flatten rich text line by line, keeping every external URL it mentions.

    Links come from anchors and from URLs pasted as plain text, in order and
    without repeats.
    """
    links = inline_link_targets(element)
    text = _block_text(element)
    for url in _BARE_URL_RE.findall(text):
        if url not in links:
            links.append(url)
    return text, links


def _block_text(element) -> str:
    """One line per paragraph, list item or ``<br>``; inline tags stay inline.

    Splitting on every tag would put an anchor's text and its target on lines
    of their own, away from the sentence they belong to.
    """
    for line_break in element.find_all("br"):
        line_break.replace_with("\n")
    for block in element.find_all(_BLOCK_TAGS):
        block.append("\n")
    lines = (" ".join(line.split()) for line in element.get_text().splitlines())
    return "\n".join(line for line in lines if line)
