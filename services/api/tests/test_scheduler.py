"""Placement rules (scheduler.py), with hand-built on-air lists."""

from datetime import UTC, datetime

from api.scheduler import STORY_GAP_MS, hold_advice, is_big_moment, place
from api_factories import match_state, moment, proposal
from crq_schemas import MomentKind, OverlayLayer, OverlayPacket

NOW = 600_000


def packet(cue: str, layer=OverlayLayer.LOWER_THIRD, t_in=NOW - 2_000, t_out=NOW + 8_000, priority=5,
           source=None, replaces=()) -> OverlayPacket:
    return OverlayPacket(cue_id=cue, match_id="m", layer=layer, t_in_ms=t_in, t_out_ms=t_out, period=1,
                         clock_ms=t_in, priority=priority, replaces=list(replaces), line="On air",
                         source_proposal_id=source or f"p-{cue}", approval_id="d-1", approved_by="operator",
                         approved_at=datetime(2026, 10, 27, tzinfo=UTC))


def card(pid="p-new", layer=OverlayLayer.LOWER_THIRD, length=10_000, **kw):
    return proposal(pid, layer=layer, t_start_ms=0, t_end_ms=length, moment_id=kw.pop("moment_id", "mo-new"), **kw)


STORIES = {"p-old": "mo-old", "p-other": "mo-other"}


def moment_of(pid: str):
    return STORIES.get(pid)


def test_a_free_layer_airs_at_once_for_the_slot_length():
    slot = place(card(), [], NOW, moment())
    assert (slot.t_in_ms, slot.t_out_ms, slot.replaces, slot.late) == (NOW, NOW + 10_000, [], False)


def test_a_busy_layer_waits_for_the_earliest_free_gap():
    slot = place(card(), [packet("old")], NOW, moment())
    assert slot.t_in_ms == NOW + 8_000 and "free" in slot.reason


def test_another_layer_is_not_a_collision():
    assert place(card(layer=OverlayLayer.TICKER), [packet("old")], NOW, moment()).t_in_ms == NOW


def test_a_graphic_stays_up_at_least_its_minimum():
    slot = place(card(length=1_000, min_hold_ms=4_000), [], NOW, moment())
    assert slot.t_out_ms - slot.t_in_ms == 4_000


def test_one_story_at_a_time_on_the_main_layers():
    other = packet("other", layer=OverlayLayer.STAT_PANEL, t_in=NOW - 5_000, t_out=NOW + 10_000, source="p-other")
    slot = place(card(layer=OverlayLayer.LOWER_THIRD), [other], NOW, moment(), moment_of)
    assert slot.t_in_ms == NOW - 5_000 + STORY_GAP_MS and "one story" in slot.reason


def test_the_same_story_and_the_ticker_are_not_held_back():
    same = packet("old", layer=OverlayLayer.STAT_PANEL, t_in=NOW - 5_000, t_out=NOW + 10_000, source="p-old")
    assert place(card(moment_id="mo-old"), [same], NOW, moment(), moment_of).t_in_ms == NOW
    other = packet("other", layer=OverlayLayer.STAT_PANEL, t_in=NOW - 5_000, source="p-other")
    assert place(card(layer=OverlayLayer.TICKER), [other], NOW, moment(), moment_of).t_in_ms == NOW


def test_a_goal_cuts_the_lower_third_and_the_stat_panel():
    on_air = [packet("lt"), packet("sp", layer=OverlayLayer.STAT_PANEL), packet("tk", layer=OverlayLayer.TICKER)]
    slot = place(card(layer=OverlayLayer.FULL_SCREEN, priority=1), on_air, NOW, moment(kind=MomentKind.GOAL))
    assert slot.t_in_ms == NOW and sorted(slot.replaces) == ["lt", "sp"]


def test_a_red_card_is_a_big_moment_and_a_yellow_is_not():
    assert is_big_moment(moment(kind=MomentKind.CARD, summary="Red card Cato Hart"))
    assert is_big_moment(moment(kind=MomentKind.CARD, summary="Second yellow, sent off Cato Hart"))
    assert not is_big_moment(moment(kind=MomentKind.CARD, summary="Yellow card Cato Hart"))


def test_a_goal_routine_follow_up_starts_after_its_offset_and_does_not_cut():
    item = card(layer=OverlayLayer.TICKER, package_id="pk-1", package_seq=2, package_offset_ms=25_000)
    slot = place(item, [packet("lt")], NOW, moment(kind=MomentKind.GOAL))
    assert slot.t_in_ms == NOW + 25_000 and slot.replaces == []


def test_a_new_caption_cuts_the_running_one():
    slot = place(card(layer=OverlayLayer.CAPTION), [packet("cap", layer=OverlayLayer.CAPTION)], NOW, moment())
    assert slot.t_in_ms == NOW and slot.replaces == ["cap"]


def test_held_back_past_its_max_delay_it_cuts_a_lower_priority_graphic():
    long_one = packet("long", t_out=NOW + 60_000, priority=7)
    slot = place(card(priority=2, max_delay_ms=15_000), [long_one], NOW, moment())
    assert slot.t_in_ms == NOW and slot.replaces == ["long"]


def test_held_back_past_its_max_delay_by_a_higher_priority_graphic_it_airs_late():
    long_one = packet("long", t_out=NOW + 60_000, priority=1)
    slot = place(card(priority=5, max_delay_ms=15_000), [long_one], NOW, moment())
    assert slot.t_in_ms == NOW + 60_000 and slot.late


def test_a_replaced_or_finished_packet_does_not_block():
    replaced = packet("lt")
    cutter = packet("goal", layer=OverlayLayer.FULL_SCREEN, t_in=NOW - 1_000, replaces=["lt"])
    finished = packet("done", t_in=NOW - 20_000, t_out=NOW - 1)
    assert place(card(), [replaced, cutter, finished], NOW, moment()).t_in_ms == NOW


def test_hold_advice_only_when_pressure_rises_and_not_on_a_goal():
    rising = match_state(pressure_trend="rising")
    advice = hold_advice(moment(state=rising), NOW)
    assert advice.recommend_hold and advice.until_play_ms > NOW
    assert not hold_advice(moment(kind=MomentKind.GOAL, state=rising), NOW).recommend_hold
    assert not hold_advice(moment(), NOW).recommend_hold
