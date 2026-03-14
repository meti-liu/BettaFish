from __future__ import annotations

import math
import re
import time
from difflib import SequenceMatcher
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple

import pymysql
from flask import Blueprint, jsonify, render_template, request

from config import settings
from InsightEngine.tools.risk_index_analyzer import RiskIndexAnalyzer


mvp_bp = Blueprint("mvp", __name__, url_prefix="/mvp")


PROVINCES = [
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
]

PLATFORM_CONFIG = {
    "weibo": {
        "label": "微博",
        "note_table": "weibo_note",
        "comment_table": "weibo_note_comment",
        "join_key": "note_id",
        "note_time_expr": "DATE(FROM_UNIXTIME(n.create_time + 28800))",
        "note_time_fmt": "DATE_FORMAT(FROM_UNIXTIME(n.create_time + 28800), '%%Y-%%m-%%d %%H:%%i:%%s')",
        "comment_time_expr": "DATE(FROM_UNIXTIME(c.create_time + 28800))",
        "topic_expr": "COALESCE(n.corpus_topic, n.source_keyword, '未分类')",
        "content_expr": "COALESCE(n.content, '')",
        "nickname_expr": "COALESCE(n.nickname, '')",
        "note_ip_expr": "COALESCE(n.ip_location, '')",
        "liked_expr": "CAST(COALESCE(n.liked_count, '0') AS UNSIGNED)",
        "comments_expr": "CAST(COALESCE(n.comments_count, '0') AS UNSIGNED)",
        "shared_expr": "CAST(COALESCE(n.shared_count, '0') AS UNSIGNED)",
        "comment_ip_expr": "COALESCE(c.ip_location, '')",
        "comment_like_expr": "CAST(COALESCE(c.comment_like_count, '0') AS UNSIGNED)",
        "comment_ts_expr": "(c.create_time + 28800)",
        "comment_time_fmt": "DATE_FORMAT(FROM_UNIXTIME(c.create_time + 28800), '%%Y-%%m-%%d %%H:%%i:%%s')",
        "comment_content_expr": "COALESCE(c.content, '')",
        "comment_nickname_expr": "COALESCE(c.nickname, '')",
    },
    "xhs": {
        "label": "小红书",
        "note_table": "xhs_note",
        "comment_table": "xhs_note_comment",
        "join_key": "note_id",
        "note_time_expr": "DATE(FROM_UNIXTIME(CASE WHEN n.time > 20000000000 THEN n.time/1000 ELSE n.time END + 28800))",
        "note_time_fmt": "DATE_FORMAT(FROM_UNIXTIME(CASE WHEN n.time > 20000000000 THEN n.time/1000 ELSE n.time END + 28800), '%%Y-%%m-%%d %%H:%%i:%%s')",
        "comment_time_expr": "DATE(FROM_UNIXTIME(CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800))",
        "topic_expr": "COALESCE(n.corpus_topic, n.source_keyword, n.title, '未分类')",
        "content_expr": "CONCAT(COALESCE(n.title, ''), ' ', COALESCE(n.desc, ''))",
        "nickname_expr": "COALESCE(n.nickname, '')",
        "note_ip_expr": "COALESCE(n.ip_location, '')",
        "liked_expr": "CAST(COALESCE(n.liked_count, '0') AS UNSIGNED)",
        "comments_expr": "CAST(COALESCE(n.comment_count, '0') AS UNSIGNED)",
        "shared_expr": "CAST(COALESCE(n.share_count, '0') AS UNSIGNED)",
        "comment_ip_expr": "COALESCE(c.ip_location, '')",
        "comment_like_expr": "CAST(COALESCE(c.like_count, '0') AS UNSIGNED)",
        "comment_ts_expr": "(CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800)",
        "comment_time_fmt": "DATE_FORMAT(FROM_UNIXTIME(CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800), '%%Y-%%m-%%d %%H:%%i:%%s')",
        "comment_content_expr": "COALESCE(c.content, '')",
        "comment_nickname_expr": "COALESCE(c.nickname, '')",
    },
    "dy": {
        "label": "抖音",
        "note_table": "douyin_aweme",
        "comment_table": "douyin_aweme_comment",
        "join_key": "aweme_id",
        "note_time_expr": "DATE(FROM_UNIXTIME(CASE WHEN n.create_time > 20000000000 THEN n.create_time/1000 ELSE n.create_time END + 28800))",
        "note_time_fmt": "DATE_FORMAT(FROM_UNIXTIME(CASE WHEN n.create_time > 20000000000 THEN n.create_time/1000 ELSE n.create_time END + 28800), '%%Y-%%m-%%d %%H:%%i:%%s')",
        "comment_time_expr": "DATE(FROM_UNIXTIME(CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800))",
        "topic_expr": "COALESCE(n.corpus_topic, n.source_keyword, n.title, '未分类')",
        "content_expr": "CONCAT(COALESCE(n.title, ''), ' ', COALESCE(n.desc, ''))",
        "nickname_expr": "COALESCE(n.nickname, '')",
        "note_ip_expr": "COALESCE(n.ip_location, '')",
        "liked_expr": "CAST(COALESCE(n.liked_count, '0') AS UNSIGNED)",
        "comments_expr": "CAST(COALESCE(n.comment_count, '0') AS UNSIGNED)",
        "shared_expr": "CAST(COALESCE(n.share_count, '0') AS UNSIGNED)",
        "comment_ip_expr": "COALESCE(c.ip_location, '')",
        "comment_like_expr": "CAST(COALESCE(c.like_count, '0') AS UNSIGNED)",
        "comment_ts_expr": "(CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800)",
        "comment_time_fmt": "DATE_FORMAT(FROM_UNIXTIME(CASE WHEN c.create_time > 20000000000 THEN c.create_time/1000 ELSE c.create_time END + 28800), '%%Y-%%m-%%d %%H:%%i:%%s')",
        "comment_content_expr": "COALESCE(c.content, '')",
        "comment_nickname_expr": "COALESCE(c.nickname, '')",
    },
}

STOPWORDS = {
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "以及",
    "就是",
    "一个",
    "一些",
    "可以",
    "进行",
    "相关",
    "什么",
    "怎么",
    "真的",
    "非常",
    "一下",
    "还是",
    "自己",
}

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

