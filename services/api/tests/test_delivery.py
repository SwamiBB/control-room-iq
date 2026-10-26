"""Which text each viewer group gets after approval: checked variant, template, or the approved base line."""

from agents.workflow import fallback_variants
from api.fallback_text import template_line
from api.main import ViewerPrefs, app, hub
from api_factories import RecordingSocket, match_state, moment, proposal
from crq_schemas import MomentKind, OverlayPacket, Persona, TeamStats
from fastapi.testclient import TestClient
from simulator.cli import build_meta

META = build_meta(42)
BASE = "Big chance for Ade Pike, xG 0.41, saved"


def _moment(kind=MomentKind.BIG_CHANCE):
    state = match_state(home=TeamStats(team="har", goals=1), away=TeamStats(team="nfu", goals=0))
    return moment(kind=kind, player="har-02", team="har", state=state)


def _viewer(lang="en", persona=Persona.FAN, access="none") -> RecordingSocket:
    ws = RecordingSocket()
    hub.viewers[ws] = ViewerPrefs(persona=persona, access=access, lang=lang)
    return ws


def _variant(lang, text, persona="fan", access="none") -> dict:
    return {"moment_id": "mo-1", "persona": persona, "access": access, "lang": lang, "text": text, "cites": ["e-1"]}


def _approve(variants, m=None, line=BASE) -> None:
    m = m or _moment()
    hub.meta, hub.moments[m.moment_id] = META, m
    p = proposal(line=line, moment_id=m.moment_id)
    hub.proposals[p.proposal_id] = p
    hub.results[m.moment_id] = {"variants": variants}
    TestClient(app).post(f"/proposals/{p.proposal_id}/approve")


def _seen(ws: RecordingSocket) -> OverlayPacket:
    (msg,) = ws.of_type("overlay")
    return OverlayPacket.model_validate(msg["item"])


def test_variant_that_passes_every_check_is_delivered():
    es = _viewer("es")
    _approve([_variant("es", "Gran ocasión para Ade Pike, xG 0,41, parada")])
    assert (_seen(es).line, _seen(es).lang) == ("Gran ocasión para Ade Pike, xG 0,41, parada", "es")


def test_failing_translation_falls_back_to_the_template_in_that_language():
    es = _viewer("es")
    _approve([_variant("es", "Gran ocasión para Ade Pike, xG 0,71, parada")])
    assert (_seen(es).line, _seen(es).lang) == (template_line(_moment(), "es", META), "es")


def test_failing_base_language_variant_falls_back_to_the_approved_line():
    en = _viewer("en", Persona.ANALYST)
    _approve([_variant("en", "Ade Pike's 5th big chance, xG 0.41", persona="analyst")])
    assert (_seen(en).line, _seen(en).lang) == (BASE, "en")


def test_high_stakes_moment_uses_templates_outside_the_base_language():
    es, en = _viewer("es"), _viewer("en")
    goal = _moment(MomentKind.GOAL)
    _approve([_variant("es", "¡GOL de Ade Pike!"), _variant("en", "Ade Pike scores!")], m=goal,
             line="GOAL Ade Pike")
    assert _seen(es).line == template_line(goal, "es", META)
    assert _seen(en).line == "Ade Pike scores!"


def test_no_template_and_failed_variant_airs_the_approved_line_marked_as_english():
    hi = _viewer("hi")
    _approve([_variant("hi", BASE)], m=_moment(MomentKind.MOMENTUM_SHIFT))
    assert (_seen(hi).line, _seen(hi).lang) == (BASE, "en")


def test_offline_fallback_english_never_airs_labelled_as_another_language():
    es, hi = _viewer("es"), _viewer("hi", access="deaf")
    m = _moment()
    requests = [(Persona.FAN, "none", "es", {}), (Persona.FAN, "deaf", "hi", {})]
    variants = [v.model_dump(mode="json") for v in fallback_variants(m, BASE, requests)]
    _approve(variants, m=m)
    assert _seen(es).line == template_line(m, "es", META)
    assert _seen(hi).line == template_line(m, "hi", META)


def test_each_viewer_group_is_audited_once_with_its_reasons():
    _viewer("es"), _viewer("es")  # two sockets, one viewer group
    console = RecordingSocket()
    hub.operators.add(console)
    _approve([_variant("es", "Gran ocasión para Ade Pike, xG 0,71")])
    (entry,) = hub.deliveries
    assert (entry["lang"], entry["source"], entry["failures"]) == ("es", "template", ["numbers"])
    assert entry["approval_id"] == hub.decisions[-1].entry_id
    assert console.of_type("deliveries")[0]["deliveries"] == [entry]
    assert TestClient(app).get("/deliveries").json() == [entry]
