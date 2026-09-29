"""Parse a turma's Tarefas page (Turma Virtual > Atividades > Tarefas).

Each tarefa is two rows of a ``table.listing``: a title row carrying the
delivery period, then a row with the teacher's description. Rows of a closed
tarefa carry no SIGAA id, so callers identify them by turma and title.

An empty result is only trusted when SIGAA says so ("Nenhum item foi
encontrado"). A page without the Tarefas fieldset, or a listing whose rows are
not recognized, raises ``UnrecognizedPageError``.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import ClassActivity
from ._variants import page_parser
from .links import text_and_links

TAREFA_KIND = "tarefa"

_TAREFAS_LEGEND_RE = re.compile(r"^\s*Tarefas\s*$")
_EMPTY_LISTING_RE = re.compile(r"Nenhum item foi encontrado", re.I)


def _tarefas_fieldset(soup: BeautifulSoup):
    legend = soup.find("legend", string=_TAREFAS_LEGEND_RE)
    return legend.find_parent("fieldset") if legend else None


def _declares_no_tarefas(soup: BeautifulSoup) -> bool:
    fieldset = _tarefas_fieldset(soup)
    return bool(fieldset and _EMPTY_LISTING_RE.search(fieldset.get_text(" ", strip=True)))


@page_parser(
    "task_list",
    lambda soup: _tarefas_fieldset(soup) is not None,
    empty=_declares_no_tarefas,
    # A title row without its delivery period is a layout this parser does not know.
    validate=lambda result, soup: all(tarefa.period for tarefa in result),
    name="tarefas-listing",
)
def parse_tarefa_list(soup: BeautifulSoup, id_turma: str) -> list[ClassActivity]:
    tarefas: list[ClassActivity] = []
    for table in _tarefas_fieldset(soup).select("table.listing"):
        group = _group_name(table)
        for row in table.select("tbody > tr"):
            title_cell = _title_cell(row)
            if title_cell is not None:
                tarefas.append(_tarefa(title_cell, id_turma, group))
    return tarefas


def _title_cell(row):
    """A title row has several cells; the description row below it has one."""
    if len(row.find_all("td", recursive=False)) < 2:
        return None
    return row.find("td", class_="first", recursive=False)


def _tarefa(title_cell, id_turma: str, group: str | None) -> ClassActivity:
    period_cell = title_cell.find_next_sibling("td")
    period = " ".join(period_cell.get_text(" ", strip=True).split()) if period_cell else ""
    description, links = _description(title_cell.find_parent("tr"))
    return ClassActivity(
        id_turma=id_turma,
        kind=TAREFA_KIND,
        title=title_cell.get_text(" ", strip=True),
        period=period,
        description=description,
        links=links,
        group=group,
    )


def _description(title_row) -> tuple[str, list[str]]:
    """The teacher's text sits in the row right after the title row."""
    row = title_row.find_next_sibling("tr")
    cells = row.find_all("td", recursive=False) if row else []
    if len(cells) != 1 or "first" not in cells[0].get("class", []):
        return "", []
    return text_and_links(cells[0])


def _group_name(table) -> str | None:
    fieldset = table.find_parent("fieldset")
    legend = fieldset.find("legend") if fieldset else None
    name = legend.get_text(" ", strip=True) if legend else ""
    return name if name and not _TAREFAS_LEGEND_RE.match(name) else None
