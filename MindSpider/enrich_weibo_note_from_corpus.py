#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 Data/自建语料库 (1).csv 的人工标注字段回填到社媒内容表（wb/dy/xhs）。

匹配策略（按优先级）：
1) 同一天 + source_keyword 精确命中（检索词/话题）
2) 同一天 + content 包含“话题”文本
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "Data" / "自建语料库 (1).csv"
PLATFORM_LINE_RANGES = {
    "dy": [(5192, 6368)],
    "xhs": [(8724, 9622)],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回填社媒内容表语料标注字段（wb/dy/xhs）")
    parser.add_argument("--input", type=str, default=str(DEFAULT_CSV), help="语料CSV路径")
    parser.add_argument("--start-date", type=str, default="", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写入")
    parser.add_argument(
        "--only-empty",
        action="store_true",
        help="仅回填 lang_theme 为空的记录（推荐）",
    )
    parser.add_argument(
        "--scan-by",
        type=str,
        choices=["topic-date", "note-day"],
        default="topic-date",
        help="扫描方式：topic-date=按topic_id所属daily_topics日期；note-day=按帖子创建日期",
    )
    parser.add_argument(
        "--platform",
        type=str,
        choices=["wb", "dy", "xhs"],
        default="wb",
        help="目标平台：wb=微博，dy=抖音，xhs=小红书",
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


def _read_text_with_fallback(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"无法读取文本文件: {path}")


def _parse_section_csv(path: Path, start_line: int, end_line: int) -> pd.DataFrame:
    lines = _read_text_with_fallback(path).splitlines()
    chunk = lines[start_line - 1 : end_line]
    chunk = [line for line in chunk if line.strip()]
    if not chunk:
        return pd.DataFrame()

    reader = csv.reader(chunk)
    rows = list(reader)
    if not rows:
        return pd.DataFrame()

    header = [str(x).strip() for x in rows[0]]
    data_rows = rows[1:]
    clean_rows = []
    for row in data_rows:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        clean_rows.append(row[: len(header)])

    df = pd.DataFrame(clean_rows, columns=header)
    rename_map = {
        "关键词": "检索词",
        "词条": "话题",
        "链接": "话题链接",
    }
    df = df.rename(columns=rename_map)
    return df


def read_platform_corpus(path: Path, platform: str) -> pd.DataFrame:
    if platform in ("dy", "xhs") and path.suffix.lower() == ".csv":
        start_line, end_line = PLATFORM_LINE_RANGES[platform][0]
        return _parse_section_csv(path, start_line, end_line)
    return read_csv(path)


def _slice_by_line_ranges(df: pd.DataFrame, ranges: List[tuple[int, int]]) -> pd.DataFrame:
    idx_parts = []
    total = len(df)
    for start_line, end_line in ranges:
        start_idx = max(0, start_line - 2)
        end_idx = min(total - 1, end_line - 2)
        if start_idx <= end_idx:
            idx_parts.append(df.iloc[start_idx : end_idx + 1])
    if not idx_parts:
        return df.iloc[0:0].copy()
    return pd.concat(idx_parts, ignore_index=True)


def filter_df_by_platform(df: pd.DataFrame, platform: str) -> pd.DataFrame:
    if "平台" in df.columns:
        val_map = {
            "wb": ["微博", "weibo", "wb"],
            "dy": ["抖音", "douyin", "dy"],
            "xhs": ["小红书", "xiaohongshu", "xhs"],
        }
        markers = [m.lower() for m in val_map[platform]]
        col = df["平台"].astype(str).str.strip().str.lower()
        return df[col.apply(lambda x: any(m in x for m in markers))].copy()

    if platform in PLATFORM_LINE_RANGES:
        return _slice_by_line_ranges(df, PLATFORM_LINE_RANGES[platform])

    if platform == "wb":
        # 没有“平台”列时，按已知区段排除 dy/xhs，剩余视为 wb 区段。
        mask = pd.Series(True, index=df.index)
        total = len(df)
        for ranges in PLATFORM_LINE_RANGES.values():
            for start_line, end_line in ranges:
                start_idx = max(0, start_line - 2)
                end_idx = min(total - 1, end_line - 2)
                if start_idx <= end_idx:
                    mask.iloc[start_idx : end_idx + 1] = False
        return df[mask].copy()

    return df.copy()


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


def canonical_text(v: str) -> str:
    s = normalize_topic(v)
    return "".join(ch.lower() for ch in s if not ch.isspace())


def parse_day(v) -> Optional[date]:
    s = normalize_text(v)
    if not s:
        return None
    known_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    ]
    for fmt in known_formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    ts = pd.to_datetime(s, errors="coerce", dayfirst=False, yearfirst=False)
    if pd.isna(ts):
        return None
    return ts.date()


def build_corpus_rows(df: pd.DataFrame) -> List[Dict]:
    out: List[Dict] = []
    for _, r in df.iterrows():
        day = parse_day(r.get("时间"))
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


def datetime_or_none(s: str) -> Optional[str]:
    s = normalize_text(s)
    if not s:
        return None
    ts = pd.to_datetime(s, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def choose_best(note: Dict, candidates: List[Dict]) -> Optional[Dict]:
    src_kw = normalize_text(note.get("source_keyword"))
    content = normalize_text(note.get("content"))
    note_day = note.get("day")
    src_kw_norm = canonical_text(src_kw)
    content_norm = canonical_text(content)
    best = None
    best_score = -1
    for c in candidates:
        score = 0
        c_kw = normalize_text(c["keyword"])
        c_topic = normalize_text(c["topic"])
        c_kw_norm = canonical_text(c_kw)
        c_topic_norm = canonical_text(c_topic)

        if src_kw and src_kw in {c_kw, c_topic}:
            score += 3
        if src_kw_norm and src_kw_norm in {c_kw_norm, c_topic_norm}:
            score += 2
        if c_topic_norm and c_topic_norm in content_norm:
            score += 2
        if c_kw_norm and c_kw_norm in content_norm:
            score += 1
        if note_day and c.get("day") == note_day:
            score += 2
        if score > best_score:
            best_score = score
            best = c
    return best if best_score > 0 else None


PLATFORM_CONFIG = {
    "wb": {
        "table": "weibo_note",
        "id_col": "id",
        "source_keyword_col": "source_keyword",
        "content_expr": "content",
        "day_expr": "DATE(FROM_UNIXTIME(create_time + 28800))",
    },
    "dy": {
        "table": "douyin_aweme",
        "id_col": "id",
        "source_keyword_col": "source_keyword",
        "content_expr": "CONCAT(COALESCE(`title`, ''), ' ', COALESCE(`desc`, ''))",
        "day_expr": "DATE(FROM_UNIXTIME(CASE WHEN `create_time` > 20000000000 THEN `create_time`/1000 ELSE `create_time` END + 28800))",
    },
    "xhs": {
        "table": "xhs_note",
        "id_col": "id",
        "source_keyword_col": "source_keyword",
        "content_expr": "CONCAT(COALESCE(`title`, ''), ' ', COALESCE(`desc`, ''))",
        "day_expr": "DATE(FROM_UNIXTIME(CASE WHEN `time` > 20000000000 THEN `time`/1000 ELSE `time` END + 28800))",
    },
}


def fetch_notes(cur, start: str, end: str, only_empty: bool, scan_by: str, platform: str) -> List[Dict]:
    cfg = PLATFORM_CONFIG[platform]
    table = cfg["table"]
    id_col = cfg["id_col"]
    source_keyword_col = cfg["source_keyword_col"]
    content_expr = cfg["content_expr"]
    day_expr = cfg["day_expr"]
    where_empty = "AND (lang_theme IS NULL OR lang_theme = '')" if only_empty else ""
    if scan_by == "topic-date":
        sql = f"""
            SELECT {id_col}, {source_keyword_col}, {content_expr} AS content, topic_id, {day_expr} AS day
            FROM {table}
            WHERE topic_id IN (
                SELECT topic_id FROM daily_topics
                WHERE extract_date BETWEEN %s AND %s
            )
            {where_empty}
        """
    else:
        sql = f"""
            SELECT {id_col}, {source_keyword_col}, {content_expr} AS content, topic_id, {day_expr} AS day
            FROM {table}
            WHERE {day_expr} BETWEEN %s AND %s
            {where_empty}
        """
    cur.execute(sql, (start, end))
    rows = cur.fetchall()
    return [
        {"id": r[0], "source_keyword": r[1], "content": r[2], "topic_id": r[3], "day": r[4]}
        for r in rows
    ]


def build_kw_topic_index(rows: List[Dict]) -> Dict[str, List[Dict]]:
    idx: Dict[str, List[Dict]] = {}
    for r in rows:
        for key in (r["keyword"], r["topic"]):
            norm = canonical_text(key)
            if not norm:
                continue
            idx.setdefault(norm, []).append(r)
    return idx


def update_note(cur, note_id: int, match: Dict, platform: str) -> int:
    table = PLATFORM_CONFIG[platform]["table"]
    sql = """
        UPDATE {table_name}
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
    """.format(table_name=table)
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
            datetime_or_none(match["corpus_time"]),
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

    raw_df = read_platform_corpus(input_path, args.platform)
    if args.platform in ("dy", "xhs") and input_path.suffix.lower() == ".csv":
        df = raw_df
    else:
        df = filter_df_by_platform(raw_df, args.platform)
    corpus_rows = build_corpus_rows(df)
    if not corpus_rows:
        raise RuntimeError("语料为空或没有可解析的“时间”字段。")

    dated_days = [r["day"] for r in corpus_rows if r.get("day")]
    if args.start_date:
        start_date = pd.to_datetime(args.start_date).date()
    elif dated_days:
        start_date = min(dated_days)
    else:
        raise RuntimeError("当前平台语料未包含“时间”，请显式传入 --start-date。")

    if args.end_date:
        end_date = pd.to_datetime(args.end_date).date()
    elif dated_days:
        end_date = max(dated_days)
    else:
        raise RuntimeError("当前平台语料未包含“时间”，请显式传入 --end-date。")

    by_day: Dict[date, List[Dict]] = {}
    undated_rows: List[Dict] = []
    for row in corpus_rows:
        row_day = row.get("day")
        if row_day is None:
            undated_rows.append(row)
            continue
        if row_day < start_date or row_day > end_date:
            continue
        by_day.setdefault(row_day, []).append(row)
    kw_topic_idx = build_kw_topic_index([r for rs in by_day.values() for r in rs] + undated_rows)

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

    notes = fetch_notes(cur, str(start_date), str(end_date), args.only_empty, args.scan_by, args.platform)
    matched = 0
    updated = 0
    for note in notes:
        day = note["day"]
        candidates = list(by_day.get(day, []))
        # 回退：如果同日候选少或匹配不到，则按关键词/话题全局候选补充。
        src_kw_norm = canonical_text(note.get("source_keyword", ""))
        if src_kw_norm and src_kw_norm in kw_topic_idx:
            candidates.extend(kw_topic_idx[src_kw_norm])
        if not candidates:
            continue
        best = choose_best(note, candidates)
        if not best:
            continue
        matched += 1
        if not args.dry_run:
            updated += update_note(cur, note["id"], best, args.platform)

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
    cur.close()
    conn.close()

    print(f"date_range={start_date}~{end_date}")
    print(f"platform={args.platform}")
    print(f"notes_scanned={len(notes)}")
    print(f"matched={matched}")
    print(f"updated={updated if not args.dry_run else 0}")
    print(f"dry_run={args.dry_run}")


if __name__ == "__main__":
    main()