RISK_CONTEXT_TERMS = {
    "战争",
    "轰炸",
    "冲突",
    "制裁",
    "导弹",
    "核",
    "恐袭",
    "毒品",
    "贩毒",
    "走私",
    "枪击",
    "暴恐",
    "伊朗",
    "美国",
}

ri_analyzer = RiskIndexAnalyzer(alpha=0.1, beta=0.8, gamma=0.1)
_API_CACHE: Dict[str, Tuple[float, Dict]] = {}
_API_CACHE_TTL_SECONDS = 180
_API_CACHE_MAX_ITEMS = 256


def _db_conn():
    return pymysql.connect(
        host=settings.DB_HOST,
        port=int(settings.DB_PORT),
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset=settings.DB_CHARSET or "utf8mb4",
        autocommit=True,
    )


def _parse_date_range() -> Tuple[date, date]:
    today = datetime.now().date()
    default_start = today - timedelta(days=29)
    start_raw = (request.args.get("start_date") or "").strip()
    end_raw = (request.args.get("end_date") or "").strip()
    try:
        start_d = datetime.strptime(start_raw, "%Y-%m-%d").date() if start_raw else default_start
    except ValueError:
        start_d = default_start
    try:
        end_d = datetime.strptime(end_raw, "%Y-%m-%d").date() if end_raw else today
    except ValueError:
        end_d = today
    if end_d < start_d:
        start_d, end_d = end_d, start_d
    return start_d, end_d


def _platform_key() -> str:
    platform = (request.args.get("platform") or "weibo").strip().lower()
    if platform not in PLATFORM_CONFIG:
        return "weibo"
    return platform


def _risk_index_from_heat(heat: float) -> float:
    if heat <= 0:
        return 0.0
    # 软饱和：避免中高互动量样本大面积顶到 100
    x = math.log1p(max(0.0, float(heat)))
    score = 100.0 * (1.0 - math.exp(-x / 4.2))
    return min(95.0, round(score, 2))


def _risk_level(ri: float) -> str:
    if ri >= 80:
        return "危险"
    if ri >= 60:
        return "警告"
    if ri >= 40:
        return "关注"
    return "安全"


def _province_from_ip(ip_location: str) -> str:
    text = (ip_location or "").strip()
    if not text:
        return ""
    for p in PROVINCES:
        if p in text:
            return p
    if "内蒙古" in text:
        return "内蒙古"
    if "广西" in text:
        return "广西"
    if "宁夏" in text:
        return "宁夏"
    if "新疆" in text:
        return "新疆"
    if "西藏" in text:
        return "西藏"
    return ""


def _topic_filter_sql(cfg: Dict, topic: str, where: List[str], params: List):
    if not topic:
        return
    topic_like = f"%{topic}%"
    where.append(
        "("
        f"{cfg['topic_expr']} LIKE %s "
        f"OR {cfg['content_expr']} LIKE %s "
        "OR COALESCE(n.source_keyword, '') LIKE %s "
        "OR COALESCE(n.corpus_keyword, '') LIKE %s "
        "OR COALESCE(n.corpus_topic, '') LIKE %s "
        "OR COALESCE(n.lang_theme, '') LIKE %s "
        "OR COALESCE(n.lang_sub_theme, '') LIKE %s "
        "OR COALESCE(n.lang_third_theme, '') LIKE %s"
        ")"
    )
    params.extend([topic_like, topic_like, topic_like, topic_like, topic_like, topic_like, topic_like, topic_like])


def _apply_theme_filters(where: List[str], params: List):
    theme = (request.args.get("theme") or "").strip()
    sub_theme = (request.args.get("sub_theme") or "").strip()
    if theme:
        where.append("COALESCE(n.lang_theme, '') = %s")
        params.append(theme)
    if sub_theme:
        where.append("COALESCE(n.lang_sub_theme, '') = %s")
        params.append(sub_theme)


def _cache_key(name: str) -> str:
    kv = tuple(sorted((k, v) for k, v in request.args.items() if k not in {"_ts"}))
    return f"{name}:{kv}"


def _cache_get(name: str):
    if request.args.get("force_refresh") == "1":
        return None
    key = _cache_key(name)
    item = _API_CACHE.get(key)
    if not item:
        return None
    ts, payload = item
    if time.time() - ts > _API_CACHE_TTL_SECONDS:
        _API_CACHE.pop(key, None)
        return None
    return payload


def _cache_set(name: str, payload: Dict):
    if len(_API_CACHE) >= _API_CACHE_MAX_ITEMS:
        # 简单清理过期项；若仍超限则清空
        now = time.time()
        expired_keys = [k for k, (ts, _) in _API_CACHE.items() if now - ts > _API_CACHE_TTL_SECONDS]
        for k in expired_keys:
            _API_CACHE.pop(k, None)
        if len(_API_CACHE) >= _API_CACHE_MAX_ITEMS:
            _API_CACHE.clear()
    _API_CACHE[_cache_key(name)] = (time.time(), payload)


def _log_minmax(vals: List[float], default: float = 0.5) -> List[float]:
    if not vals:
        return []
    logs = [math.log(max(1.0, float(v))) for v in vals]
    mn, mx = min(logs), max(logs)
    if mx == mn:
        return [default for _ in logs]
    return [(v - mn) / (mx - mn) for v in logs]


def _minmax(vals: List[float], default: float = 0.3) -> List[float]:
    if not vals:
        return []
    mn, mx = min(vals), max(vals)
    if mx == mn:
        return [default for _ in vals]
    return [(v - mn) / (mx - mn) for v in vals]


