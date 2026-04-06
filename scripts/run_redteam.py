from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation import evaluate_dataset, write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the admissions red-team suite.")
    parser.add_argument(
        "--dataset",
        default=str(ROOT / "evals" / "datasets" / "redteam.json"),
        help="Path to the red-team dataset JSON file.",
    )
    parser.add_argument(
        "--failure-modes",
        default=str(ROOT / "evals" / "failure_modes" / "top20.json"),
        help="Path to the failure mode library JSON file.",
    )
    parser.add_argument(
        "--policy",
        default=str(ROOT / "data" / "seed" / "openclaw_policy.json"),
        help="Path to the OpenClaw security policy JSON file.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(ROOT / "evals" / "reports"),
        help="Directory where reports should be written.",
    )
    args = parser.parse_args()

    report_dir = Path(args.report_dir).resolve()
    json_path = report_dir / "latest_redteam_report.json"
    markdown_path = report_dir / "latest_redteam_report.md"

    summary = evaluate_dataset(
        dataset_path=Path(args.dataset).resolve(),
        failure_modes_path=Path(args.failure_modes).resolve(),
        policy_path=Path(args.policy).resolve(),
    )
    write_report(summary, json_path=json_path, markdown_path=markdown_path)

    print(
        json.dumps(
            {
                "dataset": str(Path(args.dataset).resolve()),
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "overall_pass_rate": summary["overall_pass_rate"],
                "metrics": summary["metrics"],
                "release_blockers": len(summary["release_blockers"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
