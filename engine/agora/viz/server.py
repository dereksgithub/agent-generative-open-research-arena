"""Lightweight HTTP server for the AGORA visualization shell.

Serves:
  GET /                       — the single-page app (index.html)
  GET /static/<path>          — CSS / JS assets
  GET /api/runs               — list all available runs
  GET /api/runs/<run_path>/metadata.json    — run metadata
  GET /api/runs/<run_path>/<filename>       — any run output file
  GET /api/scenarios          — list example scenario files
  POST /api/runs/launch       — launch a new heuristic run and return its path
"""

from __future__ import annotations

import json
import logging
import mimetypes
import subprocess
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal

import yaml

logger = logging.getLogger(__name__)

VizMode = Literal["dashboard", "spatial"]

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DASHBOARD_STATIC_DIR = _REPO_ROOT / "viz" / "src"
_SPATIAL_APP_DIR = _REPO_ROOT / "viz" / "spatial"
_SPATIAL_DIST_DIR = _SPATIAL_APP_DIR / "dist"
_SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scenarios"
_REQUIRED_RUN_FILES = (
    "scenario.yaml",
    "metadata.json",
    "decisions.jsonl",
    "aggregate.csv",
    "agent_states.jsonl",
)


def _resolve_static_dir(mode: VizMode) -> Path:
    if mode == "dashboard":
        return _DASHBOARD_STATIC_DIR

    if mode != "spatial":
        raise ValueError(f"Unsupported viz mode: {mode}")

    spatial_index = _SPATIAL_DIST_DIR / "index.html"
    if spatial_index.exists():
        return _SPATIAL_DIST_DIR

    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=_SPATIAL_APP_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Spatial mode requires a built frontend, but `npm` is not available. "
            "Run `npm install && npm run build` in `viz/spatial`."
        ) from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or str(exc)).strip().splitlines()
        summary = details[-1] if details else str(exc)
        raise RuntimeError(
            "Failed to build the spatial frontend automatically. "
            f"Run `npm install && npm run build` in `viz/spatial`. Build error: {summary}"
        ) from exc

    if result.returncode != 0 or not spatial_index.exists():
        raise RuntimeError(
            "Spatial frontend build did not produce `viz/spatial/dist/index.html`."
        )

    return _SPATIAL_DIST_DIR