def _topic_ri_reports(
    cfg: Dict,
    start_d: date,
    end_d: date,
    topic: str,
    max_topics: int,
    max_comments_per_topic: int,
    max_rows: int,
    theme: str = "",
    sub_theme: str = "",
) -> List[Dict]:
    where = [f"{cfg['comment_time_expr']} BETWEEN %s AND %s"]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
    if theme:
        where.append("COALESCE(n.lang_theme, '') = %s")
        params.append(theme)
    if sub_theme:
        where.append("COALESCE(n.lang_sub_theme, '') = %s")
        params.append(sub_theme)
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            {cfg['topic_expr']} AS topic_name,
            c.{cfg['join_key']} AS join_key,
            {cfg['comment_content_expr']} AS comment_content,
            {cfg['comment_like_expr']} AS comment_like,
            {cfg['comment_ts_expr']} AS comment_ts
        FROM {cfg['comment_table']} c
        JOIN {cfg['note_table']} n ON c.{cfg['join_key']} = n.{cfg['join_key']}
        WHERE {where_sql}
        ORDER BY {cfg['comment_ts_expr']} DESC
        LIMIT %s
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params + [max_rows])
            rows = cur.fetchall()

    by_topic: Dict[str, List[Tuple]] = defaultdict(list)
    for topic_name, join_key, comment_content, comment_like, comment_ts in rows:
        t = (topic_name or "未分类").strip() or "未分类"
        if len(by_topic[t]) >= max_comments_per_topic:
            continue
        by_topic[t].append((join_key, comment_content or "", int(comment_like or 0), float(comment_ts or 0.0)))

    topic_rows = sorted(by_topic.items(), key=lambda kv: len(kv[1]), reverse=True)[:max_topics]
    reports: List[Dict] = []
    for topic_name, trows in topic_rows:
        texts = [r[1] for r in trows]
        likes = [r[2] for r in trows]
        times = [r[3] for r in trows]
        h_norm = _log_minmax(likes)
        v_vel = _minmax(times)
        batch = ri_analyzer.analyze_batch_texts(texts, h_norm, v_vel, initialize_if_needed=True)
        valid = []
        for idx, rr in enumerate(batch.results):
            if not rr.analysis_performed:
                continue
            raw_txt = texts[idx]
            valid.append(
                {
                    "comment_id": str(trows[idx][0]),
                    "text": raw_txt,
                    "like_count": likes[idx],
                    "risk_index": float(rr.risk_index),
                    "risk_level": rr.risk_level,
                    "sentiment_score": float(rr.sentiment_score),
                    "impact_coefficient": float(rr.impact_coefficient),
                    "risk_reason": rr.risk_reason,
                    "ts": times[idx],
                }
            )
        if not valid:
            continue

        weights = [1.0 + math.log1p(max(0, int(x["like_count"]))) for x in valid]
        weighted_ri = sum(x["risk_index"] * w for x, w in zip(valid, weights)) / max(1e-9, sum(weights))
        avg_ri = sum(x["risk_index"] for x in valid) / len(valid)
        danger_ratio = sum(1 for x in valid if x["risk_index"] >= 80.0) / len(valid)
        attack_ratio = sum(1 for x in valid if any(t in x["text"].lower() for t in ATTACK_HINT_TERMS)) / len(valid)
        context_hits = 0
        for x in valid:
            text_l = x["text"].lower()
            if any(k in text_l for k in RISK_CONTEXT_TERMS):
                context_hits += 1
        context_ratio = context_hits / len(valid)
        if any(k in topic_name for k in RISK_CONTEXT_TERMS):
            context_ratio = min(1.0, context_ratio + 0.2)

        topic_ri = (
            0.50 * weighted_ri
            + 0.20 * (danger_ratio * 100.0)
            + 0.15 * (attack_ratio * 100.0)
            + 0.15 * (context_ratio * 100.0)
        )

        day_map = defaultdict(int)
        for x in valid:
            if x["ts"] > 0:
                day_map[datetime.fromtimestamp(x["ts"]).date().isoformat()] += 1
        counts = list(day_map.values()) or [len(valid)]
        velocity_raw = (max(counts) - min(counts)) / max(1.0, (sum(counts) / len(counts)))

        reports.append(
            {
                "topic_name": topic_name,
                "comment_count": len(valid),
                "topic_ri": round(topic_ri, 2),
                "weighted_ri": round(weighted_ri, 2),
                "avg_ri": round(avg_ri, 2),
                "danger_ratio": round(danger_ratio, 4),
                "attack_ratio": round(attack_ratio, 4),
                "context_ratio": round(context_ratio, 4),
                "velocity_raw": float(velocity_raw),
                "top_comments": sorted(valid, key=lambda x: (x["risk_index"], x["like_count"]), reverse=True)[:20],
            }
        )

    reports.sort(key=lambda x: (x["topic_ri"], x["danger_ratio"], x["comment_count"]), reverse=True)
    return reports


@mvp_bp.route("/")
def hot_ranking_page():
    return render_template("mvp/hot_ranking.html", page_key="hot")


@mvp_bp.route("/trend")
def trend_page():
    return render_template("mvp/trend.html", page_key="trend")


@mvp_bp.route("/heatmap")
def heatmap_page():
    return render_template("mvp/heatmap.html", page_key="heatmap")


@mvp_bp.route("/event-analysis")
def event_analysis_page():
    return render_template("mvp/event_analysis.html", page_key="event_analysis")


@mvp_bp.route("/response-center")
def response_center_page():
    return render_template("mvp/response_center.html", page_key="response_center")


