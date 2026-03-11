#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从语料库导入语情关键词到 daily_topics。

支持两种写入策略：
1) fixed: 所有关键词写入指定日期（默认今天）
2) from-row-time: 按每行时间列自动分配到对应日期
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import pandas as pd
from sqlalchemy import create_engine, text

from config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "Data"
DEFAULT_CANDIDATES = [
    DEFAULT_DATA_DIR / "自建语料库 (1).csv",
    DEFAULT_DATA_DIR / "自建语料库 (1).xlsx",
    DEFAULT_DATA_DIR / "自建语料库.csv",
    DEFAULT_DATA_DIR / "自建语料库.xlsx",
]

# 业务要求：daily_topics 仅写“话题”，不混入“检索词”。
KEYWORD_COLUMNS = ["话题"]
FILTER_COLUMNS = ["主题", "次主题", "次次主题"]
DEFAULT_TIME_COLUMN = "时间"
DEFAULT_EXCLUDED_KEYWORDS = {"中文", "普通话", "姓名"}
PLATFORM_LINE_RANGES = {
    "dy": [(5192, 6368)],
    "xhs": [(8724, 9622)],
}
PLATFORM_CONTENT_TABLE = {
    "wb": "weibo_note",
    "dy": "douyin_aweme",
    "xhs": "xhs_note",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从语料库导入语情关键词到 daily_topics"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="",
        help="语料文件路径（csv/xlsx），默认自动探测 Data/自建语料库*",
    )
    parser.add_argument(
        "--date",
        type=str,
        default="",
        help="目标日期，格式 YYYY-MM-DD，默认今天（date-mode=fixed时生效）",
    )
    parser.add_argument(
        "--date-mode",
        choices=["fixed", "from-row-time"],
        default="fixed",
        help="fixed=统一写入同一天；from-row-time=按行时间写入各自日期",
    )
    parser.add_argument(
        "--time-column",
        type=str,
        default=DEFAULT_TIME_COLUMN,
        help="按行写入时使用的时间列名，默认“时间”",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="",
        help="按行写入时的起始日期（含），YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="",
        help="按行写入时的结束日期（含），YYYY-MM-DD",
    )
    parser.add_argument(
        "--topic-name",
        type=str,
        default="语情定向爬取",
        help="写入 daily_topics 的 topic_name",
    )
    parser.add_argument(
        "--topic-id",
        type=str,
        default="",
        help="写入 daily_topics 的 topic_id，默认根据日期生成",
    )
    parser.add_argument(
        "--theme",
        action="append",
        default=[],
        help="按主题过滤，可重复传入，如 --theme 语言系统 --theme 语言接触",
    )
    parser.add_argument(
        "--subtheme",
        action="append",
        default=[],
        help="按次主题过滤，可重复传入",
    )
    parser.add_argument(
        "--third-theme",
        action="append",
        default=[],
        help="按次次主题过滤，可重复传入",
    )
    parser.add_argument(
        "--platform",
        choices=["all", "wb", "dy", "xhs"],
        default="all",
        help="语料平台切片：all=全量；wb/dy/xhs=按平台子集",
    )
    parser.add_argument(
        "--dedup-source",
        choices=["none", "db"],
        default="none",
        help="关键词去重来源：none=不去重；db=基于数据库已有内容去重",
    )
    parser.add_argument(
        "--dedup-days",
        type=int,
        default=0,
        help="db去重时间窗口天数，0=全量历史",
    )
    parser.add_argument(
        "--mode",
        choices=["overwrite", "append"],
        default="overwrite",
        help="overwrite=覆盖当天记录；append=合并到指定topic_id记录",
    )
    parser.add_argument(
        "--max-keywords",
        type=int,
        default=500,
        help="最多写入关键词数量，默认500",
    )
    parser.add_argument(
        "--exclude-keyword",
        action="append",
        default=[],
        help="排除关键词，可重复传入；默认会排除：中文/普通话/姓名",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=20,
        help="预览打印关键词数量，默认20",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览，不写数据库",
    )
    return parser.parse_args()


def resolve_input_path(input_arg: str) -> Path:
    if input_arg:
        p = Path(input_arg)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        if p.exists():
            return p
        raise FileNotFoundError(f"输入文件不存在: {p}")

    for p in DEFAULT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "未找到语料文件，请显式传入 --input，例如 Data/自建语料库 (1).csv"
    )


