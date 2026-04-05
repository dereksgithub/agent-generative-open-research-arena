"""Tests for the visualization server API (Phase 5)."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from agora.viz.server import _DASHBOARD_STATIC_DIR, VizHandler

# We test the handler directly by running a real HTTP server on an ephemeral port.


@pytest.fixture()
def run_output(tmp_path: Path) -> Path:
    """Create a minimal fake run directory structure."""
    runs_dir = tmp_path / "runs"
    scenario_dir = runs_dir / "morning_commute"
    run_dir = scenario_dir / "20260403_100000"
    run_dir.mkdir(parents=True)

    # metadata.json
    meta = {
        "agora_version": "0.1.0",
        "run_id": "abc123def456",
        "scenario_id": "morning_commute_v1",
        "scenario_name": "morning_commute",
        "domain": "transport",
        "decision_mode": "heuristic",
        "total_ticks": 4,
        "total_agents": 2,
        "total_decisions": 8,
        "seed": 42,
    }
    (run_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    # scenario.yaml
    (run_dir / "scenario.yaml").write_text(
        "\n".join([
            "id: morning_commute_v1",
            "name: morning_commute",
            "domain: transport",
            "simulation:",
            "  ticks: 4",
            "  tick_unit: hour",
            "  seed: 42",
            "locations:",
            "  - id: home",
            "    name: Home",
            "    type: residential",
            "    x: 0",
            "    y: 0",
            "routes: []",
            "agents:",
            "  - id: alice",
            "    name: Alice",
            "    role: commuter",
            "    traits: []",
            "    home_location: home",
            "  - id: bob",
            "    name: Bob",
            "    role: commuter",
            "    traits: []",
            "    home_location: home",
            "interventions: []",
            "kpis: []",
        ]),
        encoding="utf-8",
    )

    # decisions.jsonl
    decisions = [
        {"tick": 0, "agent_id": "alice", "action": "stay", "target": "home", "reasoning": "No goal.", "metadata": {}},
        {"tick": 0, "agent_id": "bob", "action": "stay", "target": "home", "reasoning": "Resting.", "metadata": {}},
    ]
    (run_dir / "decisions.jsonl").write_text(
        "\n".join(json.dumps(d) for d in decisions), encoding="utf-8"
    )

    # aggregate.csv
    (run_dir / "aggregate.csv").write_text(
        "tick,travel_count,stay_count,total_agents\n0,0,2,2\n1,2,0,2\n", encoding="utf-8"
    )

    # agent_states.jsonl
    (run_dir / "agent_states.jsonl").write_text(
        json.dumps({"tick": 0, "agent_id": "alice", "agent_name": "Alice", "role": "commuter", "location": "home", "action": "stay", "mode": "", "traits": []}) + "\n",
        encoding="utf-8",
    )

    # kpis.json
    (run_dir / "kpis.json").write_text(json.dumps({"run_id": "abc123def456", "kpis": {}}), encoding="utf-8")

    # events.jsonl
    (run_dir / "events.jsonl").write_text(
        json.dumps({"event_id": 0, "run_id": "abc123def456", "tick": 0, "event_type": "run_start"}) + "\n",
        encoding="utf-8",
    )

    return runs_dir


@pytest.fixture()
def viz_server(run_output: Path):
    """Start a viz server on an ephemeral port and yield (host, port)."""
    import socket
    from http.server import HTTPServer

    # Find a free port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    VizHandler.runs_dir = run_output.resolve()
    VizHandler.static_dir = _DASHBOARD_STATIC_DIR.resolve()

    server = HTTPServer(("127.0.0.1", port), VizHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield ("127.0.0.1", port)
    server.shutdown()


@pytest.fixture()
def viz_server_spatial(run_output: Path, tmp_path: Path):
    """Start a viz server with a fake built spatial frontend."""
    import socket
    from http.server import HTTPServer

    spatial_dir = tmp_path / "spatial-dist"
    assets_dir = spatial_dir / "assets"
    assets_dir.mkdir(parents=True)
    (spatial_dir / "index.html").write_text(
        "<html><body><h1>AGORA Spatial Viewer</h1><script src='/assets/spatial.js'></script></body></html>",
        encoding="utf-8",
    )
    (assets_dir / "spatial.js").write_text("console.log('spatial');", encoding="utf-8")

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    VizHandler.runs_dir = run_output.resolve()
    VizHandler.static_dir = spatial_dir.resolve()

    server = HTTPServer(("127.0.0.1", port), VizHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield ("127.0.0.1", port)
    server.shutdown()


def _get(host: str, port: int, path: str) -> tuple[int, str]:
    conn = HTTPConnection(host, port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    return resp.status, body


def _post(host: str, port: int, path: str, data: dict) -> tuple[int, str]:
    conn = HTTPConnection(host, port, timeout=5)
    body = json.dumps(data)
    conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    resp_body = resp.read().decode("utf-8")
    conn.close()
    return resp.status, resp_body


class TestVizAPI:
    def test_index_returns_html(self, viz_server):
        host, port = viz_server
        status, body = _get(host, port, "/")
        assert status == 200
        assert "AGORA" in body
        assert "<html" in body

    def test_api_runs_lists_runs(self, viz_server):
        host, port = viz_server
        status, body = _get(host, port, "/api/runs")
        assert status == 200
        data = json.loads(body)
        assert "runs" in data
        assert len(data["runs"]) == 1
        run = data["runs"][0]
        assert run["scenario"] == "morning_commute"
        assert run["run_id"] == "abc123def456"
        assert run["seed"] == 42
        assert run["ready"] is True
        assert run["issues"] == []

    def test_api_run_file_metadata(self, viz_server):
        host, port = viz_server
        status, body = _get(host, port, "/api/runs/morning_commute/20260403_100000/metadata.json")
        assert status == 200
        data = json.loads(body)
        assert data["run_id"] == "abc123def456"

    def test_api_run_file_decisions(self, viz_server):
        host, port = viz_server
        status, body = _get(host, port, "/api/runs/morning_commute/20260403_100000/decisions.jsonl")
        assert status == 200
        lines = body.strip().split("\n")
        assert len(lines) == 2

    def test_api_run_file_not_found(self, viz_server):
        host, port = viz_server
        status, body = _get(host, port, "/api/runs/morning_commute/20260403_100000/nonexistent.json")
        assert status == 404

    def test_api_run_path_traversal_blocked(self, viz_server):
        host, port = viz_server
        status, body = _get(host, port, "/api/runs/../../etc/passwd")
        assert status in (403, 404)

    def test_api_scenarios_lists_examples(self, viz_server):
        host, port = viz_server
        status, body = _get(host, port, "/api/scenarios")
        assert status == 200
        data = json.loads(body)
        assert "scenarios" in data
        # Should find the example scenarios from the repo
        names = [s["name"] for s in data["scenarios"]]
        assert "morning_commute" in names

    def test_api_launch_run(self, viz_server, monkeypatch):
        host, port = viz_server

        def fake_run_scenario(*, scenario_path, seed, use_llm):
            assert scenario_path.name == "morning_commute.yaml"
            assert seed == 42
            assert use_llm is False
            return SimpleNamespace(
                output_dir=Path("/tmp/agora_demo_output"),
                scenario_name="morning_commute",
                run_id="run123",
                total_decisions=120,
            )

        monkeypatch.setattr(
            "agora.simulation.runner.run_scenario",
            fake_run_scenario,
        )

        status, body = _post(
            host,
            port,
            "/api/runs/launch",
            {
                "scenario_path": str(
                    Path(__file__).resolve().parents[2]
                    / "scenarios"
                    / "examples"
                    / "morning_commute.yaml"
                ),
                "seed": 42,
            },
        )
        assert status == 200
        data = json.loads(body)
        assert data["run_path"] == "morning_commute/agora_demo_output"
        assert data["run_id"] == "run123"
        assert data["total_decisions"] == 120

    def test_api_not_found(self, viz_server):
        host, port = viz_server
        status, body = _get(host, port, "/api/nonexistent")
        assert status == 404

    def test_api_runs_marks_incomplete_runs(self, run_output):
        import socket
        from http.server import HTTPServer

        scenario_dir = run_output / "morning_commute"
        partial_run = scenario_dir / "20260403_090000"
        partial_run.mkdir(parents=True)
        (partial_run / "scenario.yaml").write_text("name: morning_commute\nsimulation:\n  ticks: 4\n", encoding="utf-8")
        (partial_run / "metadata.json").write_text(json.dumps({"scenario_name": "morning_commute"}), encoding="utf-8")

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        VizHandler.runs_dir = run_output.resolve()
        VizHandler.static_dir = _DASHBOARD_STATIC_DIR.resolve()
        server = HTTPServer(("127.0.0.1", port), VizHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            status, body = _get("127.0.0.1", port, "/api/runs")
        finally:
            server.shutdown()

        assert status == 200
        data = json.loads(body)
        assert len(data["runs"]) == 2
        ready_run = data["runs"][0]
        partial = data["runs"][1]
        assert ready_run["ready"] is True
        assert partial["ready"] is False
        assert "missing decisions.jsonl" in partial["issues"]
        assert "missing aggregate.csv" in partial["issues"]
        assert "missing agent_states.jsonl" in partial["issues"]

    def test_spatial_index_returns_html(self, viz_server_spatial):
        host, port = viz_server_spatial
        status, body = _get(host, port, "/")
        assert status == 200
        assert "Spatial Viewer" in body

    def test_spatial_assets_are_served(self, viz_server_spatial):
        host, port = viz_server_spatial
        status, body = _get(host, port, "/assets/spatial.js")
        assert status == 200
        assert "spatial" in body


class TestVizCLI:
    def test_cli_viz_help(self):
        from agora.cli import main
        # --help exits with SystemExit(0)
        with pytest.raises(SystemExit) as exc_info:
            main(["viz", "--help"])
        assert exc_info.value.code == 0

    def test_cli_viz_mode_is_forwarded(self, monkeypatch):
        from agora.cli import main

        captured = {}

        def fake_run_server(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("agora.viz.server.run_server", fake_run_server)

        result = main(["viz", "--mode", "spatial", "--no-browser"])

        assert result == 0
        assert captured["mode"] == "spatial"
        assert captured["open_browser"] is False

    def test_cli_viz_spatial_alias_sets_mode(self, monkeypatch):
        from agora.cli import main

        captured = {}

        def fake_run_server(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("agora.viz.server.run_server", fake_run_server)

        result = main(["viz", "--spatial", "--no-browser"])

        assert result == 0
        assert captured["mode"] == "spatial"
