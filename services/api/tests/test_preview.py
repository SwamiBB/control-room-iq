"""Preview before firing: the operator picks viewer groups and sees what each would get, and why."""

from api.delivery import DeliveryPlan
from api.preview import PreviewContext, parse_view, preview, view_key, viewer_groups
from api.variant_checks import build_context
from api_factories import match_state, proposal
from crq_schemas import NarrativeVariant, Persona, TeamStats


def _variant(persona: str, lang: str, text: str, access: str = "none") -> NarrativeVariant:
    return NarrativeVariant(moment_id="mo-1", persona=persona, access=access, lang=lang, text=text)


def _plan(p, variants=(), templates=None, high_stakes=False, override=False) -> DeliveryPlan:
    return DeliveryPlan(variants=tuple(variants), ctx=build_context(p, None, None), templates=templates or {},
                        is_high_stakes=high_stakes, is_override=override)


def test_views_parse_with_or_without_a_side():
    v = parse_view("newcomer.deaf.hi")
    assert (v.persona, v.access, v.lang, v.allegiance) == (Persona.NEWCOMER, "deaf", "hi", "neutral")
    assert parse_view("fan.none.es.away").allegiance == "away"
    assert view_key(parse_view("analyst.none.en.home")) == "analyst.none.en.home"


def test_unknown_views_are_refused():
    for bad in ("fan.none", "fan.none.fr", "fan.blind.en", "fan.none.en.visitors", "coach.none.en"):
        try:
            parse_view(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} should be refused")


def test_picker_offers_every_combination_for_the_configured_languages():
    groups = viewer_groups(("en", "es", "hi"))
    assert len(groups) == 3 * 2 * 3 * 3
    assert len({g.key for g in groups}) == len(groups)
    assert {g.lang for g in viewer_groups(("en",))} == {"en"}


def test_each_picked_group_shows_its_own_text_and_reason():
    p = proposal(line="Harbor City pressing hard.")
    plan = _plan(p, variants=[_variant("fan", "es", "Harbor City presiona fuerte.")],
                 templates={"hi": "Harbor City दबाव बना रहा है।"})
    views = [parse_view(k) for k in ("fan.none.en", "fan.none.es", "fan.none.hi")]
    en, es, hi = preview(p, plan, views).items
    assert (en.source, en.text, en.lang_shown) == ("base", "Harbor City pressing hard.", "en")
    assert (es.source, es.text, es.lang_shown) == ("variant", "Harbor City presiona fuerte.", "es")
    assert (hi.source, hi.lang_shown, hi.failures) == ("template", "hi", ["no_variant"])


def test_a_failed_variant_shows_why_and_falls_back_to_the_english_line():
    p = proposal(line="Harbor City pressing hard.")
    plan = _plan(p, variants=[_variant("fan", "hi", "Harbor City pressing hard.")])  # copied, not translated
    (item,) = preview(p, plan, [parse_view("fan.none.hi")]).items
    assert (item.source, item.text, item.lang_shown) == ("base", "Harbor City pressing hard.", "en")
    assert "untranslated" in item.failures


def test_a_typed_override_is_previewed_in_english_for_everyone():
    p = proposal(line="AI line")
    plan = _plan(p, variants=[_variant("fan", "es", "Línea IA")], override=True)
    items = preview(p, plan, [parse_view("fan.none.es")], PreviewContext(override_line="My own words")).items
    assert [(i.source, i.text, i.lang_shown) for i in items] == [("override", "My own words", "en")]


def test_supporters_see_the_score_from_their_side():
    state = match_state(home=TeamStats(team="har", goals=1), away=TeamStats(team="nor"))
    p = proposal()
    away, neutral = preview(p, _plan(p), [parse_view("fan.none.en.away"), parse_view("fan.none.en")],
                            PreviewContext(state=state)).items
    assert away.perspective["score"] == [0, 1] and away.perspective["score_text"] == "0–1 down"
    assert neutral.perspective is None