@mvp_bp.route("/api/hot-events")
def api_hot_events():
    cached = _cache_get("hot-events")
    if cached is not None:
        return jsonify(cached)
    topic = (request.args.get("topic") or "").strip()
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    page = max(1, int(request.args.get("page", 1) or 1))
    page_size = max(1, min(50, int(request.args.get("page_size", 10) or 10)))
    start_d, end_d = _parse_date_range()
    offset = (page - 1) * page_size

    where = [
        f"{cfg['note_time_expr']} BETWEEN %s AND %s",
    ]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
    _apply_theme_filters(where, params)
    where_sql = " AND ".join(where)

    count_sql = f"SELECT COUNT(1) FROM {cfg['note_table']} n WHERE {where_sql}"
    data_sql = f"""
        SELECT
            n.id,
            {cfg['topic_expr']} AS topic_name,
            {cfg['content_expr']} AS content,
            {cfg['nickname_expr']} AS nickname,
            {cfg['note_time_fmt']} AS create_time,
            {cfg['liked_expr']} AS liked_count,
            {cfg['comments_expr']} AS comments_count,
            {cfg['shared_expr']} AS shared_count
        FROM {cfg['note_table']} n
        WHERE {where_sql}
        ORDER BY n.id DESC
        LIMIT %s OFFSET %s
    """

    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = int(cur.fetchone()[0] or 0)
            cur.execute(data_sql, params + [page_size, offset])
            rows = cur.fetchall()

    items = []
    for r in rows:
        heat = float((r[5] or 0) + (r[6] or 0) + (r[7] or 0))
        content_text = str(r[2] or "")
        txt_l = content_text.lower()
        has_attack_hint = any(t in txt_l for t in ATTACK_HINT_TERMS)

        # 热度基线（不再直接把高热=100）
        base_ri = _risk_index_from_heat(heat)

        # 文本语义 RI（截断控制成本，避免超长营销文影响性能）
        semantic_ri = base_ri
        try:
            semantic_input = content_text[:1200]
            rr = ri_analyzer.analyze_single_text(
                text=semantic_input,
                h_norm=min(1.0, math.log1p(max(0.0, heat)) / 12.0),
                v_velocity=0.25,
            )
            if rr and rr.success and rr.analysis_performed:
                semantic_ri = float(rr.risk_index)
        except Exception:
            semantic_ri = base_ri

        # 混合评分：语义主导，热度辅助
        mixed_ri = 0.68 * semantic_ri + 0.32 * base_ri
        # 无攻击提示词时做上限保护，避免“学习/日常”类被误顶格
        if not has_attack_hint:
            mixed_ri = min(mixed_ri, 88.0)

        items.append(
            {
                "id": r[0],
                "topic_name": r[1],
                "content": content_text,
                "nickname": r[3],
                "create_time": r[4],
                "liked_count": int(r[5] or 0),
                "comments_count": int(r[6] or 0),
                "shared_count": int(r[7] or 0),
                "risk_index": round(max(0.0, min(100.0, mixed_ri)), 2),
                "platform": platform,
            }
        )

    total_pages = max(1, math.ceil(total / page_size))
    payload = {
        "success": True,
        "data": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
        "meta": {"platform": platform, "platform_label": cfg["label"]},
    }
    _cache_set("hot-events", payload)
    return jsonify(payload)


@mvp_bp.route("/api/ranking")
def api_ranking():
    cached = _cache_get("ranking")
    if cached is not None:
        return jsonify(cached)
    topic = (request.args.get("topic") or "").strip()
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    top_n = max(1, min(50, int(request.args.get("top_n", 10) or 10)))
    start_d, end_d = _parse_date_range()
    where = [
        f"{cfg['note_time_expr']} BETWEEN %s AND %s",
    ]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
    _apply_theme_filters(where, params)
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            {cfg['topic_expr']} AS topic_name,
            {cfg['nickname_expr']} AS nickname,
            {cfg['note_time_fmt']} AS create_time,
            {cfg['liked_expr']} AS liked_count,
            {cfg['comments_expr']} AS comments_count,
            {cfg['shared_expr']} AS shared_count
        FROM {cfg['note_table']} n
        WHERE {where_sql}
        ORDER BY ({cfg['liked_expr']} + {cfg['comments_expr']} + {cfg['shared_expr']}) DESC
        LIMIT %s
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params + [top_n])
            rows = cur.fetchall()

    data = []
    for r in rows:
        heat = int((r[3] or 0) + (r[4] or 0) + (r[5] or 0))
        data.append(
            {
                "topic_name": r[0],
                "nickname": r[1],
                "create_time": r[2],
                "heat_score": heat,
                "platform": platform,
            }
        )
    payload = {"success": True, "data": data, "meta": {"platform": platform, "platform_label": cfg["label"]}}
    _cache_set("ranking", payload)
    return jsonify(payload)


@mvp_bp.route("/api/trend-30d")
def api_trend_30d():
    cached = _cache_get("trend-30d")
    if cached is not None:
        return jsonify(cached)
    topic = (request.args.get("topic") or "").strip()
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    where = [
        f"{cfg['note_time_expr']} BETWEEN %s AND %s",
    ]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
    _apply_theme_filters(where, params)
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT
            {cfg['note_time_expr']} AS d,
            COUNT(1) AS cnt,
            AVG({cfg['liked_expr']} + {cfg['comments_expr']} + {cfg['shared_expr']}) AS avg_heat
        FROM {cfg['note_table']} n
        WHERE {where_sql}
        GROUP BY d
        ORDER BY d
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    day_map: Dict[str, Tuple[int, float]] = {}
    for d, cnt, avg_heat in rows:
        day_map[str(d)] = (int(cnt or 0), float(avg_heat or 0.0))

    # 每日攻击占比（轻量代理）：攻击词命中评论数 / 当日评论总数
    attack_like_terms = [f"%{t.lower()}%" for t in ATTACK_HINT_TERMS]
    attack_cond = " OR ".join([f"LOWER({cfg['comment_content_expr']}) LIKE %s" for _ in ATTACK_HINT_TERMS]) or "1=0"
    c_where = [f"{cfg['comment_time_expr']} BETWEEN %s AND %s"]
    c_params: List = [start_d, end_d]
    if topic:
        _topic_filter_sql(cfg, topic, c_where, c_params)
        _apply_theme_filters(c_where, c_params)
    c_where_sql = " AND ".join(c_where)
    c_sql = f"""
        SELECT
            {cfg['comment_time_expr']} AS d,
            COUNT(1) AS c_cnt,
            SUM(CASE WHEN ({attack_cond}) THEN 1 ELSE 0 END) AS attack_cnt
        FROM {cfg['comment_table']} c
        JOIN {cfg['note_table']} n ON c.{cfg['join_key']} = n.{cfg['join_key']}
        WHERE {c_where_sql}
        GROUP BY d
        ORDER BY d
    """
    attack_map: Dict[str, Tuple[int, int]] = {}
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(c_sql, c_params + attack_like_terms)
            c_rows = cur.fetchall()
    for d, c_cnt, attack_cnt in c_rows:
        attack_map[str(d)] = (int(c_cnt or 0), int(attack_cnt or 0))

    dates: List[str] = []
    topic_counts: List[int] = []
    avg_heat_list: List[float] = []
    attack_ratio_list: List[float] = []
    cur_d = start_d
    while cur_d <= end_d:
        key = cur_d.isoformat()
        cnt, avg_heat = day_map.get(key, (0, 0.0))
        c_cnt, attack_cnt = attack_map.get(key, (0, 0))
        dates.append(key)
        topic_counts.append(cnt)
        avg_heat_list.append(float(avg_heat))
        attack_ratio_list.append((attack_cnt / c_cnt) if c_cnt > 0 else 0.0)
        cur_d += timedelta(days=1)

    # 按当前时间窗口内的热度做归一，避免曲线长期贴边
    heat_logs = [math.log1p(max(0.0, x)) for x in avg_heat_list]
    if heat_logs:
        h_min, h_max = min(heat_logs), max(heat_logs)
    else:
        h_min, h_max = 0.0, 0.0
    heat_norm = [((h - h_min) / (h_max - h_min) * 100.0) if h_max > h_min else 0.0 for h in heat_logs]

    # 综合 RI：热度(55%) + 攻击占比(45%)
    risk_index: List[float] = []
    attack_ratio_pct: List[float] = []
    for hn, ar in zip(heat_norm, attack_ratio_list):
        ar_pct = max(0.0, min(100.0, ar * 100.0))
        attack_ratio_pct.append(round(ar_pct, 2))
        ri = 0.55 * hn + 0.45 * ar_pct
        risk_index.append(round(max(0.0, min(100.0, ri)), 2))

    payload = {
        "success": True,
        "data": {
            "dates": dates,
            "topic_counts": topic_counts,
            "risk_index": risk_index,
            "attack_ratio": attack_ratio_pct,
            "heat_norm": [round(x, 2) for x in heat_norm],
        },
        "meta": {"platform": platform, "platform_label": cfg["label"]},
    }
    _cache_set("trend-30d", payload)
    return jsonify(payload)


