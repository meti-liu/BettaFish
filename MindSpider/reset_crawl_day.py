#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理指定日期的爬虫数据（默认微博）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymysql


def parse_env(path: Path):
    env = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.split("#", 1)[0].strip().strip('"').strip("'")
    return env


def parse_args():
    p = argparse.ArgumentParser(description="按日期清理爬虫数据")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--platform", default="wb", choices=["wb"], help="当前支持 wb")
    p.add_argument("--remove-topics", action="store_true", help="同时删除 daily_topics 当天配置")
    p.add_argument("--apply", action="store_true", help="确认执行删除（默认仅预览）")
    return p.parse_args()


def main():
    args = parse_args()
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
    d = args.date

    cur.execute(
        "SELECT COUNT(1) FROM weibo_note WHERE DATE(FROM_UNIXTIME(create_time + 28800))=%s",
        (d,),
    )
    note_count = int(cur.fetchone()[0] or 0)
    cur.execute(
        """
        SELECT COUNT(1)
        FROM weibo_note_comment c
        JOIN weibo_note n ON c.note_id = n.note_id
        WHERE DATE(FROM_UNIXTIME(n.create_time + 28800))=%s
        """,
        (d,),
    )
    comment_count = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(1) FROM daily_topics WHERE extract_date=%s", (d,))
    topic_count = int(cur.fetchone()[0] or 0)

    print(f"preview date={d}")
    print(f"weibo_note={note_count}")
    print(f"weibo_note_comment={comment_count}")
    print(f"daily_topics={topic_count}")

    if not args.apply:
        conn.rollback()
        cur.close()
        conn.close()
        print("dry-run only, no deletion.")
        return

    cur.execute(
        """
        DELETE c FROM weibo_note_comment c
        JOIN weibo_note n ON c.note_id = n.note_id
        WHERE DATE(FROM_UNIXTIME(n.create_time + 28800))=%s
        """,
        (d,),
    )
    deleted_comments = int(cur.rowcount or 0)
    cur.execute(
        "DELETE FROM weibo_note WHERE DATE(FROM_UNIXTIME(create_time + 28800))=%s",
        (d,),
    )
    deleted_notes = int(cur.rowcount or 0)

    deleted_topics = 0
    if args.remove_topics:
        cur.execute("DELETE FROM daily_topics WHERE extract_date=%s", (d,))
        deleted_topics = int(cur.rowcount or 0)

    conn.commit()
    cur.close()
    conn.close()

    print("deleted:")
    print(f"weibo_note_comment={deleted_comments}")
    print(f"weibo_note={deleted_notes}")
    print(f"daily_topics={deleted_topics}")


if __name__ == "__main__":
    main()

