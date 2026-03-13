#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xhs_note 兜底回写：
当常规 topic_id/date 链路扫不到时，按 source_keyword 对 xhs 语料分段做精确匹配回写。
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "Data" / "自建语料库 (1).csv"
XHS_SECTION = (8724, 9622)  # 1-based line range


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="xhs_note source_keyword 兜底回写")
    parser.add_argument("--input", type=str, default=str(DEFAULT_CSV), help="语料 CSV 路径")
    parser.add_argument("--id-start", type=int, default=0, help="可选：起始 id（含）")
    parser.add_argument("--id-end", type=int, default=0, help="可选：结束 id（含）")
    parser.add_argument("--only-empty", action="store_true", help="仅回写 lang_theme 为空记录（推荐）")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写入")
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


def normalize_text(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return ""
    return s


def normalize_token(v: object) -> str:
    s = normalize_text(v).replace("#", "").lower()
    return "".join(ch for ch in s if not ch.isspace())


def read_text_fallback(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"无法读取CSV: {path}")


def load_xhs_corpus_maps(path: Path) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    start_line, end_line = XHS_SECTION
    lines = read_text_fallback(path).splitlines()[start_line - 1 : end_line]
    lines = [ln for ln in lines if ln.strip()]
    rows = list(csv.reader(lines))
    if not rows:
        return {}, {}

    header = [str(h).strip() for h in rows[0]]
    idx = {k: i for i, k in enumerate(header)}

    def get(r: List[str], key: str) -> str:
        i = idx.get(key)
        if i is None or i >= len(r):
            return ""
        return normalize_text(r[i])

    by_topic: Dict[str, Dict] = {}
    by_keyword: Dict[str, Dict] = {}
    for r in rows[1:]:
        item = {
            "theme": get(r, "主题"),
            "sub_theme": get(r, "次主题"),
            "third_theme": get(r, "次次主题"),
            "remark1": get(r, "备注1"),
            "remark2": get(r, "备注2"),
            "remark3": get(r, "备注3"),
            "keyword": get(r, "关键词") or get(r, "检索词"),
            "topic": get(r, "词条") or get(r, "话题"),
            "topic_link": get(r, "链接") or get(r, "话题链接"),
        }
        tkey = normalize_token(item["topic"])
        kkey = normalize_token(item["keyword"])
        if tkey and tkey not in by_topic:
            by_topic[tkey] = item
        if kkey and kkey not in by_keyword:
            by_keyword[kkey] = item
    return by_topic, by_keyword


def fetch_xhs_notes(cur, id_start: int, id_end: int, only_empty: bool):
    where = ["source_keyword IS NOT NULL", "source_keyword <> ''"]
    params: List[object] = []
    if only_empty:
        where.append("(lang_theme IS NULL OR lang_theme = '')")
    if id_start > 0 and id_end > 0:
        where.append("id BETWEEN %s AND %s")
        params.extend([id_start, id_end])
    elif id_start > 0:
        where.append("id >= %s")
        params.append(id_start)
    elif id_end > 0:
        where.append("id <= %s")
        params.append(id_end)
    sql = f"""
        SELECT id, source_keyword
        FROM xhs_note
        WHERE {" AND ".join(where)}
        ORDER BY id
    """
    cur.execute(sql, params)
    return cur.fetchall()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path

    by_topic, by_keyword = load_xhs_corpus_maps(input_path)
    if not by_topic and not by_keyword:
        raise RuntimeError("xhs 语料分段为空，无法回写。")

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

    notes = fetch_xhs_notes(cur, args.id_start, args.id_end, args.only_empty)
    matched = 0
    updated = 0
    for nid, source_keyword in notes:
        key = normalize_token(source_keyword)
        match = by_topic.get(key) or by_keyword.get(key)
        if not match:
            continue
        matched += 1
        if args.dry_run:
            continue
        cur.execute(
            """
            UPDATE xhs_note
            SET
                lang_theme = %s,
                lang_sub_theme = %s,
                lang_third_theme = %s,
                remark1 = %s,
                remark2 = %s,
                remark3 = %s,
                corpus_keyword = %s,
                corpus_topic = %s,
                topic_link = %s
            WHERE id = %s
            """,
            (
                match["theme"],
                match["sub_theme"],
                match["third_theme"],
                match["remark1"],
                match["remark2"],
                match["remark3"],
                match["keyword"],
                match["topic"],
                match["topic_link"],
                nid,
            ),
        )
        updated += int(cur.rowcount or 0)

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
    cur.close()
    conn.close()

    print(f"scope_id={args.id_start or '-'}~{args.id_end or '-'}")
    print(f"notes_scanned={len(notes)}")
    print(f"matched={matched}")
    print(f"updated={updated if not args.dry_run else 0}")
    print(f"dry_run={args.dry_run}")


if __name__ == "__main__":
    main()

