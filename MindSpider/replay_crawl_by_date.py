#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按日期区间回放 DeepSentimentCrawling，避免手工逐天执行。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

from config import settings


PROJECT_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按日期区间批量回放爬虫")
    parser.add_argument("--start-date", required=True, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--platforms",
        nargs="+",
        default=[],
        choices=["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"],
        help="指定平台，不传则用默认全平台",
    )
    parser.add_argument("--max-keywords", type=int, default=20, help="每平台关键词上限")
    parser.add_argument("--max-notes", type=int, default=20, help="每平台内容上限")
    parser.add_argument("--max-comments", type=int, default=20, help="每条内容评论上限")
    parser.add_argument("--test", action="store_true", help="测试模式")
    parser.add_argument("--dry-run", action="store_true", help="仅展示将执行的日期")
    parser.add_argument(
        "--skip-missing-topics",
        action="store_true",
        help="跳过没有 daily_topics 的日期（推荐）",
    )
    return parser.parse_args()


def parse_iso_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def build_engine():
    dialect = (settings.DB_DIALECT or "mysql").lower()
    if dialect in ("postgres", "postgresql"):
        url = (
            f"postgresql+psycopg://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )
    else:
        url = (
            f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
            f"?charset={settings.DB_CHARSET}"
        )
    return create_engine(url, future=True)


def has_topics(target_date: date) -> bool:
    engine = build_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(1) AS cnt FROM daily_topics WHERE extract_date = :d"),
            {"d": target_date},
        ).first()
    return bool(row and row[0] and int(row[0]) > 0)


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def run_for_date(args: argparse.Namespace, target_date: date) -> int:
    cmd = [sys.executable, "main.py", "--deep-sentiment", "--date", target_date.isoformat()]
    if args.platforms:
        cmd.extend(["--platforms"] + args.platforms)
    cmd.extend(
        [
            "--max-keywords",
            str(args.max_keywords),
            "--max-notes",
            str(args.max_notes),
            "--max-comments",
            str(args.max_comments),
        ]
    )
    if args.test:
        cmd.append("--test")

    print(f"[RUN] {' '.join(cmd)}")
    if args.dry_run:
        return 0

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode


def main() -> None:
    args = parse_args()
    start = parse_iso_date(args.start_date)
    end = parse_iso_date(args.end_date)
    if end < start:
        raise ValueError("end-date 不能早于 start-date")

    success = 0
    failed = 0
    skipped = 0
    for d in date_range(start, end):
        if args.skip_missing_topics and not has_topics(d):
            print(f"[SKIP] {d} 没有 daily_topics")
            skipped += 1
            continue
        code = run_for_date(args, d)
        if code == 0:
            success += 1
        else:
            failed += 1
            print(f"[FAIL] {d} 返回码={code}")

    print("\n=== 回放完成 ===")
    print(f"成功: {success}")
    print(f"失败: {failed}")
    print(f"跳过: {skipped}")


if __name__ == "__main__":
    main()

