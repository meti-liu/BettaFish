#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从语料库导入语情关键词到 daily_topics。

默认行为：
1) 读取 Data/自建语料库 (1).csv（自动回退到同名 xlsx/csv）
2) 提取关键词并去重
3) 覆盖指定日期（默认今天）的 daily_topics，仅保留 1 条语情关键词记录
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Sequence

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

KEYWORD_COLUMNS = ["检索词", "话题"]
FILTER_COLUMNS = ["主题", "次主题", "次次主题"]


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
        help="目标日期，格式 YYYY-MM-DD，默认今天",
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


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv_fallback(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"不支持的文件类型: {path.suffix}")


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text_value = str(value).strip()
    if not text_value or text_value.lower() == "nan":
        return ""
    return text_value


def normalize_list(values: Sequence[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        v = normalize_text(value)
        if v:
            out.append(v)
    return out


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


def extract_keywords(df: pd.DataFrame, max_keywords: int) -> List[str]:
    seen = set()
    keywords: List[str] = []

    columns = [c for c in KEYWORD_COLUMNS if c in df.columns]
    if not columns:
        raise ValueError(f"输入文件中未找到关键词列，期望包含: {KEYWORD_COLUMNS}")

    for col in columns:
        for raw in df[col].tolist():
            token = normalize_text(raw)
            if token and token not in seen:
                seen.add(token)
                keywords.append(token)
            if len(keywords) >= max_keywords:
                return keywords
    return keywords


def make_topic_id(topic_name: str, target_date: date) -> str:
    seed = f"{topic_name}-{target_date.isoformat()}"
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
    return f"lang_{target_date.strftime('%Y%m%d')}_{h}"


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


def upsert_daily_topics(
    *,
    target_date: date,
    topic_id: str,
    topic_name: str,
    topic_description: str,
    keywords: List[str],
    mode: str,
) -> None:
    now_ts = int(time.time())
    kw_json = json.dumps(keywords, ensure_ascii=False)

    engine = build_engine()
    with engine.begin() as conn:
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
        else:
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
            print(f"{idx:>3}. {kw}")


def main() -> None:
    args = parse_args()
    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    )
    input_path = resolve_input_path(args.input)

    raw_df = read_table(input_path)
    df = apply_filters(raw_df, args.theme, args.subtheme, args.third_theme)
    keywords = extract_keywords(df, args.max_keywords)

    if not keywords:
        raise RuntimeError("过滤后没有可导入的关键词，请放宽筛选条件或检查语料列名。")

    topic_id = args.topic_id or make_topic_id(args.topic_name, target_date)
    filter_hint = {
        "theme": normalize_list(args.theme),
        "subtheme": normalize_list(args.subtheme),
        "third_theme": normalize_list(args.third_theme),
    }
    topic_description = (
        f"由 import_language_keywords.py 导入。source={input_path.name}; "
        f"rows={len(df)}; filters={json.dumps(filter_hint, ensure_ascii=False)}"
    )

    print(f"输入文件: {input_path}")
    print(f"目标日期: {target_date}")
    print(f"写入模式: {args.mode}")
    print(f"topic_id: {topic_id}")
    print(f"topic_name: {args.topic_name}")
    show_preview(keywords, args.preview)

    if args.dry_run:
        print("dry-run 模式：未写入数据库。")
        return

    upsert_daily_topics(
        target_date=target_date,
        topic_id=topic_id,
        topic_name=args.topic_name,
        topic_description=topic_description,
        keywords=keywords,
        mode=args.mode,
    )
    print("写入完成。")


if __name__ == "__main__":
    main()

