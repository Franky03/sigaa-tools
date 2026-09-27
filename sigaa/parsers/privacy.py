"""Text representations used by the onboarding privacy scanner."""
from html import unescape

from bs4 import BeautifulSoup


def text_representations(text):
    decoded = unescape(text)
    soup = BeautifulSoup(decoded, "html.parser")
    # Both separators matter: inline tags can split a name, while separate
    # cells can supply the whitespace between full-name components.
    return (text, decoded, soup.get_text(""), soup.get_text(" "))
