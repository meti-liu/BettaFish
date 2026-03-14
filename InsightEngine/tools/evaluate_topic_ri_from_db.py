"""
按 topic 聚合评论 RI 的评估脚本。

流程：
1) 从数据库按平台读取 comment + note 关联数据；
2) 对每条评论计算 RI；
3) 以点赞权重对话题内评论 RI 做加权汇总；
4) 输出话题级风险排行和高风险评论样本。
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Tuple

import pymysql

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import settings
from InsightEngine.tools.risk_index_analyzer import RiskIndexAnalyzer

ATTACK_HINT_TERMS = {
    "去死",
    "全家死",
    "该死",
    "畜生",
    "垃圾",
    "人肉",
    "诽谤",
    "网暴",
    "恶心",
    "滚",
    "毒",
    "丧尽天良",
    "纳粹",
    "歧视",
    "仇恨",
    "侮辱",
}


PLATFORM_SQL = {
    "weibo": {
        "label": "微博",
        "sql": """
            SELECT
                COALESCE(n.corpus_topic, n.source_keyword, '未分类') AS topic_name,
                c.comment_id,
                COALESCE(c.content, '') AS content,
                CAST(COALESCE(c.comment_like_count, '0') AS UNSIGNED) AS like_count,
                (c.create_time + 28800) AS ts
            FROM weibo_note_comment c
            JOIN weibo_note n ON c.note_id = n.note_id
            WHERE DATE(FROM_UNIXTIME(c.create_time + 28800)) BETWEEN %s AND %s
              AND COALESCE(c.content, '') <> ''
            ORDER BY c.create_time DESC
            LIMIT %s
        """,
    },
    "xhs": {
        "label": "小红书",
        "sql": """
            SELECT
                COALESCE(n.corpus_topic, n.source_keyword, n.title, '未分类') AS topic_name,
                c.comment_id,
                COALESCE(c.content, '') AS content,
                CAST(COALESCE(c.like_count, '0') AS UNSIGNED) AS like_count,
                (CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800) AS ts
            FROM xhs_note_comment c
            JOIN xhs_note n ON c.note_id = n.note_id
            WHERE DATE(FROM_UNIXTIME(CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800)) BETWEEN %s AND %s
              AND COALESCE(c.content, '') <> ''
            ORDER BY c.create_time DESC
            LIMIT %s
        """,
    },
    "dy": {
        "label": "抖音",
        "sql": """
            SELECT
                COALESCE(n.corpus_topic, n.source_keyword, n.title, '未分类') AS topic_name,
                c.comment_id,
                COALESCE(c.content, '') AS content,
                CAST(COALESCE(c.like_count, '0') AS UNSIGNED) AS like_count,
                (CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800) AS ts
            FROM douyin_aweme_comment c
            JOIN douyin_aweme n ON c.aweme_id = n.aweme_id
            WHERE DATE(FROM_UNIXTIME(CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800)) BETWEEN %s AND %s
              AND COALESCE(c.content, '') <> ''
            ORDER BY c.create_time DESC
            LIMIT %s
        """,
    },
}


def db_conn():
    return pymysql.connect(
        host=settings.DB_HOST,
        port=int(settings.DB_PORT),
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset=settings.DB_CHARSET or "utf8mb4",
        autocommit=True,
    )


def _safe_text(text: str, max_len: int = 90) -> str:
    t = (text or "").replace("\n", " ").replace("\r", " ").strip()
    return t if len(t) <= max_len else (t[: max_len - 3] + "...")


def _build_h_norms(likes: List[int]) -> List[float]:
    vals = [max(1, int(x)) for x in likes]
    logs = [math.log(v) for v in vals]
    mn, mx = min(logs), max(logs)
    if mx == mn:
        return [0.5 for _ in logs]
    return [(v - mn) / (mx - mn) for v in logs]


def _build_v_velocity(times: List[float]) -> List[float]:
    if not times:
        return []
    mn, mx = min(times), max(times)
    if mx == mn:
        return [0.3 for _ in times]
    return [(t - mn) / (mx - mn) for t in times]


def fetch_rows(platform: str, start_date: str, end_date: str, max_rows: int) -> List[Tuple]:
    cfg = PLATFORM_SQL[platform]
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(cfg["sql"], [start_date, end_date, max_rows])
            return list(cur.fetchall())


def evaluate_topic(
    platform: str,
    topic_name: str,
    rows: List[Tuple],
    analyzer: RiskIndexAnalyzer,
) -> Dict:
    texts = [str(r[2]) for r in rows]
    likes = [int(r[3] or 0) for r in rows]
    times = [float(r[4] or 0) for r in rows]
    h_norms = _build_h_norms(likes)
    v_vels = _build_v_velocity(times)

    batch = analyzer.analyze_batch_texts(
        texts=texts,
        h_norm_list=h_norms,
        v_velocity_list=v_vels,
        initialize_if_needed=True,
    )

    items: List[Dict] = []
    for idx, rr in enumerate(batch.results):
        row = rows[idx]
        rr_d = asdict(rr)
        rr_d.update(
            {
                "platform": platform,
                "topic_name": topic_name,
                "comment_id": str(row[1]),
                "like_count": likes[idx],
                "raw_text": texts[idx],
                "text_preview": _safe_text(texts[idx]),
            }
        )
        items.append(rr_d)

    valid = [x for x in items if x.get("analysis_performed")]
    if not valid:
        return {
            "platform": platform,
            "topic_name": topic_name,
            "comment_count": len(rows),
            "weighted_ri": 0.0,
            "avg_ri": 0.0,
            "danger_ratio": 0.0,
            "attack_ratio": 0.0,
            "top_comments": [],
        }

    # 点赞加权：w = 1 + log(1+likes)
    weights = [1.0 + math.log1p(int(x["like_count"])) for x in valid]
    weighted_ri = sum(float(x["risk_index"]) * w for x, w in zip(valid, weights)) / max(1e-9, sum(weights))
    avg_ri = sum(float(x["risk_index"]) for x in valid) / len(valid)
    danger_ratio = sum(1 for x in valid if float(x["risk_index"]) >= 80.0) / len(valid)
    attack_ratio = (
        sum(
            1
            for x in valid
            if any(term in str(x.get("raw_text", "")).lower() for term in ATTACK_HINT_TERMS)
        )
        / len(valid)
    )
    topic_ri = 0.55 * weighted_ri + 0.25 * (danger_ratio * 100.0) + 0.20 * (attack_ratio * 100.0)

    valid.sort(key=lambda x: (float(x["risk_index"]), int(x["like_count"])), reverse=True)
    return {
        "platform": platform,
        "topic_name": topic_name,
        "comment_count": len(valid),
        "topic_ri": round(topic_ri, 2),
        "weighted_ri": round(weighted_ri, 2),
        "avg_ri": round(avg_ri, 2),
        "danger_ratio": round(danger_ratio, 4),
        "attack_ratio": round(attack_ratio, 4),
        "top_comments": valid[:5],
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate topic-level RI from DB comments")
    parser.add_argument("--platforms", nargs="+", default=["weibo", "xhs", "dy"], choices=["weibo", "xhs", "dy"])
    parser.add_argument("--start-date", type=str, default="2024-07-01")
    parser.add_argument("--end-date", type=str, default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--topic-like", type=str, default="", help="可选，按关键词过滤 topic")
    parser.add_argument("--max-rows-per-platform", type=int, default=6000)
    parser.add_argument("--max-comments-per-topic", type=int, default=80)
    parser.add_argument("--min-comments-per-topic", type=int, default=10)
    parser.add_argument("--max-topics", type=int, default=30, help="按评论量截断后最多分析的话题数/平台")
    parser.add_argument("--top-n", type=int, default=15, help="最终展示前 N 个 topic")
    parser.add_argument("--alpha", type=float, default=0.1)
    parser.add_argument("--beta", type=float, default=0.8)
    parser.add_argument("--gamma", type=float, default=0.1)
    args = parser.parse_args()

    analyzer = RiskIndexAnalyzer(alpha=args.alpha, beta=args.beta, gamma=args.gamma)
    topic_like = args.topic_like.strip().lower()

    print(f"RI 权重: alpha={args.alpha}, beta={args.beta}, gamma={args.gamma}")
    print(f"时间范围: {args.start_date} ~ {args.end_date}")
    if topic_like:
        print(f"主题过滤: {topic_like}")

    topic_reports: List[Dict] = []

    for p in args.platforms:
        print(f"\n>>> 平台: {p}")
        rows = fetch_rows(p, args.start_date, args.end_date, args.max_rows_per_platform)
        print(f"读取评论行数: {len(rows)}")
        by_topic: Dict[str, List[Tuple]] = defaultdict(list)
        for r in rows:
            topic = (r[0] or "未分类").strip() or "未分类"
            if topic_like and topic_like not in topic.lower():
                continue
            if len(by_topic[topic]) >= args.max_comments_per_topic:
                continue
            by_topic[topic].append(r)

        topic_items = sorted(by_topic.items(), key=lambda kv: len(kv[1]), reverse=True)[: args.max_topics]
        topic_items = [kv for kv in topic_items if len(kv[1]) >= args.min_comments_per_topic]
        print(f"候选话题数: {len(topic_items)}")

        for topic_name, topic_rows in topic_items:
            report = evaluate_topic(p, topic_name, topic_rows, analyzer)
            topic_reports.append(report)

    if not topic_reports:
        print("\n没有满足条件的话题数据。")
        return

    topic_reports.sort(
        key=lambda x: (
            float(x["topic_ri"]),
            float(x["danger_ratio"]),
            int(x["comment_count"]),
        ),
        reverse=True,
    )

    print("\n" + "=" * 120)
    print(f"话题 RI 排行（Top {args.top_n}）")
    print("=" * 120)
    for i, t in enumerate(topic_reports[: args.top_n], start=1):
        print(
            f"{i:>2}. [{t['platform']}] topic={t['topic_name']} | comments={t['comment_count']} "
            f"| topic_RI={t['topic_ri']} | weighted_RI={t['weighted_ri']} | avg_RI={t['avg_ri']} "
            f"| danger_ratio={t['danger_ratio']} | attack_ratio={t['attack_ratio']}"
        )
        for c in t["top_comments"][:3]:
            print(
                f"    - id={c['comment_id']} RI={c['risk_index']} likes={c['like_count']} "
                f"reason={c.get('risk_reason','')}"
            )
            print(f"      text={c['text_preview']}")


if __name__ == "__main__":
    main()

