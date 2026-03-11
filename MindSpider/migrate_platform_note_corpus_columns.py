#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为 wb/dy/xhs 内容表增加语料标注字段（幂等）。
"""

from __future__ import annotations

from pathlib import Path

import pymysql


TARGET_TABLES = ["weibo_note", "douyin_aweme", "xhs_note"]

COLUMNS = [
    ("lang_theme", "varchar(128) DEFAULT NULL COMMENT '主题'"),
    ("lang_sub_theme", "varchar(128) DEFAULT NULL COMMENT '次主题'"),
    ("lang_third_theme", "varchar(128) DEFAULT NULL COMMENT '次次主题'"),
    ("remark1", "varchar(255) DEFAULT NULL COMMENT '备注1'"),
    ("remark2", "varchar(255) DEFAULT NULL COMMENT '备注2'"),
    ("remark3", "varchar(255) DEFAULT NULL COMMENT '备注3'"),
    ("role_media", "varchar(64) DEFAULT NULL COMMENT '媒体'"),
    ("role_expert", "varchar(64) DEFAULT NULL COMMENT '专家'"),
    ("role_public", "varchar(64) DEFAULT NULL COMMENT '普通人'"),
    ("role_government", "varchar(64) DEFAULT NULL COMMENT '政府'"),
    ("role_enterprise", "varchar(64) DEFAULT NULL COMMENT '企业'"),
    ("reproduce_flag", "varchar(64) DEFAULT NULL COMMENT '复现'"),
    ("corpus_keyword", "varchar(255) DEFAULT NULL COMMENT '检索词'"),
    ("corpus_topic", "varchar(500) DEFAULT NULL COMMENT '话题'"),
    ("corpus_heat", "bigint DEFAULT NULL COMMENT '热度'"),
    ("corpus_time", "datetime DEFAULT NULL COMMENT '语料时间'"),
    ("site_click_count", "int DEFAULT NULL COMMENT '本站点击次数'"),
    ("daily_rank_minutes", "int DEFAULT NULL COMMENT '当日上榜时间（分）'"),
    ("host_name", "varchar(255) DEFAULT NULL COMMENT '主持人'"),
    ("host_homepage", "text COMMENT '主持人主页'"),
    ("topic_category", "varchar(128) DEFAULT NULL COMMENT '分类'"),
    ("topic_mark", "varchar(64) DEFAULT NULL COMMENT '标识'"),
    ("topic_link", "text COMMENT '话题链接'"),
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


def ensure_table_columns(cur, db_name: str, table: str) -> int:
    added = 0
    for col, ddl in COLUMNS:
        cur.execute(
            """
            SELECT COUNT(1)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
            """,
            (db_name, table, col),
        )
        exists = int(cur.fetchone()[0] or 0) > 0
        if exists:
            print(f"{table}: skip {col}")
            continue
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        added += 1
        print(f"{table}: add {col}")
    return added


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

    total_added = 0
    for table in TARGET_TABLES:
        total_added += ensure_table_columns(cur, db_name, table)

    conn.commit()
    cur.close()
    conn.close()
    print(f"done, added={total_added}")


if __name__ == "__main__":
    main()

