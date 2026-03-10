#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查指定日期区间的关键词导入与爬取结果。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import pymysql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查回放爬取结果")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    return parser.parse_args()


def load_env(path: Path) -> dict:
    env = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        clean = v.split("#", 1)[0].strip().strip('"').strip("'")
        env[k.strip()] = clean
    return env


def main() -> None:
    args = parse_args()
    env = load_env(Path(".env"))
    conn = pymysql.connect(
        host=env.get("DB_HOST", "127.0.0.1"),
        port=int(env.get("DB_PORT", "3306")),
        user=env.get("DB_USER"),
        password=env.get("DB_PASSWORD"),
        database=env.get("DB_NAME"),
        charset=env.get("DB_CHARSET", "utf8mb4"),
    )
    cur = conn.cursor()

    cur.execute(
        """
        SELECT extract_date, topic_id, topic_name
        FROM daily_topics
        WHERE extract_date BETWEEN %s AND %s
        ORDER BY extract_date
        """,
        (args.start_date, args.end_date),
    )
    topics = cur.fetchall()
    print("TOPICS=", topics)

    cur.execute(
        """
        SELECT scheduled_date, task_id, topic_id, platform, task_status, total_crawled, success_count, error_count
        FROM crawling_tasks
        WHERE scheduled_date BETWEEN %s AND %s
        ORDER BY id DESC
        LIMIT 50
        """,
        (args.start_date, args.end_date),
    )
    tasks = cur.fetchall()
    print("TASKS=", tasks)

    cur.execute(
        """
        SELECT topic_id, COUNT(1)
        FROM weibo_note
        WHERE topic_id IN (
            SELECT topic_id
            FROM daily_topics
            WHERE extract_date BETWEEN %s AND %s
        )
        GROUP BY topic_id
        """,
        (args.start_date, args.end_date),
    )
    print("WB_NOTES=", cur.fetchall())

    cur.execute(
        """
        SELECT n.topic_id, COUNT(1)
        FROM weibo_note_comment c
        JOIN weibo_note n ON c.note_id = n.note_id
        WHERE n.topic_id IN (
            SELECT topic_id
            FROM daily_topics
            WHERE extract_date BETWEEN %s AND %s
        )
        GROUP BY n.topic_id
        """,
        (args.start_date, args.end_date),
    )
    print("WB_COMMENTS=", cur.fetchall())

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

