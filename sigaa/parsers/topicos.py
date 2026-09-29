"""Find activities posted as Tópicos de Aula on a Turma Virtual Principal page.

Teachers often publish an assignment as a lesson topic, e.g.
``Atividade 02 :: HQ ... (21/09/2026 - 23/09/2026)``, instead of a SIGAA
Tarefa. Such a topic never reaches the portal event dropdowns or the Tarefas
page, and its instructions and links live only in ``div.conteudotopico``.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import ClassActivity
from ._common import fold
from ._variants import page_parser
from .links import text_and_links
from .news import news_panel

ACTIVITY_KIND = "atividade"

_PERIOD_RE = re.compile(r"\(\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})\s*\)\s*$")
# "ATIVIDADE REMOTA" marks a remote lesson, not an assignment, so it is ignored.
_REMOTE_LESSON_RE = re.compile(r"\batividade remota\b")
_ACTIVITY_RE = re.compile(r"\batividades?\b")


def _is_class_page(soup: BeautifulSoup) -> bool:
    """Topics, or the Principal page's news panel when a class has no topics yet."""
    return bool(soup.select("div.topico-aula")) or news_panel(soup) is not None


def _every_topic_has_a_title(soup: BeautifulSoup) -> bool:
    """A topic without its heading means the layout changed: skipping it could hide one."""
    return all(topic.select_one(".titulo") for topic in soup.select("div.topico-aula"))


@page_parser(
    "activity_topics",
    _is_class_page,
    # Most lesson topics are not activities; a class with none is not a failure.
    empty=lambda soup: True,
    validate=lambda result, soup: _every_topic_has_a_title(soup),
    name="class-topic-headings",
)
def parse_activity_topics(soup: BeautifulSoup, id_turma: str) -> list[ClassActivity]:
    """Lesson topics whose title names an activity, with their text and links."""
    activities: list[ClassActivity] = []
    for topic in soup.select("div.topico-aula"):
        heading = topic.select_one(".titulo")
        if heading is None:
            continue
        title, period = _title_and_period(heading.get_text(" ", strip=True))
        if not _names_an_activity(title):
            continue
        description, links = _content(topic)
        activities.append(
            ClassActivity(
                id_turma=id_turma,
                kind=ACTIVITY_KIND,
                title=title,
                period=period,
                description=description,
                links=links,
            )
        )
    return activities


def _title_and_period(heading: str) -> tuple[str, str]:
    match = _PERIOD_RE.search(heading)
    if not match:
        return heading, ""
    start, end = match.groups()
    return heading[: match.start()].strip(), f"{start} a {end}"


def _names_an_activity(title: str) -> bool:
    folded = _REMOTE_LESSON_RE.sub(" ", fold(title))
    return bool(_ACTIVITY_RE.search(folded))


def _content(topic) -> tuple[str, list[str]]:
    content = topic.select_one(".conteudotopico")
    if content is None:
        return "", []
    return text_and_links(content)