@mvp_bp.route("/api/heatmap-china")
def api_heatmap_china():
    cached = _cache_get("heatmap-china")
    if cached is not None:
        return jsonify(cached)
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    where = [f"{cfg['note_time_expr']} BETWEEN %s AND %s"]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
    _apply_theme_filters(where, params)
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            {cfg['note_ip_expr']} AS ip_location,
            ({cfg['liked_expr']} + {cfg['comments_expr']} + {cfg['shared_expr']}) AS heat_score,
            {cfg['content_expr']} AS content_text
        FROM {cfg['note_table']} n
        WHERE {where_sql}
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    agg = defaultdict(lambda: {"event_count": 0, "like_sum": 0, "attack_count": 0})
    for ip_location, heat_score, content_text in rows:
        province = _province_from_ip(ip_location)
        if not province:
            continue
        agg[province]["event_count"] += 1
        agg[province]["like_sum"] += int(heat_score or 0)
        text_l = str(content_text or "").lower()
        if any(t in text_l for t in ATTACK_HINT_TERMS):
            agg[province]["attack_count"] += 1

    # Fallback for platforms where note-level ip_location is often empty:
    # use comment-level IP to recover regional distribution.
    if not agg:
        comment_sql = f"""
            SELECT
                {cfg['comment_ip_expr']} AS ip_location,
                {cfg['comment_like_expr']} AS like_score,
                {cfg['comment_content_expr']} AS content_text
            FROM {cfg['comment_table']} c
            JOIN {cfg['note_table']} n ON c.{cfg['join_key']} = n.{cfg['join_key']}
            WHERE {where_sql}
        """
        with _db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(comment_sql, params)
                c_rows = cur.fetchall()
        for ip_location, like_score, content_text in c_rows:
            province = _province_from_ip(ip_location)
            if not province:
                continue
            agg[province]["event_count"] += 1
            agg[province]["like_sum"] += int(like_score or 0)
            text_l = str(content_text or "").lower()
            if any(t in text_l for t in ATTACK_HINT_TERMS):
                agg[province]["attack_count"] += 1

    province_heat = []
    for province, st in agg.items():
        event_count = int(st["event_count"] or 0)
        if event_count <= 0:
            continue
        heat = float(event_count * 3 + st["like_sum"])
        attack_ratio = float(st["attack_count"] / max(1, event_count))
        # 风险值在热度基础上叠加攻击占比，避免和热度完全同质
        risk_raw = heat * (1.0 + min(attack_ratio * 1.1, 0.8)) + event_count * 2.0
        province_heat.append((province, heat, risk_raw, event_count, attack_ratio))

    if not province_heat:
        return jsonify({"success": True, "data": [], "meta": {"platform": platform, "platform_label": cfg["label"]}})

    def _norm_scores(vals: List[float]) -> List[float]:
        logs = [math.log1p(max(0.0, v)) for v in vals]
        min_log = min(logs)
        max_log = max(logs)
        if max_log == min_log:
            return [60.0 for _ in vals]
        return [round((x - min_log) / (max_log - min_log) * 100.0, 2) for x in logs]

    heat_norm = _norm_scores([x[1] for x in province_heat])
    risk_norm = _norm_scores([x[2] for x in province_heat])

    data = []
    for (province, heat, _risk_raw, event_count, attack_ratio), h_val, r_val in zip(province_heat, heat_norm, risk_norm):
        data.append(
            {
                "name": province,
                # 兼容旧前端默认读取 value
                "value": r_val,
                "heat_value": h_val,
                "risk_value": r_val,
                "event_count": int(event_count),
                "heat_score": round(heat, 2),
                "attack_ratio": round(attack_ratio * 100.0, 2),
            }
        )

    total_events = int(sum(x[3] for x in province_heat))
    peak_heat = max(data, key=lambda x: x["heat_value"], default=None)
    peak_risk = max(data, key=lambda x: x["risk_value"], default=None)
    payload = {
        "success": True,
        "data": data,
        "meta": {
            "platform": platform,
            "platform_label": cfg["label"],
            "summary": {
                "total_events": total_events,
                "province_count": len(data),
                "high_risk_provinces": sum(1 for x in data if x["risk_value"] >= 80),
                "peak_heat_province": peak_heat["name"] if peak_heat else "",
                "peak_risk_province": peak_risk["name"] if peak_risk else "",
            },
        },
    }
    _cache_set("heatmap-china", payload)
    return jsonify(payload)


