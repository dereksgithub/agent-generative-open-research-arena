"""Tests for the typed simulation state model."""

from agora.simulation.state import (
    LocationState,
    RouteState,
    SimulationState,
)


def test_state_has_stable_run_id():
    s = SimulationState()
    assert len(s.run_id) == 12
    assert s.run_id.isalnum()


def test_event_id_increments():
    s = SimulationState()
    assert s.next_event_id() == 0
    assert s.next_event_id() == 1
    assert s.next_event_id() == 2


def test_routes_from_filters_by_location():
    s = SimulationState(routes=[
        RouteState("a", "b", "drive", 10, 10),
        RouteState("a", "c", "transit", 20, 20),
        RouteState("b", "a", "drive", 10, 10),
    ])
    from_a = s.routes_from("a")
    assert len(from_a) == 2
    assert all(r.from_location == "a" for r in from_a)

    from_b = s.routes_from("b")
    assert len(from_b) == 1


def test_snapshot_for_agent():
    s = SimulationState(
        scenario_id="scenario-1",
        tick=5,
        tick_unit="hour",
        locations={
            "home": LocationState(
                "home",
                "Home",
                "residential",
                None,
                0,
                0,
                resources={"parking_spaces": 10},
            ),
        },
        routes=[
            RouteState("home", "office", "drive", 15, 15),
        ],
    )
    snap = s.snapshot_for_agent("home")
    assert snap["tick"] == 5
    assert snap["scenario_id"] == "scenario-1"
    assert len(snap["routes_from"]["home"]) == 1
    assert snap["routes_from"]["home"][0]["mode"] == "drive"
    assert snap["current_location_resources"]["parking_spaces"] == 10


def test_to_snapshot_serializes_world_state():
    s = SimulationState(
        tick=5,
        tick_unit="hour",
        locations={
            "home": LocationState(
                "home",
                "Home",
                "residential",
                10,
                0,
                0,
                occupant_ids=["alice", "bob"],
                resources={"parking_spaces": 8},
            ),
        },
        routes=[
            RouteState("home", "office", "drive", 15, 22.5),
        ],
    )
    snap = s.to_snapshot()
    assert snap["tick"] == 5
    assert snap["tick_unit"] == "hour"
    assert snap["locations"][0]["occupant_count"] == 2
    assert snap["locations"][0]["resources"]["parking_spaces"] == 8
    assert snap["routes"][0]["base_travel_time"] == 15
    assert snap["routes"][0]["current_travel_time"] == 22.5


def test_get_location():
    s = SimulationState(locations={
        "a": LocationState("a", "Place A", "residential", None, 0, 0),
    })
    assert s.get_location("a") is not None
    assert s.get_location("nonexistent") is None


def test_location_occupancy():
    loc = LocationState("a", "Place A", "residential", capacity=10, x=0, y=0)
    assert loc.occupant_ids == []
    loc.occupant_ids.append("agent_1")
    assert "agent_1" in loc.occupant_ids


def test_route_state_tracks_base_and_current():
    r = RouteState("a", "b", "drive", base_travel_time=15, current_travel_time=15)
    assert r.base_travel_time == 15
    r.current_travel_time = 37.5  # after intervention
    assert r.base_travel_time == 15  # base unchanged
    assert r.current_travel_time == 37.5
