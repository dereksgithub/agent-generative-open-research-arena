"""AGORA command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agora",
        description="AGORA — Agent-Generative Open Research Arena",
    )
    sub = parser.add_subparsers(dest="command")

    # --- agora run -----------------------------------------------------------
    run_p = sub.add_parser("run", help="Run a scenario")
    run_p.add_argument("scenario", type=Path, help="Path to a scenario YAML file")
    run_p.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility"
    )
    run_p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: runs/<scenario-name>/<timestamp>)",
    )
    run_p.add_argument(
        "--no-llm",
        action="store_true",
        help="Use heuristic agent decisions instead of LLM calls (default)",
    )

    # LLM configuration flags
    llm_group = run_p.add_argument_group("LLM options", "Configure LLM-backed agent reasoning")
    llm_group.add_argument(
        "--llm",
        action="store_true",
        help="Enable LLM-backed agent decisions",
    )
    llm_group.add_argument(
        "--llm-provider",
        type=str,
        default="openai",
        help="LLM provider name or alias (default: openai)",
    )
    llm_group.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="Model name (default: provider's default)",
    )
    llm_group.add_argument(
        "--llm-api-key",
        type=str,
        default=None,
        help="API key (default: from environment variable)",
    )
    llm_group.add_argument(
        "--llm-base-url",
        type=str,
        default=None,
        help="Base URL for local/custom endpoints",
    )
    llm_group.add_argument(
        "--llm-temperature",
        type=float,
        default=0.4,
        help="Sampling temperature (default: 0.4)",
    )
    llm_group.add_argument(
        "--llm-max-tokens",
        type=int,
        default=512,
        help="Maximum completion tokens per request (default: 512)",
    )
    llm_group.add_argument(
        "--llm-timeout",
        type=float,
        default=60.0,
        help="HTTP timeout per request in seconds (default: 60.0)",
    )
    llm_group.add_argument(
        "--llm-max-retries",
        type=int,
        default=2,
        help="Retry count for transient provider errors (default: 2)",
    )
    llm_group.add_argument(
        "--llm-max-consecutive-failures",
        type=int,
        default=3,
        help="Disable LLM mode after this many consecutive failed decisions (default: 3)",
    )
    llm_group.add_argument(
        "--llm-cache-dir",
        type=Path,
        default=None,
        help="Directory for prompt caching (default: <output-dir>/.prompt_cache)",
    )

    # --- agora viz -----------------------------------------------------------
    viz_p = sub.add_parser("viz", help="Launch the run viewer in the browser")
    viz_p.add_argument(
        "--port", type=int, default=8080, help="Server port (default: 8080)"
    )
    viz_p.add_argument(
        "--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)"
    )
    viz_p.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Directory containing run outputs (default: runs/)",
    )
    viz_p.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't auto-open the browser",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "run":
        return _cmd_run(args)

    if args.command == "viz":
        return _cmd_viz(args)

    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Execute `agora run <scenario>`."""
    from agora.simulation.runner import run_scenario

    scenario_path: Path = args.scenario.resolve()
    if not scenario_path.exists():
        print(f"Error: scenario file not found: {scenario_path}", file=sys.stderr)
        return 1

    # Determine LLM mode: --llm enables it, --no-llm disables it
    use_llm = getattr(args, "llm", False) and not args.no_llm

    try:
        result = run_scenario(
            scenario_path=scenario_path,
            seed=args.seed,
            output_dir=args.output_dir,
            use_llm=use_llm,
            llm_provider=args.llm_provider,
            llm_model=args.llm_model,
            llm_api_key=args.llm_api_key,
            llm_base_url=args.llm_base_url,
            llm_temperature=args.llm_temperature,
            llm_max_tokens=args.llm_max_tokens,
            llm_timeout=args.llm_timeout,
            llm_max_retries=args.llm_max_retries,
            llm_cache_dir=args.llm_cache_dir,
            llm_max_consecutive_failures=args.llm_max_consecutive_failures,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"\nRun complete. Output: {result.output_dir}")
    if result.llm_accounting:
        acct = result.llm_accounting
        print(f"LLM accounting: {acct['total_requests']} requests, "
              f"{acct['total_tokens']} tokens, "
              f"{acct['total_latency_ms']}ms total latency, "
              f"{acct['total_cached']} cache hits")
    return 0


def _cmd_viz(args: argparse.Namespace) -> int:
    """Execute `agora viz` — launch the browser-based run viewer."""
    from agora.viz.server import run_server

    run_server(
        host=args.host,
        port=args.port,
        runs_dir=args.runs_dir,
        open_browser=not args.no_browser,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
