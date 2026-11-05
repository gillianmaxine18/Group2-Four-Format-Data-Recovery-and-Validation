"""Command line entry point:  python main.py --config config.json"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.common import ProcessingError, load_config
from src.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, load the configuration and run the pipeline."""
    parser = argparse.ArgumentParser(description="Four-format data recovery and validation")
    parser.add_argument("--config", required=True, help="path to config.json")
    parser.add_argument("--reporting-year", type=int, help="override reporting_year from the config")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ProcessingError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    if args.reporting_year is not None:
        config["reporting_year"] = args.reporting_year
    return run_pipeline(config, Path(args.config).resolve().parent)


if __name__ == "__main__":
    sys.exit(main())
