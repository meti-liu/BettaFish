"""
使用数据库真实评论做 RI 试算。

用途：
1) 从 weibo/xhs/dy 评论表抽样；
2) 调用 RiskIndexAnalyzer 进行评分；
3) 输出高风险/低风险样本，便于人工校验“准不准”。
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import asdict
from typing import Dict, List, Tuple

import pymysql

# 兼容直接脚本执行时的模块导入路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import settings
from InsightEngine.tools.risk_index_analyzer import RiskIndexAnalyzer


PLATFORM_SQL = {
    "weibo": {
        "top_like_sql": """
            SELECT c.comment_id, c.content, c.comment_like_count, c.create_time
            FROM weibo_note_comment c
            WHERE COALESCE(c.content, '') <> ''
            ORDER BY CAST(COALESCE(c.comment_like_count, '0') AS UNSIGNED) DESC
            LIMIT %s
        """,
        "latest_sql": """
            SELECT c.comment_id, c.content, c.comment_like_count, c.create_time
            FROM weibo_note_comment c
            WHERE COALESCE(c.content, '') <> ''
            ORDER BY c.create_time DESC
            LIMIT %s
        """,
        "like_cast": lambda x: int(x or 0),
        "time_cast": lambda x: float(x or 0),
    },
    "xhs": {
        "top_like_sql": """
            SELECT c.comment_id, c.content, c.like_count, c.create_time
            FROM xhs_note_comment c
            WHERE COALESCE(c.content, '') <> ''
            ORDER BY CAST(COALESCE(c.like_count, '0') AS UNSIGNED) DESC
            LIMIT %s
        """,
        "latest_sql": """
            SELECT c.comment_id, c.content, c.like_count, c.create_time
            FROM xhs_note_comment c
            WHERE COALESCE(c.content, '') <> ''
            ORDER BY c.create_time DESC
            LIMIT %s
        """,
        "like_cast": lambda x: int(x or 0),
        "time_cast": lambda x: float(x or 0),
    },
    "dy": {
        "top_like_sql": """
            SELECT c.comment_id, c.content, c.like_count, c.create_time
            FROM douyin_aweme_comment c
            WHERE COALESCE(c.content, '') <> ''
            ORDER BY CAST(COALESCE(c.like_count, '0') AS UNSIGNED) DESC
            LIMIT %s
        """,
        "latest_sql": """
            SELECT c.comment_id, c.content, c.like_count, c.create_time
            FROM douyin_aweme_comment c
            WHERE COALESCE(c.content, '') <> ''
            ORDER BY c.create_time DESC
            LIMIT %s
        """,
        "like_cast": lambda x: int(x or 0),
        "time_cast": lambda x: float(x or 0),
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


def _safe_text(text: str, max_len: int = 80) -> str:
    t = (text or "").replace("\n", " ").replace("\r", " ").strip()
    return t if len(t) <= max_len else t[: max_len - 3] + "..."


def _build_h_norms(likes: List[int]) -> List[float]:
    vals = [max(1, int(x)) for x in likes]
    logs = [math.log(v) for v in vals]
    mn, mx = min(logs), max(logs)
    if mx == mn:
        return [0.5 for _ in logs]
    return [(v - mn) / (mx - mn) for v in logs]


def _build_v_velocity(times: List[float]) -> List[float]:
    """
    用“时间新近程度”做简化传播速度 proxy（仅用于试算演示）。
    越新 -> 越接近 1。
    """
    if not times:
        return []
    mn, mx = min(times), max(times)
    if mx == mn:
        return [0.3 for _ in times]
    return [(t - mn) / (mx - mn) for t in times]


def fetch_platform_comments(platform: str, limit: int, sample_mode: str) -> List[Tuple]:
    cfg = PLATFORM_SQL[platform]
    with db_conn() as conn:
        with conn.cursor() as cur:
            if sample_mode == "top_like":
                cur.execute(cfg["top_like_sql"], [limit])
                return list(cur.fetchall())
            if sample_mode == "latest":
                cur.execute(cfg["latest_sql"], [limit])
                return list(cur.fetchall())

            # mixed: 一半高赞 + 一半最新，避免样本单一
            top_n = max(1, limit // 2)
            latest_n = max(1, limit - top_n)
            cur.execute(cfg["top_like_sql"], [top_n])
            top_rows = list(cur.fetchall())
            cur.execute(cfg["latest_sql"], [latest_n])
            latest_rows = list(cur.fetchall())
            merged: List[Tuple] = []
            seen = set()
            for row in top_rows + latest_rows:
                key = str(row[0])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(row)
            return merged[:limit]


def evaluate_platform(
    platform: str, limit: int, analyzer: RiskIndexAnalyzer, sample_mode: str
) -> List[Dict]:
    cfg = PLATFORM_SQL[platform]
    rows = fetch_platform_comments(platform, limit, sample_mode)
    if not rows:
        return []

    likes = [cfg["like_cast"](r[2]) for r in rows]
    times = [cfg["time_cast"](r[3]) for r in rows]
    h_norms = _build_h_norms(likes)
    v_vels = _build_v_velocity(times)

    results = []
    for i, row in enumerate(rows):
        comment_id, content, like_count, _create_time = row
        ri = analyzer.analyze_single_text(
            text=str(content),
            h_norm=h_norms[i],
            v_velocity=v_vels[i],
            initialize_if_needed=True,
        )
        item = asdict(ri)
        item.update(
            {
                "platform": platform,
                "comment_id": str(comment_id),
                "like_count": int(cfg["like_cast"](like_count)),
                "text_preview": _safe_text(str(content), 100),
                "h_norm": round(h_norms[i], 4),
                "v_velocity": round(v_vels[i], 4),
            }
        )
        results.append(item)
    return results


def print_report(all_items: List[Dict], top_n: int = 10):
    valid = [x for x in all_items if x.get("analysis_performed")]
    failed = [x for x in all_items if not x.get("analysis_performed")]
    valid.sort(key=lambda x: float(x.get("risk_index", 0.0)), reverse=True)

    print("=" * 100)
    print(f"总样本: {len(all_items)} | 成功分析: {len(valid)} | 失败: {len(failed)}")
    print("=" * 100)
    level_stats: Dict[str, int] = {}
    for x in valid:
        lv = str(x.get("risk_level", "未知"))
        level_stats[lv] = level_stats.get(lv, 0) + 1
    if level_stats:
        print("风险等级分布:", " | ".join([f"{k}:{v}" for k, v in sorted(level_stats.items())]))

    print("\n[高风险 Top]")
    high_items = valid[:top_n]
    for i, x in enumerate(high_items, start=1):
        print(
            f"{i:>2}. [{x['platform']}] id={x['comment_id']} RI={x['risk_index']:<6} "
            f"level={x['risk_level']:<2} S={x['sentiment_score']:<5} I={x['impact_coefficient']:<4} "
            f"likes={x['like_count']:<4} text={x['text_preview']}\n"
            f"     reason={x.get('risk_reason','')}"
        )

    print("\n[低风险 Top]")
    high_keys = {(x["platform"], x["comment_id"]) for x in high_items}
    low_candidates = [x for x in reversed(valid) if (x["platform"], x["comment_id"]) not in high_keys]
    for i, x in enumerate(low_candidates[:top_n], start=1):
        print(
            f"{i:>2}. [{x['platform']}] id={x['comment_id']} RI={x['risk_index']:<6} "
            f"level={x['risk_level']:<2} S={x['sentiment_score']:<5} I={x['impact_coefficient']:<4} "
            f"likes={x['like_count']:<4} text={x['text_preview']}\n"
            f"     reason={x.get('risk_reason','')}"
        )

    if failed:
        print("\n[失败样本]")
        for i, x in enumerate(failed[:5], start=1):
            print(f"{i:>2}. [{x['platform']}] id={x['comment_id']} error={x.get('error_message')}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate RI model on DB comments")
    parser.add_argument(
        "--platforms",
        nargs="+",
        default=["weibo", "xhs", "dy"],
        choices=["weibo", "xhs", "dy"],
        help="Platforms to evaluate",
    )
    parser.add_argument("--limit-per-platform", type=int, default=20, help="Sample size per platform")
    parser.add_argument("--top-n", type=int, default=10, help="Show top N high/low risk rows")
    parser.add_argument("--alpha", type=float, default=0.1, help="RI weight for heatness")
    parser.add_argument("--beta", type=float, default=0.8, help="RI weight for sentiment*impact")
    parser.add_argument("--gamma", type=float, default=0.1, help="RI weight for velocity")
    parser.add_argument(
        "--sample-mode",
        type=str,
        default="mixed",
        choices=["mixed", "top_like", "latest"],
        help="Sampling strategy per platform",
    )
    args = parser.parse_args()
    analyzer = RiskIndexAnalyzer(alpha=args.alpha, beta=args.beta, gamma=args.gamma)
    print(f"RI 权重: alpha={args.alpha}, beta={args.beta}, gamma={args.gamma}")

    all_items: List[Dict] = []
    for p in args.platforms:
        print(
            f"\n>>> 抽样平台: {p}, limit={args.limit_per_platform}, mode={args.sample_mode}"
        )
        items = evaluate_platform(p, args.limit_per_platform, analyzer, args.sample_mode)
        print(f"    获取并分析: {len(items)} 条")
        all_items.extend(items)

    print_report(all_items, top_n=args.top_n)


if __name__ == "__main__":
    main()

