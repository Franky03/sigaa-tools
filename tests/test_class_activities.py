"""Assignments that live only inside the Turma Virtual: Tópicos de Aula and the Tarefas page.

Regression: "Atividade 02" of Teste de Software (DINF00054, turma 377491) was
posted as a lesson topic. It never reached the portal event dropdowns, so sync
stored nothing and its link (a Google Form) could not be found.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import FIXTURES, TEST_PASSWORD, TEST_USERNAME
from sigaa import config, mcp_server
from sigaa.config import Settings
from sigaa.errors import STAGE_PARSE
from sigaa.models import Deadline
from sigaa.parsers import tarefa as tarefa_parser
from sigaa.parsers import tarefa_list as tarefa_list_parser
from sigaa.parsers import topicos as topicos_parser
from sigaa.services import sync, watch, whatsnew
from sigaa.store.db import connect
from sigaa.store.repository import Repository

ID_TURMA = "377491"
CLASS_CODE = "DINF00054"
TOPIC_TITLE = "ATIVIDADE REMOTA -- Atividade 02 :: HQ de exemplo"
TOPIC_DEADLINE_ID = "topico:377491:atividade-remota-atividade-02-hq-de-exemplo"
TAREFA_TITLE = "Atividade 02 - Questionário"
TAREFA_DEADLINE_ID = "tarefa:377491:atividade-02-questionario"
FORM_URL = "https://docs.google.com/forms/d/e/FORM-EXEMPLO/viewform"
SLIDES_URL = "https://docs.google.com/presentation/d/SLIDES-EXEMPLO/edit?usp=sharing"
PORTAL_EVENT_ID = "45959072"
FIXED_NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def logged_in(clean_credentials):
    clean_credentials[(config.KEYRING_SERVICE, config.KEYRING_ACTIVE_USERNAME)] = TEST_USERNAME
    clean_credentials[(config.KEYRING_SERVICE, TEST_USERNAME)] = TEST_PASSWORD


@pytest.fixture
def teste_de_software(fake_sigaa, logged_in):
    fake_sigaa.add_class(ID_TURMA, CLASS_CODE, "turma_topicos.html")
    return fake_sigaa


def _settings(tmp_path: Path) -> Settings:
    return Settings(db_path=tmp_path / "t.db")


def _repo(tmp_path: Path) -> Repository:
    return Repository(connect(tmp_path / "t.db"))


# --- parsers ---------------------------------------------------------------

def test_activity_topic_is_found_with_its_period_and_links():
    (activity,) = topicos_parser.parse_activity_topics(_fixture("turma_topicos.html"), ID_TURMA)

    assert (activity.id_turma, activity.kind, activity.title, activity.period) == (
        ID_TURMA, "atividade", TOPIC_TITLE, "21/09/2026 a 23/09/2026",
    )
    assert activity.links == [SLIDES_URL, FORM_URL]
    assert f"formulário ({FORM_URL})" in activity.description


def test_lessons_and_remote_lessons_are_not_activities():
    titles = [a.title for a in topicos_parser.parse_activity_topics(
        _fixture("turma_topicos.html"), ID_TURMA
    )]

    assert not any("Aula" in title for title in titles)


def test_topic_without_a_title_raises_a_parse_error():
    html = _fixture("turma_topicos.html").replace('class="titulo"', 'class="cabecalho"')

    with pytest.raises(topicos_parser.TopicParseError) as excinfo:
        topicos_parser.parse_activity_topics(html, ID_TURMA)

    assert excinfo.value.stage == STAGE_PARSE
    assert ID_TURMA in str(excinfo.value)


def test_tarefa_list_rows_carry_period_description_and_links():
    first, second = tarefa_list_parser.parse_tarefa_list(_fixture("tarefas.html"), ID_TURMA)

    assert (first.kind, first.title, first.group) == ("tarefa", TAREFA_TITLE, "Tarefas Individuais")
    assert first.period == "de 21/09/2026 às 08h00 a 23/09/2026 às 23h59"
    assert first.links == [FORM_URL]
    assert f"formulário ({FORM_URL})" in first.description
    assert second.links == ["https://www.youtube.com/watch?v=VIDEO-EXEMPLO"]


def test_declared_empty_tarefa_list_is_the_only_trusted_empty_result():
    assert tarefa_list_parser.parse_tarefa_list(_fixture("tarefas_empty.html"), ID_TURMA) == []


@pytest.mark.parametrize(
    "html",
    [
        _fixture("tarefas.html").replace('class="listing"', 'class="grid"'),
        _fixture("tarefas_empty.html").replace("Nenhum item foi encontrado", ""),
        _fixture("auth_redirect.html"),
    ],
    ids=["unrecognized-rows", "no-empty-notice", "not-the-tarefas-page"],
)
def test_unrecognized_tarefa_pages_raise_a_parse_error(html):
    with pytest.raises(tarefa_list_parser.TarefaListParseError) as excinfo:
        tarefa_list_parser.parse_tarefa_list(html, ID_TURMA)

    assert excinfo.value.stage == STAGE_PARSE
    assert ID_TURMA in str(excinfo.value)


def test_portal_tarefa_description_keeps_its_link_target():
    html = _fixture("tarefa.html").replace(
        "Enunciado da atividade de exemplo.",
        f'Responda o <a href="{FORM_URL}">formulário</a>.',
    )

    fields = tarefa_parser.parse_tarefa_body(html)

    assert fields["Descrição"] == f"Responda o formulário ({FORM_URL}) ."


# --- sync and the surfaces reading it --------------------------------------

def test_sync_stores_the_topic_activity_as_an_atividade_deadline(teste_de_software, tmp_path):
    result = sync.sync(_settings(tmp_path))

    assert result.ok, result.error
    assert [d.id for d in result.new_deadlines] == [TOPIC_DEADLINE_ID]
    assert result.classes[0].deadlines_new == 1
    (stored,) = _repo(tmp_path).get_deadlines(id_turma=ID_TURMA)
    assert (stored.id, stored.id_turma, stored.kind, stored.title, stored.date, stored.detail) == (
        TOPIC_DEADLINE_ID, ID_TURMA, "atividade", TOPIC_TITLE,
        "21/09/2026 a 23/09/2026", "tópico de aula",
    )


def test_sync_stores_tarefa_page_rows_as_tarefa_deadlines(teste_de_software, tmp_path):
    teste_de_software.tarefa_pages[ID_TURMA] = _fixture("tarefas.html")

    result = sync.sync(_settings(tmp_path))

    assert result.ok, result.error
    kinds = {d.id: d.kind for d in _repo(tmp_path).get_deadlines(id_turma=ID_TURMA)}
    assert kinds[TAREFA_DEADLINE_ID] == "tarefa"
    assert kinds[TOPIC_DEADLINE_ID] == "atividade"


def test_a_tarefa_the_portal_already_lists_is_not_stored_twice(teste_de_software, tmp_path):
    teste_de_software.tarefa_pages[ID_TURMA] = _fixture("tarefas.html")
    teste_de_software.portal_deadlines = [Deadline(
        id=PORTAL_EVENT_ID, id_turma=ID_TURMA, kind="tarefa", title=TAREFA_TITLE,
        date="21/09 à 23/09",
    )]

    sync.sync(_settings(tmp_path))

    ids = {d.id for d in _repo(tmp_path).get_deadlines(id_turma=ID_TURMA)}
    assert PORTAL_EVENT_ID in ids
    assert TAREFA_DEADLINE_ID not in ids


def test_resync_is_idempotent(teste_de_software, tmp_path):
    sync.sync(_settings(tmp_path))

    again = sync.sync(_settings(tmp_path))

    assert again.ok
    assert again.new_deadlines == []


def test_unparseable_tarefa_page_fails_the_class_but_keeps_the_rest(teste_de_software, tmp_path):
    teste_de_software.tarefa_pages[ID_TURMA] = _fixture("tarefas.html").replace(
        'class="listing"', 'class="grid"'
    )

    result = sync.sync(_settings(tmp_path))

    assert not result.ok
    assert result.error_stage == STAGE_PARSE
    (issue,) = result.classes[0].errors
    assert issue.stage == STAGE_PARSE
    assert [d.id for d in result.new_deadlines] == [TOPIC_DEADLINE_ID]


def test_unparseable_topics_surface_as_a_watch_error(fake_sigaa, logged_in, tmp_path):
    fake_sigaa.add_class(ID_TURMA, CLASS_CODE, "turma_topicos.html")
    fake_sigaa.pages[ID_TURMA] = fake_sigaa.pages[ID_TURMA].replace(
        'class="titulo"', 'class="cabecalho"'
    )

    run = watch.run_once(_settings(tmp_path), now=lambda: FIXED_NOW)

    assert run.status == watch.STATUS_FAILED
    (error,) = [e for e in run.events if e["type"] == "error"]
    assert (error["stage"], error["class_id"]) == (STAGE_PARSE, ID_TURMA)


def test_watch_reports_the_activity_once_the_teacher_posts_it(fake_sigaa, logged_in, tmp_path):
    fake_sigaa.add_class(ID_TURMA, CLASS_CODE, "news_empty.html")
    before = watch.run_once(_settings(tmp_path), now=lambda: FIXED_NOW)
    fake_sigaa.pages[ID_TURMA] = _fixture("turma_topicos.html")

    run = watch.run_once(_settings(tmp_path), now=lambda: FIXED_NOW)

    assert before.status == watch.STATUS_NO_CHANGES
    assert run.status == watch.STATUS_CHANGES

    (event,) = [e for e in run.events if e["type"] == "deadline"]
    assert (event["item_id"], event["class_code"], event["kind"], event["title"]) == (
        TOPIC_DEADLINE_ID, CLASS_CODE, "atividade", TOPIC_TITLE,
    )


def test_whats_new_lists_the_new_activity(teste_de_software, tmp_path):
    sync.sync(_settings(tmp_path))

    feed = whatsnew.collect(_repo(tmp_path))

    assert [d.id for d in feed.deadlines] == [TOPIC_DEADLINE_ID]


def test_mcp_lists_the_activity_by_class_and_serves_its_body_with_links(
    teste_de_software, tmp_path, monkeypatch
):
    sync.sync(_settings(tmp_path))
    monkeypatch.setattr(mcp_server, "_repo", lambda: _repo(tmp_path))

    for class_filter in (ID_TURMA, CLASS_CODE):
        listed = mcp_server.sigaa_list_deadlines(class_code=class_filter)
        assert [(d["id"], d["kind"]) for d in listed] == [(TOPIC_DEADLINE_ID, "atividade")]

    body = mcp_server.sigaa_get_tarefa_body(TOPIC_DEADLINE_ID)

    assert body["title"] == TOPIC_TITLE
    assert body["fields"]["Links"] == [SLIDES_URL, FORM_URL]
    assert FORM_URL in body["fields"]["Descrição"]
    assert body["fields"]["Período"] == "21/09/2026 a 23/09/2026"


def test_a_cached_tarefa_body_survives_a_resync(teste_de_software, tmp_path):
    teste_de_software.portal_deadlines = [Deadline(
        id=PORTAL_EVENT_ID, id_turma=ID_TURMA, kind="tarefa", title="Tarefa do portal",
        date="21/09 à 23/09",
    )]
    sync.sync(_settings(tmp_path))
    _repo(tmp_path).update_deadline_body(PORTAL_EVENT_ID, '{"Descrição": "cache"}')

    sync.sync(_settings(tmp_path))

    stored = {d.id: d for d in _repo(tmp_path).get_deadlines()}
    assert stored[PORTAL_EVENT_ID].body == '{"Descrição": "cache"}'
