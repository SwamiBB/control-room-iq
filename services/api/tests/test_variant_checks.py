"""Code checks every AI language/persona variant must pass before it can air."""

import pytest
from api.variant_checks import build_context, check_variant
from api_factories import match_state, moment, proposal
from crq_schemas import NarrativeVariant, OverlayLayer, TeamStats
from simulator.cli import build_meta

META = build_meta(42)  # Harbor City (Eli Arden, Ade Pike, ...) v Northfield United (Oli Arden, Cato Hart, ...)
BASE = "Big chance for Ade Pike, xG 0.41, saved"


def _ctx(base: str = BASE, layer=OverlayLayer.LOWER_THIRD):
    state = match_state(home=TeamStats(team="har", goals=1, xg=1.23, possession_pct=56.0),
                        away=TeamStats(team="nfu", goals=0, xg=0.4, possession_pct=44.0))
    m = moment(state=state, event_ids=["e-1", "e-2"])
    return build_context(proposal(line=base, layer=layer), m, META)


def _failures(text: str, lang: str = "es", **extra) -> list[str]:
    v = NarrativeVariant(moment_id="mo-1", persona="fan", lang=lang, text=text, cites=extra.pop("cites", ["e-1"]),
                         **extra)
    return check_variant(v, _ctx())


def test_faithful_spanish_variant_passes():
    assert _failures("Gran ocasión para Ade Pike, xG 0,41, parada") == []


@pytest.mark.parametrize("text", ["Gran ocasión para Ade Pike, xG 0,61, parada",  # changed number
                                  "Ade Pike falla su 3ª ocasión, xG 0,41"])        # invented count
def test_invented_numbers_fail(text):
    assert "numbers" in _failures(text)


def test_dropping_a_number_is_allowed_for_simpler_personas():
    assert _failures("Gran ocasión para Ade Pike, parada") == []


def test_numbers_from_the_moment_state_are_allowed_at_their_display_precision():
    assert _failures("Ade Pike, xG 0,41. Marcador 1 a 0, xG 1,2-0,4, posesión 56%") == []


def test_devanagari_digits_are_read_as_numbers():
    assert "numbers" in _failures("Ade Pike का बड़ा मौका, xG ०.७१", lang="hi")
    assert _failures("Ade Pike का बड़ा मौका, xG ०.४१", lang="hi") == []


def test_changed_or_transliterated_player_name_fails():
    assert "names" in _failures("Gran ocasión para Adé Pyke, xG 0,41")
    assert "names" in _failures("एडे पाइक का बड़ा मौका, xG 0.41", lang="hi")


def test_player_not_in_the_approved_line_fails():
    assert "names" in _failures("Gran ocasión para Ade Pike tras pase de Cato Hart, xG 0,41")


def test_surname_only_and_team_names_are_allowed():
    assert _failures("Gran ocasión de Pike para Harbor City, xG 0,41") == []


def test_citing_events_outside_the_moment_fails():
    assert "cites" in _failures("Gran ocasión para Ade Pike, xG 0,41", cites=["e-99"])


def test_text_longer_than_the_layer_allows_fails():
    assert "length" in _failures("Gran ocasión para Ade Pike, xG 0,41, " + "muy " * 30 + "clara")


@pytest.mark.parametrize(("lang", "text"), [("es", "Ade Pike, xG 0,41: el árbitro se equivocó"),
                                            ("en", "Ade Pike, xG 0.41, the referee got it wrong"),
                                            ("hi", "Ade Pike का मौका, xG 0.41, सट्टा")])
def test_banned_topics_fail(lang, text):
    assert "banned_topic" in _failures(text, lang=lang)


def test_low_faithfulness_fails_and_unevaluated_passes():
    assert "faithfulness" in _failures("Gran ocasión para Ade Pike, xG 0,41", faithfulness=0.6)
    assert _failures("Gran ocasión para Ade Pike, xG 0,41", faithfulness=None) == []


def test_untranslated_text_fails():
    # The offline fallback copies the English line into every language; it must never air as Spanish/Hindi.
    assert "untranslated" in _failures(BASE + ". The score is 1 to 0.", lang="es")
    assert "untranslated" in _failures(BASE, lang="hi")


def test_base_language_variant_is_not_checked_for_translation():
    assert _failures(BASE + ". The score is 1 to 0.", lang="en") == []
