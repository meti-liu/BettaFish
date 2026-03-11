#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 Data/自建语料库 (1).csv 的人工标注字段回填到 weibo_note。

匹配策略（按优先级）：
1) 同一天 + source_keyword 精确命中（检索词/话题）
2) 同一天 + content 包含“话题”文本
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "Data" / "自建语料库 (1).csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回填 weibo_note 语料标注字段")
    parser.add_argument("--input", type=str, default=str(DEFAULT_CSV), help="语料CSV路径")
    parser.add_argument("--start-date", type=str, default="", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写入")
    parser.add_argument(
        "--only-empty",
        action="store_true",
        help="仅回填 lang_theme 为空的记录（推荐）",
    )
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


def read_csv(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"无法读取CSV: {path}")


def normalize_text(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return ""
    return s


def normalize_topic(v: str) -> str:
    s = normalize_text(v)
    return s.replace("#", "").strip()


def parse_day(v) -> Optional[date]:
    s = normalize_text(v)
    if not s:
        return None
    ts = pd.to_datetime(s, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def build_corpus_rows(df: pd.DataFrame) -> List[Dict]:
    out: List[Dict] = []
    for _, r in df.iterrows():
        day = parse_day(r.get("时间"))
        if not day:
            continue
        out.append(
            {
                "day": day,
                "theme": normalize_text(r.get("主题")),
                "sub_theme": normalize_text(r.get("次主题")),
                "third_theme": normalize_text(r.get("次次主题")),
                "remark1": normalize_text(r.get("备注1")),
                "remark2": normalize_text(r.get("备注2")),
                "remark3": normalize_text(r.get("备注3")),
                "role_media": normalize_text(r.get("媒体")),
                "role_expert": normalize_text(r.get("专家")),
                "role_public": normalize_text(r.get("普通人")),
                "role_government": normalize_text(r.get("政府")),
                "role_enterprise": normalize_text(r.get("企业")),
                "reproduce_flag": normalize_text(r.get("复现")),
                "keyword": normalize_text(r.get("检索词")),
                "topic": normalize_text(r.get("话题")),
                "heat": normalize_text(r.get("热度")),
                "corpus_time": normalize_text(r.get("时间")),
                "site_click_count": normalize_text(r.get("本站点击次数")),
                "daily_rank_minutes": normalize_text(r.get("当日上榜时间（分）")),
                "host_name": normalize_text(r.get("主持人")),
                "host_homepage": normalize_text(r.get("主持人主页")),
                "topic_category": normalize_text(r.get("分类")),
                "topic_mark": normalize_text(r.get("标识")),
                "topic_link": normalize_text(r.get("话题链接")),
            }
        )
    return out


def int_or_none(s: str) -> Optional[int]:
    s = normalize_text(s)
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def choose_best(note: Dict, candidates: List[Dict]) -> Optional[Dict]:
    src_kw = normalize_text(note.get("source_keyword"))
    content = normalize_text(note.get("content"))
    best = None
    best_score = -1
    for c in candidates:
        score = 0
        if src_kw and src_kw in {c["keyword"], c["topic"]}:
            score += 3
        norm_topic = normalize_topic(c["topic"])
        if norm_topic and norm_topic in content:
            score += 2
        if c["keyword"] and c["keyword"] in content:
            score += 1
        if score > best_score:
            best_score = score
            best = c
    return best if best_score > 0 else None


def fetch_weibo_notes(cur, start: str, end: str, only_empty: bool) -> List[Dict]:
    where_empty = "AND (lang_theme IS NULL OR lang_theme = '')" if only_empty else ""
    sql = f"""
        SELECT id, source_keyword, content, DATE(FROM_UNIXTIME(create_time + 28800)) AS day
        FROM weibo_note
        WHERE DATE(FROM_UNIXTIME(create_time + 28800)) BETWEEN %s AND %s
        {where_empty}
    """
    cur.execute(sql, (start, end))
    rows = cur.fetchall()
    return [{"id": r[0], "source_keyword": r[1], "content": r[2], "day": r[3]} for r in rows]


def update_note(cur, note_id: int, match: Dict) -> int:
    sql = """
        UPDATE weibo_note
        SET
            lang_theme = %s,
            lang_sub_theme = %s,
            lang_third_theme = %s,
            remark1 = %s,
            remark2 = %s,
            remark3 = %s,
            role_media = %s,
            role_expert = %s,
            role_public = %s,
            role_government = %s,
            role_enterprise = %s,
            reproduce_flag = %s,
            corpus_keyword = %s,
            corpus_topic = %s,
            corpus_heat = %s,
            corpus_time = %s,
            site_click_count = %s,
            daily_rank_minutes = %s,
            host_name = %s,
            host_homepage = %s,
            topic_category = %s,
            topic_mark = %s,
            topic_link = %s
        WHERE id = %s
    """
    cur.execute(
        sql,
        (
            match["theme"],
            match["sub_theme"],
            match["third_theme"],
            match["remark1"],
            match["remark2"],
            match["remark3"],
            match["role_media"],
            match["role_expert"],
            match["role_public"],
            match["role_government"],
            match["role_enterprise"],
            match["reproduce_flag"],
            match["keyword"],
            match["topic"],
            int_or_none(match["heat"]),
            match["corpus_time"],
            int_or_none(match["site_click_count"]),
            int_or_none(match["daily_rank_minutes"]),
            match["host_name"],
            match["host_homepage"],
            match["topic_category"],
            match["topic_mark"],
            match["topic_link"],
            note_id,
        ),
    )
    return int(cur.rowcount or 0)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path

    df = read_csv(input_path)
    corpus_rows = build_corpus_rows(df)
    if not corpus_rows:
        raise RuntimeError("语料为空或没有可解析的“时间”字段。")

    if args.start_date:
        start_date = pd.to_datetime(args.start_date).date()
    else:
        start_date = min(r["day"] for r in corpus_rows)
    if args.end_date:
        end_date = pd.to_datetime(args.end_date).date()
    else:
        end_date = max(r["day"] for r in corpus_rows)

    by_day: Dict[date, List[Dict]] = {}
    for row in corpus_rows:
        if row["day"] < start_date or row["day"] > end_date:
            continue
        by_day.setdefault(row["day"], []).append(row)

    env = parse_env(PROJECT_ROOT / ".env")
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

    notes = fetch_weibo_notes(cur, str(start_date), str(end_date), args.only_empty)
    matched = 0
    updated = 0
    for note in notes:
        day = note["day"]
        candidates = by_day.get(day, [])
        if not candidates:
            continue
        best = choose_best(note, candidates)
        if not best:
            continue
        matched += 1
        if not args.dry_run:
            updated += update_note(cur, note["id"], best)

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
    cur.close()
    conn.close()

    print(f"date_range={start_date}~{end_date}")
    print(f"notes_scanned={len(notes)}")
    print(f"matched={matched}")
    print(f"updated={updated if not args.dry_run else 0}")
    print(f"dry_run={args.dry_run}")


if __name__ == "__main__":
    main()

