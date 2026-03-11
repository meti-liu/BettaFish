#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为 dy/xhs 内容表增加 create_date_time 列（幂等）。
"""

from __future__ import annotations

from pathlib import Path

import pymysql


TARGETS = [
    ("douyin_aweme", "idx_douyin_aweme_create_date_time"),
    ("xhs_note", "idx_xhs_note_create_date_time"),
]


def parse_env(path: Path):
    env = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.split("#", 1)[0].strip().strip('"').strip("'")
    return env


def has_column(cur, db_name: str, table: str, col: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(1)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
        """,
        (db_name, table, col),
    )
    return int(cur.fetchone()[0] or 0) > 0


def has_index(cur, db_name: str, table: str, index_name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(1)
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s
        """,
        (db_name, table, index_name),
    )
    return int(cur.fetchone()[0] or 0) > 0


def main() -> None:
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
    cur.execute("SELECT DATABASE()")
    db_name = cur.fetchone()[0]

    for table, index_name in TARGETS:
        if has_column(cur, db_name, table, "create_date_time"):
            print(f"{table}: skip create_date_time")
        else:
            cur.execute(
                f"ALTER TABLE {table} "
                "ADD COLUMN create_date_time varchar(255) DEFAULT NULL COMMENT '帖子发布时间(北京时间)'"
            )
            print(f"{table}: add create_date_time")

        if has_index(cur, db_name, table, index_name):
            print(f"{table}: skip {index_name}")
        else:
            cur.execute(f"ALTER TABLE {table} ADD INDEX {index_name} (create_date_time)")
            print(f"{table}: add {index_name}")

    conn.commit()
    cur.close()
    conn.close()
    print("done")


if __name__ == "__main__":
    main()

