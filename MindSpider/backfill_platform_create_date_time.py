#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 dy/xhs 帖子 Unix 时间戳回填为 create_date_time（北京时间字符串）。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

import pymysql


TABLE_TIME_COL = {
    "douyin_aweme": "create_time",
    "xhs_note": "time",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回填 dy/xhs 的 create_date_time")
    parser.add_argument(
        "--tables",
        nargs="+",
        default=["douyin_aweme", "xhs_note"],
        choices=list(TABLE_TIME_COL.keys()),
        help="回填的表，默认 douyin_aweme xhs_note",
    )
    parser.add_argument("--only-empty", action="store_true", help="仅回填 create_date_time 为空的记录")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不更新")
    return parser.parse_args()


def parse_env(path: Path) -> Dict[str, str]:
    env = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.split("#", 1)[0].strip().strip('"').strip("'")
    return env


def build_update_sql(table: str, only_empty: bool) -> tuple[str, str]:
    time_col = TABLE_TIME_COL[table]
    where_parts = [
        f"{time_col} IS NOT NULL",
        f"{time_col} <> 0",
    ]
    if only_empty:
        where_parts.append("(create_date_time IS NULL OR create_date_time = '')")
    where_clause = " AND ".join(where_parts)
    datetime_expr = (
        f"DATE_FORMAT(FROM_UNIXTIME("
        f"CASE WHEN {time_col} > 20000000000 THEN {time_col}/1000 ELSE {time_col} END + 28800"
        f"), '%Y-%m-%d %H:%i:%s')"
    )
    count_sql = f"SELECT COUNT(1) FROM {table} WHERE {where_clause}"
    update_sql = f"UPDATE {table} SET create_date_time = {datetime_expr} WHERE {where_clause}"
    return count_sql, update_sql


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    env = parse_env(root / ".env")
    conn = pymysql.connect(
        host=env.get("DB_HOST", "127.0.0.1"),
        port=int(env.get("DB_PORT", "3306")),
        user=env.get("DB_USER"),
        password=env.get("DB_PASSWORD"),
        database=env.get("DB_NAME"),
        charset=env.get("DB_CHARSET", "utf8mb4"),
        autocommit=False,
    )
    cur = conn.cursor()

    total = 0
    for table in args.tables:
        count_sql, update_sql = build_update_sql(table, args.only_empty)
        cur.execute(count_sql)
        matched = int(cur.fetchone()[0] or 0)
        if args.dry_run:
            print(f"{table}: matched={matched}")
            total += matched
            continue
        if matched == 0:
            print(f"{table}: updated=0")
            continue
        cur.execute(update_sql)
        updated = int(cur.rowcount or 0)
        total += updated
        print(f"{table}: updated={updated}")

    if args.dry_run:
        conn.rollback()
        print(f"done, total_matched={total}")
    else:
        conn.commit()
        print(f"done, total_updated={total}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

