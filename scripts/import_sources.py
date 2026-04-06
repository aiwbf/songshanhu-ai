from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.knowledge import import_sources, rebuild_markdown_knowledge_base


def main() -> None:
    parser = argparse.ArgumentParser(description="Import structured admission sources.")
    parser.add_argument("--root", default=str(ROOT), help="Workspace root")
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "generated" / "knowledge_bundle.json"),
        help="Output bundle path",
    )
    parser.add_argument("--reference-date", default="2026-03-08", help="Reference date in YYYY-MM-DD")
    args = parser.parse_args()

    payload = import_sources(
        root=Path(args.root),
        output_path=Path(args.out),
        reference_date=args.reference_date,
    )
    wiki_stats = rebuild_markdown_knowledge_base(
        root=Path(args.root),
        bundle_path=Path(args.out),
        wiki_dir=Path(args.root) / "wiki",
    )
    print(
        json.dumps(
            {
                "output_path": str(Path(args.out).resolve()),
                "source_count": payload["stats"]["source_count"],
                "chunk_count": payload["stats"]["chunk_count"],
                "business_faq_chunk_count": payload["stats"]["business_faq_chunk_count"],
                "source_page_count": wiki_stats["source_page_count"],
                "topic_page_count": wiki_stats["topic_page_count"],
                "year_page_count": wiki_stats["year_page_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
