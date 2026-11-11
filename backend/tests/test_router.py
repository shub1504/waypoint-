"""Tests for prompt routing and free-form prompt handling (Phase 2)."""
import pytest

from app.router import heuristic_route


MANDATORY_PROMPTS = [
    ("delhi se indore train kal", "live_search"),
    ("cheapest flight DEL to BOM friday", "live_search"),
    ("is 12919 late?", "live_search"),
    ("mujhe kahin ghumne jana hai budget 5k", "trip_planning"),
    ("koi bhi trip suggest karo", "trip_planning"),
    ("write me a poem", "out_of_scope"),
    ("hello", "smalltalk"),
    ("delhi to mubmai flihgt", "live_search"),
]


@pytest.mark.parametrize("prompt,expected_route", MANDATORY_PROMPTS)
def test_heuristic_router_mandatory_cases(prompt, expected_route):
    decision = heuristic_route(prompt)
    assert decision.route == expected_route, f"Failed for prompt: '{prompt}' (got {decision.route}, expected {expected_route})"


def test_heuristic_router_entity_extraction():
    train_status = heuristic_route("is 12919 late?")
    assert train_status.route == "live_search"
    assert train_status.mode == "train"
    assert train_status.destination == "12919"

    flight_typo = heuristic_route("delhi to mubmai flihgt")
    assert flight_typo.route == "live_search"
    assert flight_typo.mode == "flight"

    flight_search = heuristic_route("cheapest flight DEL to BOM friday")
    assert flight_search.route == "live_search"
    assert flight_search.mode == "flight"

    planning = heuristic_route("mujhe kahin ghumne jana hai budget 5k")
    assert planning.route == "trip_planning"

    non_travel = heuristic_route("write me a poem about mountain trees")
    assert non_travel.route == "out_of_scope"
