#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据 daily_topics 的关键词与日期，回填各内容表的 topic_id。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pymysql


TABLE_CONFIG = {
    # ts_expr 返回“北京时间日期”
    "weibo_note": "DATE(FROM_UNIXTIME(create_time + 28800))",
    "douyin_aweme": "DATE(FROM_UNIXTIME(create_time + 28800))",
    "xhs_note": "DATE(FROM_UNIXTIME(CASE WHEN time > 20000000000 THEN time/1000 ELSE time END + 28800))",
    "bilibili_video": "DATE(FROM_UNIXTIME(create_time + 28800))",
    "kuaishou_video": "DATE(FROM_UNIXTIME(create_time + 28800))",
    "tieba_note": "DATE(publish_time)",
    "zhihu_content": "DATE(created_time)",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回填 topic_id 到内容表")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--tables",
        nargs="+",
        default=["weibo_note"],
        choices=list(TABLE_CONFIG.keys()),
        help="要回填的表，默认 weibo_note",
    )
    parser.add_argument(
        "--date-window-days",
        type=int,
        default=0,
        help="按日期匹配时允许的天数偏移，0表示必须同一天",
    )
    parser.add_argument(
        "--ignore-date",
        action="store_true",
        help="仅按关键词回填topic_id，不限制日期（慎用）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计不更新")
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


def parse_keywords(raw: str | None) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        return []


def fetch_daily_topics(cur, start: str, end: str) -> List[Tuple[str, str, List[str]]]:
    cur.execute(
        """
        SELECT extract_date, topic_id, keywords
        FROM daily_topics
        WHERE extract_date BETWEEN %s AND %s
        ORDER BY extract_date
        """,
        (start, end),
    )
    rows = cur.fetchall()
    out = []
    for d, topic_id, keywords_json in rows:
        kws = parse_keywords(keywords_json)
        if topic_id and kws:
            out.append((str(d), topic_id, kws))
    return out


def update_one_table(
    cur,
    table: str,
    date_str: str,
    topic_id: str,
    keywords: List[str],
    dry_run: bool,
    date_window_days: int,
    ignore_date: bool,
) -> int:
    ts_expr = TABLE_CONFIG[table]
    placeholders = ",".join(["%s"] * len(keywords))
    where_parts = [
        "(topic_id IS NULL OR topic_id = '')",
        f"source_keyword IN ({placeholders})",
    ]
    params = list(keywords)
    if not ignore_date:
        if date_window_days > 0:
            where_parts.append(f"ABS(DATEDIFF({ts_expr}, %s)) <= %s")
            params.extend([date_str, date_window_days])
        else:
            where_parts.append(f"{ts_expr} = %s")
            params.append(date_str)
    where_clause = " AND ".join(where_parts)
    count_sql = f"SELECT COUNT(1) FROM {table} WHERE {where_clause}"
    cur.execute(count_sql, params)
    matched = int(cur.fetchone()[0] or 0)
    if dry_run or matched == 0:
        return matched

    update_sql = f"UPDATE {table} SET topic_id = %s WHERE {where_clause}"
    cur.execute(update_sql, [topic_id] + params)
    return int(cur.rowcount or 0)


def main() -> None:
    args = parse_args()
    _ = datetime.strptime(args.start_date, "%Y-%m-%d")
    _ = datetime.strptime(args.end_date, "%Y-%m-%d")

    env = parse_env(Path(".env"))
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

    topics = fetch_daily_topics(cur, args.start_date, args.end_date)
    if not topics:
        print("未找到可回填的 daily_topics 数据。")
        cur.close()
        conn.close()
        return

    total_updated = 0
    for date_str, topic_id, keywords in topics:
        for table in args.tables:
            affected = update_one_table(
                cur,
                table,
                date_str,
                topic_id,
                keywords,
                args.dry_run,
                args.date_window_days,
                args.ignore_date,
            )
            total_updated += affected
            action = "match" if args.dry_run else "updated"
            print(f"{table} {date_str} topic_id={topic_id} {action}={affected}")

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
    cur.close()
    conn.close()
    print(f"done, total={'matched' if args.dry_run else 'updated'}={total_updated}")


if __name__ == "__main__":
    main()

