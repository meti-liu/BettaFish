#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xhs 区间一键流程：
按日期区间逐天调用 run_xhs_one_click.py。
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
MINDSPIDER_DIR = ROOT / "MindSpider"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="xhs 区间一键流程")
    parser.add_argument("--start-date", required=True, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--input", default="", help="语料 CSV 路径（可选）")
    parser.add_argument("--max-keywords", type=int, default=5, help="每日期关键词数")
    parser.add_argument("--max-notes", type=int, default=2, help="每关键词帖子数")
    parser.add_argument("--max-comments", type=int, default=20, help="每帖子评论数")
    parser.add_argument(
        "--dedup-source",
        choices=["none", "db"],
        default="db",
        help="关键词去重来源，默认db去重",
    )
    parser.add_argument("--dedup-days", type=int, default=0, help="db去重时间窗口天数，0=全量历史")
    parser.add_argument("--python", default=sys.executable, help="Python 解释器路径")
    parser.add_argument("--dry-run", action="store_true", help="预演模式")
    parser.add_argument("--continue-on-error", action="store_true", help="单日失败时继续后续日期")
    return parser.parse_args()


def date_range(start: datetime, end: datetime):
    d = start
    while d <= end:
        yield d.date().isoformat()
        d += timedelta(days=1)


def run_cmd(cmd: List[str], cwd: Path) -> None:
    print(f"\n[RUN] {' '.join(shlex.quote(x) for x in cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def build_one_day_cmd(args: argparse.Namespace, day: str) -> List[str]:
    cmd = [
        args.python,
        "run_xhs_one_click.py",
        "--date",
        day,
        "--max-keywords",
        str(args.max_keywords),
        "--max-notes",
        str(args.max_notes),
        "--max-comments",
        str(args.max_comments),
        "--dedup-source",
        args.dedup_source,
        "--dedup-days",
        str(args.dedup_days),
    ]
    if args.input:
        cmd.extend(["--input", args.input])
    if args.dry_run:
        cmd.append("--dry-run")
    return cmd


def main() -> None:
    args = parse_args()
    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d")
    if end < start:
        raise ValueError("end-date 不能早于 start-date")

    success_days: List[str] = []
    failed_days: List[str] = []
    for day in date_range(start, end):
        cmd = build_one_day_cmd(args, day)
        try:
            run_cmd(cmd, MINDSPIDER_DIR)
            success_days.append(day)
        except subprocess.CalledProcessError:
            failed_days.append(day)
            if not args.continue_on_error:
                break

    print("\n=== xhs range one-click summary ===")
    print(f"success_days={len(success_days)}")
    if success_days:
        print("success_list=" + ",".join(success_days))
    print(f"failed_days={len(failed_days)}")
    if failed_days:
        print("failed_list=" + ",".join(failed_days))

    if failed_days and not args.continue_on_error:
        sys.exit(1)


if __name__ == "__main__":
    main()