@mvp_bp.route("/api/topic-comments")
def api_topic_comments():
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    topic_name = (request.args.get("topic_name") or "").strip()
    if not topic_name:
        return jsonify({"success": False, "message": "topic_name 不能为空"}), 400
    start_d, end_d = _parse_date_range()
    page = max(1, int(request.args.get("page", 1) or 1))
    page_size = max(1, min(100, int(request.args.get("page_size", 20) or 20)))
    offset = (page - 1) * page_size

    where = [
        f"{cfg['note_time_expr']} BETWEEN %s AND %s",
        f"{cfg['topic_expr']} = %s",
    ]
    params: List = [start_d, end_d, topic_name]
    where_sql = " AND ".join(where)

    count_sql = f"""
        SELECT COUNT(1)
        FROM {cfg['comment_table']} c
        JOIN {cfg['note_table']} n ON c.{cfg['join_key']} = n.{cfg['join_key']}
        WHERE {where_sql}
    """
    data_sql = f"""
        SELECT
            {cfg['comment_time_fmt']} AS create_time,
            {cfg['comment_content_expr']} AS content,
            {cfg['comment_nickname_expr']} AS nickname,
            {cfg['comment_like_expr']} AS like_count
        FROM {cfg['comment_table']} c
        JOIN {cfg['note_table']} n ON c.{cfg['join_key']} = n.{cfg['join_key']}
        WHERE {where_sql}
        ORDER BY {cfg['comment_like_expr']} DESC
        LIMIT %s OFFSET %s
    """

    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = int(cur.fetchone()[0] or 0)
            cur.execute(data_sql, params + [page_size, offset])
            rows = cur.fetchall()

    data = [
        {
            "create_time": r[0],
            "content": r[1],
            "nickname": r[2],
            "like_count": int(r[3] or 0),
        }
        for r in rows
    ]
    total_pages = max(1, math.ceil(total / page_size))
    return jsonify(
        {
            "success": True,
            "data": data,
            "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages},
            "meta": {"platform": platform, "topic_name": topic_name},
        }
    )


@mvp_bp.route("/api/platform-distribution")
def api_platform_distribution():
    cached = _cache_get("platform-distribution")
    if cached is not None:
        return jsonify(cached)
    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    topic_like = f"%{topic}%"
    data = []
    with _db_conn() as conn:
        with conn.cursor() as cur:
            for platform, cfg in PLATFORM_CONFIG.items():
                where = [f"{cfg['note_time_expr']} BETWEEN %s AND %s"]
                params: List = [start_d, end_d]
                if topic:
                    where.append(
                        f"({cfg['topic_expr']} LIKE %s OR {cfg['content_expr']} LIKE %s OR COALESCE(n.source_keyword, '') LIKE %s)"
                    )
                    params.extend([topic_like, topic_like, topic_like])
                _apply_theme_filters(where, params)
                where_sql = " AND ".join(where)
                sql = f"SELECT COUNT(1) FROM {cfg['note_table']} n WHERE {where_sql}"
                cur.execute(sql, params)
                cnt = int(cur.fetchone()[0] or 0)
                data.append({"name": cfg["label"], "value": cnt, "platform": platform})
    payload = {"success": True, "data": data}
    _cache_set("platform-distribution", payload)
    return jsonify(payload)


@mvp_bp.route("/api/wordcloud")
def api_wordcloud():
    cached = _cache_get("wordcloud")
    if cached is not None:
        return jsonify(cached)
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    top_n = max(20, min(200, int(request.args.get("top_n", 80) or 80)))

    where = [f"{cfg['note_time_expr']} BETWEEN %s AND %s"]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
    _apply_theme_filters(where, params)
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT {cfg['content_expr']} AS text_col
        FROM {cfg['note_table']} n
        WHERE {where_sql}
        LIMIT 3000
    """

    token_counter: Dict[str, int] = defaultdict(int)
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    for (txt,) in rows:
        text = (txt or "").strip()
        if not text:
            continue
        for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", text):
            if token in STOPWORDS:
                continue
            if len(token) < 2:
                continue
            token_counter[token] += 1

    wc = sorted(token_counter.items(), key=lambda x: x[1], reverse=True)[:top_n]
    data = [{"name": k, "value": v} for k, v in wc]
    payload = {"success": True, "data": data, "meta": {"platform": platform, "platform_label": cfg["label"]}}
    _cache_set("wordcloud", payload)
    return jsonify(payload)


@mvp_bp.route("/api/topic-options")
def api_topic_options():
    cached = _cache_get("topic-options")
    if cached is not None:
        return jsonify(cached)
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    theme = (request.args.get("theme") or "").strip()
    sub_theme = (request.args.get("sub_theme") or "").strip()

    where = [f"{cfg['note_time_expr']} BETWEEN %s AND %s"]
    params: List = [start_d, end_d]
    if theme:
        where.append("COALESCE(n.lang_theme, '') = %s")
        params.append(theme)
    if sub_theme:
        where.append("COALESCE(n.lang_sub_theme, '') = %s")
        params.append(sub_theme)
    where_sql = " AND ".join(where)

    sql_theme = f"""
        SELECT COALESCE(n.lang_theme, '') AS v, COUNT(1) AS c
        FROM {cfg['note_table']} n
        WHERE {where_sql} AND COALESCE(n.lang_theme, '') <> ''
        GROUP BY v
        ORDER BY c DESC
        LIMIT 100
    """
    sql_sub = f"""
        SELECT COALESCE(n.lang_sub_theme, '') AS v, COUNT(1) AS c
        FROM {cfg['note_table']} n
        WHERE {where_sql} AND COALESCE(n.lang_sub_theme, '') <> ''
        GROUP BY v
        ORDER BY c DESC
        LIMIT 200
    """
    sql_topic = f"""
        SELECT {cfg['topic_expr']} AS v, COUNT(1) AS c
        FROM {cfg['note_table']} n
        WHERE {where_sql} AND {cfg['topic_expr']} <> ''
        GROUP BY v
        ORDER BY c DESC
        LIMIT 300
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_theme, params)
            themes = [r[0] for r in cur.fetchall() if r[0]]
            cur.execute(sql_sub, params)
            sub_themes = [r[0] for r in cur.fetchall() if r[0]]
            cur.execute(sql_topic, params)
            topics = [r[0] for r in cur.fetchall() if r[0]]

    payload = {
        "success": True,
        "data": {"themes": themes, "sub_themes": sub_themes, "topics": topics},
        "meta": {"platform": platform, "platform_label": cfg["label"]},
    }
    _cache_set("topic-options", payload)
    return jsonify(payload)


