#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xhs 一键流程：
1) 导入关键词到 daily_topics
2) 运行 xhs 定向爬取
3) 回填 xhs_note.topic_id
4) 回写语料标签字段
5) 回填 create_date_time 现实时间
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
MINDSPIDER_DIR = ROOT / "MindSpider"
DEFAULT_INPUT = ROOT / "Data" / "自建语料库 (1).csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="xhs 一键流程")
    parser.add_argument("--date", required=True, help="任务日期 YYYY-MM-DD")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="语料 CSV 路径")
    parser.add_argument("--max-keywords", type=int, default=5, help="每次导入/爬取关键词数")
    parser.add_argument("--max-notes", type=int, default=2, help="每个关键词抓取帖子数")
    parser.add_argument("--max-comments", type=int, default=20, help="每个帖子最多评论数")
    parser.add_argument(
        "--dedup-source",
        choices=["none", "db"],
        default="db",
        help="关键词去重来源，默认db去重",
    )
    parser.add_argument("--dedup-days", type=int, default=0, help="db去重时间窗口天数，0=全量历史")
    parser.add_argument("--python", default=sys.executable, help="Python 解释器路径")
    parser.add_argument("--dry-run", action="store_true", help="只做预演（不执行爬虫写入）")
    return parser.parse_args()


def run_cmd(cmd: List[str], cwd: Path) -> None:
    print(f"\n[RUN] {' '.join(shlex.quote(x) for x in cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main() -> None:
    args = parse_args()
    py = args.python

    # 先保证 create_date_time 字段存在（幂等）
    run_cmd([py, "migrate_platform_create_date_time_columns.py"], MINDSPIDER_DIR)

    import_cmd = [
        py,
        "import_language_keywords.py",
        "--input",
        args.input,
        "--platform",
        "xhs",
        "--date-mode",
        "fixed",
        "--date",
        args.date,
        "--max-keywords",
        str(args.max_keywords),
        "--dedup-source",
        args.dedup_source,
        "--dedup-days",
        str(args.dedup_days),
    ]
    if args.dry_run:
        run_cmd(import_cmd + ["--dry-run"], MINDSPIDER_DIR)
        run_cmd(
            [
                py,
                "backfill_topic_id.py",
                "--start-date",
                args.date,
                "--end-date",
                args.date,
                "--tables",
                "xhs_note",
                "--ignore-date",
                "--dry-run",
            ],
            MINDSPIDER_DIR,
        )
        run_cmd(
            [
                py,
                "enrich_weibo_note_from_corpus.py",
                "--platform",
                "xhs",
                "--start-date",
                args.date,
                "--end-date",
                args.date,
                "--scan-by",
                "topic-date",
                "--only-empty",
                "--dry-run",
            ],
            MINDSPIDER_DIR,
        )
        run_cmd(
            [
                py,
                "enrich_xhs_note_fallback.py",
                "--only-empty",
                "--dry-run",
            ],
            MINDSPIDER_DIR,
        )
        run_cmd(
            [
                py,
                "backfill_platform_create_date_time.py",
                "--tables",
                "xhs_note",
                "--only-empty",
                "--dry-run",
            ],
            MINDSPIDER_DIR,
        )
        print("\n[OK] dry-run completed.")
        return

    run_cmd(import_cmd, MINDSPIDER_DIR)
    run_cmd(
        [
            py,
            "main.py",
            "--deep-sentiment",
            "--date",
            args.date,
            "--platforms",
            "xhs",
            "--max-keywords",
            str(args.max_keywords),
            "--max-notes",
            str(args.max_notes),
            "--max-comments",
            str(args.max_comments),
        ],
        MINDSPIDER_DIR,
    )
    run_cmd(
        [
            py,
            "backfill_topic_id.py",
            "--start-date",
            args.date,
            "--end-date",
            args.date,
            "--tables",
            "xhs_note",
            "--ignore-date",
        ],
        MINDSPIDER_DIR,
    )
    run_cmd(
        [
            py,
            "enrich_weibo_note_from_corpus.py",
            "--platform",
            "xhs",
            "--start-date",
            args.date,
            "--end-date",
            args.date,
            "--scan-by",
            "topic-date",
            "--only-empty",
        ],
        MINDSPIDER_DIR,
    )
    run_cmd(
        [
            py,
            "enrich_xhs_note_fallback.py",
            "--only-empty",
        ],
        MINDSPIDER_DIR,
    )
    run_cmd(
        [py, "backfill_platform_create_date_time.py", "--tables", "xhs_note", "--only-empty"],
        MINDSPIDER_DIR,
    )
    print("\n[OK] xhs one-click workflow completed.")


if __name__ == "__main__":
    main()