class VizHandler(SimpleHTTPRequestHandler):
    """Request handler for the AGORA visualization server."""

    runs_dir: Path = Path("runs")
    scenarios_dir: Path = _SCENARIOS_DIR
    static_dir: Path = _DASHBOARD_STATIC_DIR

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "" or path == "/":
            self._serve_file(self.static_dir / "index.html", "text/html")
        elif path.startswith("/static/"):
            rel = path[len("/static/"):]
            self._serve_static(rel)
        elif path == "/api/runs":
            self._api_list_runs()
        elif path.startswith("/api/runs/"):
            self._api_serve_run_file(path[len("/api/runs/"):])
        elif path == "/api/scenarios":
            self._api_list_scenarios()
        else:
            # Try serving from static dir as fallback
            rel = path.lstrip("/")
            candidate = self.static_dir / rel
            if candidate.exists() and candidate.is_file():
                ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
                self._serve_file(candidate, ctype)
            else:
                self._json_response(404, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/runs/launch":
            self._api_launch_run()
        else:
            self._json_response(404, {"error": "Not found"})

    # -- API handlers ----------------------------------------------------------

    def _api_list_runs(self) -> None:
        """List all available runs grouped by scenario."""
        runs: list[dict[str, Any]] = []
        runs_dir = self.runs_dir
        if not runs_dir.exists():
            self._json_response(200, {"runs": []})
            return

        for scenario_dir in sorted(runs_dir.iterdir()):
            if not scenario_dir.is_dir():
                continue
            for run_dir in sorted(scenario_dir.iterdir(), reverse=True):
                if not run_dir.is_dir():
                    continue
                runs.append(_summarize_run_dir(run_dir, scenario_dir.name))

        runs.sort(
            key=lambda run: (
                run.get("ready", False),
                str(run.get("timestamp", "")),
                str(run.get("path", "")),
            ),
            reverse=True,
        )

        self._json_response(200, {"runs": runs})

    def _api_serve_run_file(self, rel_path: str) -> None:
        """Serve a file from a run output directory."""
        rel_path = urllib.parse.unquote(rel_path)
        # Security: prevent path traversal
        full = (self.runs_dir / rel_path).resolve()
        if not str(full).startswith(str(self.runs_dir.resolve())):
            self._json_response(403, {"error": "Forbidden"})
            return
        if not full.exists() or not full.is_file():
            self._json_response(404, {"error": f"File not found: {rel_path}"})
            return

        ctype = mimetypes.guess_type(str(full))[0] or "application/octet-stream"
        # JSONL files should be served as application/jsonl
        if full.suffix == ".jsonl":
            ctype = "application/x-jsonlines"
        self._serve_file(full, ctype)

    def _api_list_scenarios(self) -> None:
        """List available example scenario files."""
        scenarios: list[dict[str, str]] = []
        examples_dir = self.scenarios_dir / "examples"
        if examples_dir.exists():
            for f in sorted(examples_dir.glob("*.yaml")):
                scenarios.append({
                    "name": f.stem,
                    "path": str(f),
                    "filename": f.name,
                })
        self._json_response(200, {"scenarios": scenarios})

    def _api_launch_run(self) -> None:
        """Launch a new simulation run and return the result path."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            params = json.loads(body)
        except json.JSONDecodeError:
            self._json_response(400, {"error": "Invalid JSON body"})
            return

        scenario_path = params.get("scenario_path", "")
        seed = params.get("seed")

        if not scenario_path:
            self._json_response(400, {"error": "scenario_path is required"})
            return

        scenario_file = Path(scenario_path)
        if not scenario_file.exists():
            self._json_response(404, {"error": f"Scenario not found: {scenario_path}"})
            return

        try:
            from agora.simulation.runner import run_scenario
            result = run_scenario(
                scenario_path=scenario_file,
                seed=int(seed) if seed is not None else None,
                use_llm=False,
            )
            self._json_response(200, {
                "output_dir": str(result.output_dir),
                "run_path": f"{result.scenario_name}/{result.output_dir.name}",
                "run_id": result.run_id,
                "total_decisions": result.total_decisions,
            })
        except Exception as exc:
            logger.exception("Failed to launch run")
            self._json_response(500, {"error": str(exc)})

    # -- helpers ---------------------------------------------------------------

    def _serve_file(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._json_response(404, {"error": "Not found"})

    def _serve_static(self, rel_path: str) -> None:
        full = (self.static_dir / rel_path).resolve()
        if not str(full).startswith(str(self.static_dir.resolve())):
            self._json_response(403, {"error": "Forbidden"})
            return
        if not full.exists() or not full.is_file():
            self._json_response(404, {"error": f"Static file not found: {rel_path}"})
            return
        ctype = mimetypes.guess_type(str(full))[0] or "application/octet-stream"
        self._serve_file(full, ctype)

    def _json_response(self, status: int, data: Any) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(format, *args)


def _summarize_run_dir(run_dir: Path, scenario_name: str) -> dict[str, Any]:
    """Build a viewer-friendly summary for one run directory."""
    issues: list[str] = []

    for filename in _REQUIRED_RUN_FILES:
        if not (run_dir / filename).exists():
            issues.append(f"missing {filename}")

    metadata = _load_json_file(run_dir / "metadata.json", issues)
    scenario = _load_yaml_file(run_dir / "scenario.yaml", issues)
    simulation = scenario.get("simulation") if isinstance(scenario.get("simulation"), dict) else {}
    agents = scenario.get("agents") if isinstance(scenario.get("agents"), list) else []

    return {
        "path": f"{scenario_name}/{run_dir.name}",
        "scenario": metadata.get("scenario_name") or scenario.get("name") or scenario_name,
        "timestamp": run_dir.name,
        "run_id": metadata.get("run_id") or run_dir.name,
        "seed": _coerce_int(metadata.get("seed"), _coerce_int(simulation.get("seed"), None)),
        "total_ticks": _coerce_int(
            metadata.get("total_ticks"),
            _coerce_int(simulation.get("ticks"), 0),
        ),
        "total_decisions": _coerce_int(metadata.get("total_decisions"), 0),
        "total_agents": _coerce_int(metadata.get("total_agents"), len(agents)),
        "decision_mode": metadata.get("decision_mode") or "unknown",
        "domain": metadata.get("domain") or scenario.get("domain") or "",
        "ready": len(issues) == 0,
        "issues": issues,
    }


def _load_json_file(path: Path, issues: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        issues.append(f"invalid {path.name}")
        return {}
    return data if isinstance(data, dict) else {}


def _load_yaml_file(path: Path, issues: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        issues.append(f"invalid {path.name}")
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_int(value: Any, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    runs_dir: Path = Path("runs"),
    open_browser: bool = True,
    mode: VizMode = "dashboard",
) -> None:
    """Start the viz server."""
    VizHandler.runs_dir = runs_dir.resolve()
    VizHandler.scenarios_dir = _SCENARIOS_DIR
    VizHandler.static_dir = _resolve_static_dir(mode).resolve()

    server = ThreadingHTTPServer((host, port), VizHandler)
    url = f"http://{host}:{port}"
    print(f"AGORA viz server running at {url}")
    print(f"Mode: {mode}")
    print(f"Serving runs from: {runs_dir.resolve()}")
    print("Press Ctrl+C to stop.\n")

    if open_browser:
        import webbrowser
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