@mvp_bp.route("/api/province-detail")
def api_province_detail():
    cached = _cache_get("province-detail")
    if cached is not None:
        return jsonify(cached)

    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    province = (request.args.get("province") or "").strip()
    if not province:
        return jsonify({"success": False, "message": "province 不能为空"}), 400

    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    where = [f"{cfg['note_time_expr']} BETWEEN %s AND %s"]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
    _apply_theme_filters(where, params)
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            {cfg['note_ip_expr']} AS ip_location,
            {cfg['topic_expr']} AS topic_name,
            {cfg['content_expr']} AS content_text,
            {cfg['nickname_expr']} AS nickname,
            {cfg['note_time_fmt']} AS create_time,
            ({cfg['liked_expr']} + {cfg['comments_expr']} + {cfg['shared_expr']}) AS heat_score
        FROM {cfg['note_table']} n
        WHERE {where_sql}
        ORDER BY n.id DESC
        LIMIT 1200
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    topic_stats: Dict[str, Dict] = {}
    recent_events: List[Dict] = []
    for ip_location, topic_name, content_text, nickname, create_time, heat_score in rows:
        p = _province_from_ip(ip_location)
        if p != province:
            continue
        tname = (topic_name or "未分类").strip() or "未分类"
        hs = float(heat_score or 0.0)
        st = topic_stats.setdefault(tname, {"topic_name": tname, "heat_sum": 0.0, "event_count": 0})
        st["heat_sum"] += hs
        st["event_count"] += 1
        if len(recent_events) < 80:
            recent_events.append(
                {
                    "topic_name": tname,
                    "content": str(content_text or ""),
                    "nickname": nickname or "",
                    "create_time": create_time,
                    "heat_score": round(hs, 2),
                }
            )

    topic_items = []
    for st in topic_stats.values():
        ri = _risk_index_from_heat(st["heat_sum"])
        topic_items.append(
            {
                "topic_name": st["topic_name"],
                "event_count": int(st["event_count"]),
                "heat_score": round(st["heat_sum"], 2),
                "risk_index": ri,
            }
        )
    topic_items.sort(key=lambda x: x["risk_index"], reverse=True)

    recent_events.sort(key=lambda x: x["heat_score"], reverse=True)
    payload = {
        "success": True,
        "data": {
            "province": province,
            "top_topics": topic_items[:8],
            "recent_events": recent_events[:6],
        },
        "meta": {"platform": platform, "platform_label": cfg["label"]},
    }
    _cache_set("province-detail", payload)
    return jsonify(payload)


@mvp_bp.route("/api/risk-matrix")
def api_risk_matrix():
    cached = _cache_get("risk-matrix")
    if cached is not None:
        return jsonify(cached)
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    theme = (request.args.get("theme") or "").strip()
    sub_theme = (request.args.get("sub_theme") or "").strip()
    max_topics = max(10, min(300, int(request.args.get("max_topics", 120) or 120)))
    max_comments_per_topic = max(10, min(200, int(request.args.get("max_comments_per_topic", 80) or 80)))
    max_rows = max(500, min(50000, int(request.args.get("max_rows", 10000) or 10000)))
    reports = _topic_ri_reports(cfg, start_d, end_d, topic, max_topics, max_comments_per_topic, max_rows, theme, sub_theme)

    if not reports:
        payload = {
            "success": True,
            "data": {"bubbles": [], "risk_distribution": [], "top_risky_topics": []},
            "meta": {"platform": platform, "platform_label": cfg["label"]},
        }
        _cache_set("risk-matrix", payload)
        return jsonify(payload)

    heat_vals = [x["weighted_ri"] for x in reports]
    vel_vals = [x["velocity_raw"] for x in reports]
    min_h, max_h = min(heat_vals), max(heat_vals)
    min_v, max_v = min(vel_vals), max(vel_vals)

    level_counter = defaultdict(int)
    bubbles = []
    for r in reports:
        if max_h == min_h:
            heat_norm = 60.0
        else:
            heat_norm = (r["weighted_ri"] - min_h) / (max_h - min_h) * 100.0

        if max_v == min_v:
            velocity_score = 35.0
        else:
            velocity_score = (r["velocity_raw"] - min_v) / (max_v - min_v) * 100.0

        malicious_score = min(100.0, round((r["attack_ratio"] * 100.0) * 0.7 + (r["avg_ri"] * 0.3), 2))
        ri = float(r["topic_ri"])
        level = _risk_level(ri)
        level_counter[level] += 1
        bubbles.append(
            {
                "topic_name": r["topic_name"],
                "velocity_score": round(velocity_score, 2),
                "malicious_score": round(malicious_score, 2),
                "heat_norm": round(heat_norm, 2),
                "ri_score": ri,
                "note_count": r["comment_count"],
                "risk_level": level,
                "danger_ratio": r["danger_ratio"],
                "attack_ratio": r["attack_ratio"],
            }
        )

    bubbles.sort(key=lambda x: x["ri_score"], reverse=True)
    risk_distribution = [{"name": k, "value": v} for k, v in level_counter.items()]
    top_risky_topics = bubbles[:10]
    payload = {
        "success": True,
        "data": {
            "bubbles": bubbles,
            "risk_distribution": risk_distribution,
            "top_risky_topics": top_risky_topics,
        },
        "meta": {"platform": platform, "platform_label": cfg["label"]},
    }
    _cache_set("risk-matrix", payload)
    return jsonify(payload)


def _suggestion_by_topic_risk(topic_ri: float, attack_ratio: float) -> str:
    if topic_ri >= 70 or attack_ratio >= 0.2:
        return "立即触发高优先级处置：人工复核、平台举报、关键词限流与澄清联动。"
    if topic_ri >= 55:
        return "进入重点关注池：6小时滚动复测，准备统一回应口径与辟谣素材。"
    if topic_ri >= 40:
        return "保持监测：每日追踪波动，必要时做轻量引导与评论区秩序维护。"
    return "常态监测：无需专项处置，保留事件记录用于后续对比分析。"