def _read_csv_fallback(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
    last_err: Exception | None = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as err:
            last_err = err
    if last_err:
        raise last_err
    raise RuntimeError(f"读取CSV失败: {path}")


def _read_text_fallback(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"读取文本失败: {path}")


def _parse_section_csv(path: Path, start_line: int, end_line: int) -> pd.DataFrame:
    lines = _read_text_fallback(path).splitlines()
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
    df = df.rename(
        columns={
            "关键词": "检索词",
            "词条": "话题",
            "链接": "话题链接",
        }
    )
    return df


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv_fallback(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的文件类型: {path.suffix}")


def read_table_by_platform(path: Path, platform: str) -> pd.DataFrame:
    if path.suffix.lower() == ".csv" and platform in PLATFORM_LINE_RANGES:
        start_line, end_line = PLATFORM_LINE_RANGES[platform][0]
        return _parse_section_csv(path, start_line, end_line)
    return read_table(path)


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text_value = str(value).strip()
    if not text_value or text_value.lower() == "nan":
        return ""
    return text_value


def normalize_token_for_match(value: object) -> str:
    token = normalize_text(value).replace("#", "").lower()
    return "".join(ch for ch in token if not ch.isspace())


def normalize_list(values: Sequence[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        v = normalize_text(value)
        if v:
            out.append(v)
    return out


def build_excluded_keywords(extra: Sequence[str]) -> set[str]:
    return set(DEFAULT_EXCLUDED_KEYWORDS) | set(normalize_list(extra))


def is_excluded_keyword(token: str, excluded: set[str]) -> bool:
    return normalize_text(token) in excluded


def apply_filters(df: pd.DataFrame, themes: Sequence[str], subthemes: Sequence[str], third: Sequence[str]) -> pd.DataFrame:
    filtered = df.copy()

    theme_set = set(normalize_list(themes))
    subtheme_set = set(normalize_list(subthemes))
    third_set = set(normalize_list(third))

    if theme_set and "主题" in filtered.columns:
        filtered = filtered[filtered["主题"].astype(str).str.strip().isin(theme_set)]
    if subtheme_set and "次主题" in filtered.columns:
        filtered = filtered[filtered["次主题"].astype(str).str.strip().isin(subtheme_set)]
    if third_set and "次次主题" in filtered.columns:
        filtered = filtered[filtered["次次主题"].astype(str).str.strip().isin(third_set)]

    return filtered


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


def filter_by_platform(df: pd.DataFrame, platform: str) -> pd.DataFrame:
    if platform == "all":
        return df.copy()

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


def extract_keywords(df: pd.DataFrame, max_keywords: int, excluded_keywords: set[str]) -> List[str]:
    seen = set()
    keywords: List[str] = []

    columns = [c for c in KEYWORD_COLUMNS if c in df.columns]
    if not columns:
        raise ValueError(f"输入文件中未找到关键词列，期望包含: {KEYWORD_COLUMNS}")

    for col in columns:
        for raw in df[col].tolist():
            token = normalize_text(raw)
            if is_excluded_keyword(token, excluded_keywords):
                continue
            if token and token not in seen:
                seen.add(token)
                keywords.append(token)
            if len(keywords) >= max_keywords:
                return keywords
    return keywords


def extract_all_keywords(df: pd.DataFrame, excluded_keywords: set[str]) -> List[str]:
    return extract_keywords(df, max_keywords=10**9, excluded_keywords=excluded_keywords)


def parse_iso_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def to_date_safe(raw: object) -> date | None:
    text_value = normalize_text(raw)
    if not text_value:
        return None

    # 优先按常见混合格式精确解析，避免 12/12/2021 等歧义导致误判。
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
            return datetime.strptime(text_value, fmt).date()
        except ValueError:
            continue

    ts = pd.to_datetime(text_value, errors="coerce", dayfirst=False, yearfirst=False)
    if pd.isna(ts):
        return None
    return ts.date()


def limit_keywords(items: Sequence[str], max_keywords: int) -> List[str]:
    if max_keywords <= 0:
        return []
    return list(items[:max_keywords])


def extract_keywords_by_date(
    df: pd.DataFrame,
    *,
    time_column: str,
    max_keywords: int,
    start_date: date | None,
    end_date: date | None,
    excluded_keywords: set[str],
) -> Dict[date, List[str]]:
    if time_column not in df.columns:
        raise ValueError(f"未找到时间列: {time_column}")

    keyword_cols = [c for c in KEYWORD_COLUMNS if c in df.columns]
    if not keyword_cols:
        raise ValueError(f"输入文件中未找到关键词列，期望包含: {KEYWORD_COLUMNS}")

    date_to_keywords: Dict[date, List[str]] = {}
    date_to_seen: Dict[date, set] = {}

    for _, row in df.iterrows():
        row_date = to_date_safe(row.get(time_column))
        if row_date is None:
            continue
        if start_date and row_date < start_date:
            continue
        if end_date and row_date > end_date:
            continue

        if row_date not in date_to_keywords:
            date_to_keywords[row_date] = []
            date_to_seen[row_date] = set()

        current = date_to_keywords[row_date]
        seen = date_to_seen[row_date]
        if len(current) >= max_keywords:
            continue

        for col in keyword_cols:
            kw = normalize_text(row.get(col))
            if is_excluded_keyword(kw, excluded_keywords):
                continue
            if not kw or kw in seen:
                continue
            seen.add(kw)
            current.append(kw)
            if len(current) >= max_keywords:
                break

    return {d: kws for d, kws in date_to_keywords.items() if kws}


def make_topic_id(topic_name: str, target_date: date, platform: str = "all") -> str:
    seed = f"{platform}|{topic_name}|{target_date.isoformat()}"
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
    # wb 保持原有“按日”语义；dy/xhs 使用平台前缀，避免误导为“帖子发布时间=extract_date”
    if platform == "wb":
        return f"lang_{target_date.strftime('%Y%m%d')}_{h}"
    if platform in ("dy", "xhs"):
        return f"lang_{platform}_{h}"
    return f"lang_{h}"


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


def _fetch_existing_keyword_set_from_db(engine, platform: str, dedup_days: int) -> set[str]:
    table = PLATFORM_CONTENT_TABLE.get(platform)
    if not table:
        return set()

    day_expr_map = {
        "wb": "DATE(FROM_UNIXTIME(create_time + 28800))",
        "dy": "DATE(FROM_UNIXTIME(CASE WHEN create_time > 20000000000 THEN create_time/1000 ELSE create_time END + 28800))",
        "xhs": "DATE(FROM_UNIXTIME(CASE WHEN time > 20000000000 THEN time/1000 ELSE time END + 28800))",
    }
    day_expr = day_expr_map[platform]

    where = "source_keyword IS NOT NULL AND source_keyword <> ''"
    params = {}
    if dedup_days > 0:
        where += f" AND {day_expr} >= DATE_SUB(CURDATE(), INTERVAL :days DAY)"
        params["days"] = dedup_days

    sql = text(f"SELECT DISTINCT source_keyword FROM {table} WHERE {where}")
    existing: set[str] = set()
    with engine.connect() as conn:
        for row in conn.execute(sql, params):
            token = normalize_token_for_match(row[0])
            if token:
                existing.add(token)
    existing |= _fetch_existing_keyword_set_from_daily_topics(engine, platform, dedup_days)
    return existing


def _fetch_existing_keyword_set_from_daily_topics(engine, platform: str, dedup_days: int) -> set[str]:
    where_parts = []
    params = {}
    if platform in ("dy", "xhs"):
        where_parts.append("topic_id LIKE :topic_prefix")
        params["topic_prefix"] = f"lang_{platform}_%"
    if dedup_days > 0:
        where_parts.append("extract_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)")
        params["days"] = dedup_days
    where_clause = " AND ".join(where_parts)
    if where_clause:
        where_clause = "WHERE " + where_clause

    sql = text(f"SELECT keywords FROM daily_topics {where_clause}")
    existing: set[str] = set()
    with engine.connect() as conn:
        for row in conn.execute(sql, params):
            raw = row[0]
            if not raw:
                continue
            try:
                arr = json.loads(raw)
            except Exception:
                continue
            if not isinstance(arr, list):
                continue
            for item in arr:
                token = normalize_token_for_match(item)
                if token:
                    existing.add(token)
    return existing


def dedup_keywords_by_existing(candidates: Sequence[str], existing_tokens: set[str]) -> List[str]:
    out: List[str] = []
    for kw in candidates:
        token = normalize_token_for_match(kw)
        if not token:
            continue
        if token in existing_tokens:
            continue
        existing_tokens.add(token)
        out.append(kw)
    return out


def upsert_daily_topics(conn, *, target_date: date, topic_id: str, topic_name: str, topic_description: str, keywords: List[str], mode: str) -> None:
    now_ts = int(time.time())
    kw_json = json.dumps(keywords, ensure_ascii=False)

    if mode == "overwrite":
        conn.execute(
            text("DELETE FROM daily_topics WHERE extract_date = :d"),
            {"d": target_date},
        )
        conn.execute(
            text(
                """
                INSERT INTO daily_topics
                (topic_id, topic_name, topic_description, keywords, extract_date,
                 relevance_score, news_count, processing_status, add_ts, last_modify_ts)
                VALUES
                (:topic_id, :topic_name, :topic_description, :keywords, :extract_date,
                 :relevance_score, :news_count, :processing_status, :add_ts, :last_modify_ts)
                """
            ),
            {
                "topic_id": topic_id,
                "topic_name": topic_name,
                "topic_description": topic_description,
                "keywords": kw_json,
                "extract_date": target_date,
                "relevance_score": 1.0,
                "news_count": 0,
                "processing_status": "completed",
                "add_ts": now_ts,
                "last_modify_ts": now_ts,
            },
        )
        return

    # append: 合并到同一天同 topic_id 的记录，不存在就新建
    row = conn.execute(
        text(
            """
            SELECT keywords
            FROM daily_topics
            WHERE extract_date = :d AND topic_id = :topic_id
            LIMIT 1
            """
        ),
        {"d": target_date, "topic_id": topic_id},
    ).first()

    if row:
        existing = []
        try:
            existing = json.loads(row[0]) if row[0] else []
        except Exception:
            existing = []

        merged = []
        seen = set()
        for kw in list(existing) + keywords:
            k = normalize_text(kw)
            if k and k not in seen:
                seen.add(k)
                merged.append(k)

        conn.execute(
            text(
                """
                UPDATE daily_topics
                SET keywords = :keywords,
                    topic_name = :topic_name,
                    topic_description = :topic_description,
                    processing_status = :processing_status,
                    last_modify_ts = :last_modify_ts
                WHERE extract_date = :d AND topic_id = :topic_id
                """
            ),
            {
                "keywords": json.dumps(merged, ensure_ascii=False),
                "topic_name": topic_name,
                "topic_description": topic_description,
                "processing_status": "completed",
                "last_modify_ts": now_ts,
                "d": target_date,
                "topic_id": topic_id,
            },
        )
        return

    conn.execute(
        text(
            """
            INSERT INTO daily_topics
            (topic_id, topic_name, topic_description, keywords, extract_date,
             relevance_score, news_count, processing_status, add_ts, last_modify_ts)
            VALUES
            (:topic_id, :topic_name, :topic_description, :keywords, :extract_date,
             :relevance_score, :news_count, :processing_status, :add_ts, :last_modify_ts)
            """
        ),
        {
            "topic_id": topic_id,
            "topic_name": topic_name,
            "topic_description": topic_description,
            "keywords": kw_json,
            "extract_date": target_date,
            "relevance_score": 1.0,
            "news_count": 0,
            "processing_status": "completed",
            "add_ts": now_ts,
            "last_modify_ts": now_ts,
        },
    )


def show_preview(keywords: Sequence[str], preview: int) -> None:
    total = len(keywords)
    print(f"关键词总数: {total}")
    if total == 0:
        return
    n = max(0, preview)
    if n > 0:
        print(f"预览前 {min(total, n)} 个关键词:")
        for idx, kw in enumerate(keywords[:n], start=1):
            line = f"{idx:>3}. {kw}"
            try:
                print(line)
            except UnicodeEncodeError:
                # Windows GBK 控制台兼容兜底，避免预览阶段中断流程
                print(line.encode("gbk", errors="replace").decode("gbk"))


def main() -> None:
    args = parse_args()
    input_path = resolve_input_path(args.input)
    excluded_keywords = build_excluded_keywords(args.exclude_keyword)

    raw_df = read_table_by_platform(input_path, args.platform)
    if args.platform in PLATFORM_LINE_RANGES and input_path.suffix.lower() == ".csv":
        platform_df = raw_df
    else:
        platform_df = filter_by_platform(raw_df, args.platform)
    df = apply_filters(platform_df, args.theme, args.subtheme, args.third_theme)
    filter_hint = {
        "theme": normalize_list(args.theme),
        "subtheme": normalize_list(args.subtheme),
        "third_theme": normalize_list(args.third_theme),
    }

    print(f"输入文件: {input_path}")
    print(f"平台切片: {args.platform}")
    print(f"写入模式: {args.mode}")
    print(f"date-mode: {args.date_mode}")
    print(f"dedup-source: {args.dedup_source}")

    existing_tokens: set[str] = set()
    engine = None
    if args.dedup_source == "db":
        if args.platform not in ("wb", "dy", "xhs"):
            raise RuntimeError("db去重仅支持平台 wb/dy/xhs，请指定 --platform。")
        engine = build_engine()
        existing_tokens = _fetch_existing_keyword_set_from_db(engine, args.platform, args.dedup_days)
        print(f"db去重基线数量: {len(existing_tokens)}")

    if args.date_mode == "fixed":
        target_date = parse_iso_date(args.date) if args.date else date.today()
        keywords = extract_all_keywords(df, excluded_keywords)
        if args.dedup_source == "db":
            before = len(keywords)
            keywords = dedup_keywords_by_existing(keywords, existing_tokens)
            print(f"db去重过滤: {before} -> {len(keywords)}")
        keywords = limit_keywords(keywords, args.max_keywords)
        if not keywords:
            raise RuntimeError("过滤后没有可导入的关键词，请放宽筛选条件或检查语料列名。")
        topic_id = args.topic_id or make_topic_id(
            args.topic_name, target_date, args.platform
        )
        topic_description = (
            f"由 import_language_keywords.py 导入（fixed）。source={input_path.name}; "
            f"rows={len(df)}; filters={json.dumps(filter_hint, ensure_ascii=False)}"
        )

        print(f"目标日期: {target_date}")
        print(f"topic_id: {topic_id}")
        print(f"topic_name: {args.topic_name}")
        if args.platform in ("dy", "xhs"):
            print(
                "提示: extract_date 仅用于任务分桶/调度，不代表 dy/xhs 帖子实际发布时间。"
            )
        show_preview(keywords, args.preview)
        if args.dry_run:
            print("dry-run 模式：未写入数据库。")
            return

        if engine is None:
            engine = build_engine()
        with engine.begin() as conn:
            upsert_daily_topics(
                conn,
                target_date=target_date,
                topic_id=topic_id,
                topic_name=args.topic_name,
                topic_description=topic_description,
                keywords=keywords,
                mode=args.mode,
            )
        print("写入完成。")
        return

    start_date = parse_iso_date(args.start_date) if args.start_date else None
    end_date = parse_iso_date(args.end_date) if args.end_date else None
    date_keywords = extract_keywords_by_date(
        df,
        time_column=args.time_column,
        max_keywords=args.max_keywords,
        start_date=start_date,
        end_date=end_date,
        excluded_keywords=excluded_keywords,
    )
    if not date_keywords:
        raise RuntimeError("按行时间分桶后没有可写入关键词，请检查时间列或日期区间。")

    if args.dedup_source == "db":
        reduced: Dict[date, List[str]] = {}
        for d in sorted(date_keywords.keys()):
            kws = date_keywords[d]
            filtered = dedup_keywords_by_existing(kws, existing_tokens)
            reduced[d] = limit_keywords(filtered, args.max_keywords)
        date_keywords = {d: kws for d, kws in reduced.items() if kws}
        if not date_keywords:
            raise RuntimeError("db去重后无可写入关键词。")

    sorted_dates = sorted(date_keywords.keys())
    print(f"覆盖日期数: {len(sorted_dates)}")
    print(f"日期范围: {sorted_dates[0]} ~ {sorted_dates[-1]}")
    for d in sorted_dates[: min(5, len(sorted_dates))]:
        print(f"- {d}: {len(date_keywords[d])} 个关键词")
        show_preview(date_keywords[d], min(args.preview, 5))
    if len(sorted_dates) > 5:
        print(f"... 其余 {len(sorted_dates) - 5} 天省略")

    if args.dry_run:
        print("dry-run 模式：未写入数据库。")
        return

    if engine is None:
        engine = build_engine()
    with engine.begin() as conn:
        for d in sorted_dates:
            topic_id = args.topic_id or make_topic_id(args.topic_name, d, args.platform)
            topic_description = (
                f"由 import_language_keywords.py 导入（from-row-time）。source={input_path.name}; "
                f"rows={len(df)}; filters={json.dumps(filter_hint, ensure_ascii=False)}; "
                f"time_column={args.time_column}"
            )
            upsert_daily_topics(
                conn,
                target_date=d,
                topic_id=topic_id,
                topic_name=args.topic_name,
                topic_description=topic_description,
                keywords=date_keywords[d],
                mode=args.mode,
            )
    print(f"写入完成，共处理 {len(sorted_dates)} 天。")


if __name__ == "__main__":
    main()