@mvp_bp.route("/api/event-chain")
def api_event_chain():
    cached = _cache_get("event-chain")
    if cached is not None:
        return jsonify(cached)
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    topic_name = (request.args.get("topic_name") or "").strip()
    theme = (request.args.get("theme") or "").strip()
    sub_theme = (request.args.get("sub_theme") or "").strip()
    reports = _topic_ri_reports(
        cfg=cfg,
        start_d=start_d,
        end_d=end_d,
        topic=topic_name,
        max_topics=25,
        max_comments_per_topic=120,
        max_rows=12000,
        theme=theme,
        sub_theme=sub_theme,
    )
    # 若用户输入话题但未召回，回退到全局高风险池再做近似匹配
    if topic_name and not reports:
        reports = _topic_ri_reports(
            cfg=cfg,
            start_d=start_d,
            end_d=end_d,
            topic="",
            max_topics=80,
            max_comments_per_topic=120,
            max_rows=20000,
            theme=theme,
            sub_theme=sub_theme,
        )
    if not reports:
        return jsonify({"success": False, "message": "未找到对应话题数据"}), 404

    # 主题选择：exact > 包含匹配 > 相似度匹配 > 全局最高风险
    target = None
    if topic_name:
        for r in reports:
            if r["topic_name"] == topic_name:
                target = r
                break
        if target is None:
            for r in reports:
                tname = str(r.get("topic_name") or "")
                if topic_name in tname or tname in topic_name:
                    target = r
                    break
        if target is None:
            ranked = sorted(
                reports,
                key=lambda x: SequenceMatcher(None, topic_name, str(x.get("topic_name") or "")).ratio(),
                reverse=True,
            )
            if ranked:
                target = ranked[0]
    if target is None:
        target = reports[0]

    suggestion = _suggestion_by_topic_risk(float(target["topic_ri"]), float(target["attack_ratio"]))
    chain_nodes = [
        {"name": "原始评论", "value": int(target["comment_count"])},
        {"name": "情感强度", "value": round(float(target["avg_ri"]), 2)},
        {"name": "攻击占比", "value": round(float(target["attack_ratio"]) * 100.0, 2)},
        {"name": "话题RI", "value": round(float(target["topic_ri"]), 2)},
        {"name": "响应建议", "value": suggestion},
    ]
    payload = {
        "success": True,
        "data": {
            "topic": target["topic_name"],
            "platform": platform,
            "topic_ri": target["topic_ri"],
            "weighted_ri": target["weighted_ri"],
            "avg_ri": target["avg_ri"],
            "danger_ratio": target["danger_ratio"],
            "attack_ratio": target["attack_ratio"],
            "context_ratio": target.get("context_ratio", 0.0),
            "comment_count": target["comment_count"],
            "chain_nodes": chain_nodes,
            "top_comments": target["top_comments"],
            "suggestion": suggestion,
            "candidate_topics": [
                {
                    "topic_name": x["topic_name"],
                    "topic_ri": x["topic_ri"],
                    "comment_count": x["comment_count"],
                }
                for x in reports[:8]
            ],
        },
        "meta": {"platform_label": cfg["label"]},
    }
    _cache_set("event-chain", payload)
    return jsonify(payload)


@mvp_bp.route("/api/response-board")
def api_response_board():
    cached = _cache_get("response-board")
    if cached is not None:
        return jsonify(cached)
    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    theme = (request.args.get("theme") or "").strip()
    sub_theme = (request.args.get("sub_theme") or "").strip()
    top_n = max(5, min(80, int(request.args.get("top_n", 30) or 30)))

    platform = (request.args.get("platform") or "").strip().lower()
    platform_items = (
        [(platform, PLATFORM_CONFIG[platform])] if platform in PLATFORM_CONFIG else list(PLATFORM_CONFIG.items())
    )
    rows: List[Dict] = []
    for platform_key, cfg in platform_items:
        reports = _topic_ri_reports(
            cfg=cfg,
            start_d=start_d,
            end_d=end_d,
            topic=topic,
            max_topics=12,
            max_comments_per_topic=25,
            max_rows=2000,
            theme=theme,
            sub_theme=sub_theme,
        )
        for r in reports:
            tri = float(r["topic_ri"])
            rows.append(
                {
                    "platform": platform_key,
                    "platform_label": cfg["label"],
                    "topic_name": r["topic_name"],
                    "topic_ri": round(tri, 2),
                    "attack_ratio": r["attack_ratio"],
                    "danger_ratio": r["danger_ratio"],
                    "comment_count": r["comment_count"],
                    "status": "待定",
                    "measure": _suggestion_by_topic_risk(tri, float(r["attack_ratio"])),
                    "effect_drop": 0.0,
                }
            )

    rows.sort(key=lambda x: (x["topic_ri"], x["danger_ratio"], x["comment_count"]), reverse=True)
    rows = rows[:top_n]

    # 分层状态（演示友好）：避免出现“全部已执行”
    n = len(rows)
    pending_cut = max(1, math.ceil(n * 0.25))
    processing_cut = max(pending_cut + 1, math.ceil(n * 0.60))
    for idx, r in enumerate(rows):
        tri = float(r["topic_ri"])
        attack = float(r["attack_ratio"])
        if tri >= 65 or idx < pending_cut:
            status = "待处理"
            effect_drop = max(0.0, min(8.0, (100.0 - tri) * 0.05))
        elif tri >= 45 or idx < processing_cut:
            status = "处理中"
            effect_drop = max(6.0, min(28.0, 10.0 + (1 - attack) * 8.0 + (55.0 - tri) * 0.12))
        else:
            status = "已执行"
            effect_drop = max(18.0, min(60.0, 30.0 + (1 - attack) * 12.0 + (45.0 - tri) * 0.22))
        r["status"] = status
        r["effect_drop"] = round(effect_drop, 1)

    status_counter: Dict[str, int] = defaultdict(int)
    for r in rows:
        status_counter[r["status"]] += 1

    payload = {
        "success": True,
        "data": {
            "items": rows,
            "status_distribution": [{"name": k, "value": v} for k, v in status_counter.items()],
        },
    }
    _cache_set("response-board", payload)
    return jsonify(payload)

