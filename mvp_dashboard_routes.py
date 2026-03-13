from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple

import pymysql
from flask import Blueprint, jsonify, render_template, request

from config import settings


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
    return min(100.0, round(math.log1p(heat) * 18, 2))


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


@mvp_bp.route("/")
def hot_ranking_page():
    return render_template("mvp/hot_ranking.html", page_key="hot")


@mvp_bp.route("/trend")
def trend_page():
    return render_template("mvp/trend.html", page_key="trend")


@mvp_bp.route("/heatmap")
def heatmap_page():
    return render_template("mvp/heatmap.html", page_key="heatmap")


@mvp_bp.route("/api/hot-events")
def api_hot_events():
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
        items.append(
            {
                "id": r[0],
                "topic_name": r[1],
                "content": r[2],
                "nickname": r[3],
                "create_time": r[4],
                "liked_count": int(r[5] or 0),
                "comments_count": int(r[6] or 0),
                "shared_count": int(r[7] or 0),
                "risk_index": _risk_index_from_heat(heat),
                "platform": platform,
            }
        )

    total_pages = max(1, math.ceil(total / page_size))
    return jsonify(
        {
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
    )


@mvp_bp.route("/api/ranking")
def api_ranking():
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
    return jsonify({"success": True, "data": data, "meta": {"platform": platform, "platform_label": cfg["label"]}})


@mvp_bp.route("/api/trend-30d")
def api_trend_30d():
    topic = (request.args.get("topic") or "").strip()
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    where = [
        f"{cfg['note_time_expr']} BETWEEN %s AND %s",
    ]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
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

    dates: List[str] = []
    topic_counts: List[int] = []
    risk_index: List[float] = []
    cur_d = start_d
    while cur_d <= end_d:
        key = cur_d.isoformat()
        cnt, avg_heat = day_map.get(key, (0, 0.0))
        dates.append(key)
        topic_counts.append(cnt)
        risk_index.append(_risk_index_from_heat(avg_heat))
        cur_d += timedelta(days=1)

    return jsonify(
        {
            "success": True,
            "data": {
                "dates": dates,
                "topic_counts": topic_counts,
                "risk_index": risk_index,
            },
            "meta": {"platform": platform, "platform_label": cfg["label"]},
        }
    )


@mvp_bp.route("/api/heatmap-china")
def api_heatmap_china():
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    where = [f"{cfg['note_time_expr']} BETWEEN %s AND %s"]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            {cfg['note_ip_expr']} AS ip_location,
            ({cfg['liked_expr']} + {cfg['comments_expr']} + {cfg['shared_expr']}) AS heat_score
        FROM {cfg['note_table']} n
        WHERE {where_sql}
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    agg = defaultdict(lambda: {"event_count": 0, "like_sum": 0})
    for ip_location, heat_score in rows:
        province = _province_from_ip(ip_location)
        if not province:
            continue
        agg[province]["event_count"] += 1
        agg[province]["like_sum"] += int(heat_score or 0)

    # Fallback for platforms where note-level ip_location is often empty:
    # use comment-level IP to recover regional distribution.
    if not agg:
        comment_sql = f"""
            SELECT
                {cfg['comment_ip_expr']} AS ip_location,
                {cfg['comment_like_expr']} AS like_score
            FROM {cfg['comment_table']} c
            JOIN {cfg['note_table']} n ON c.{cfg['join_key']} = n.{cfg['join_key']}
            WHERE {where_sql}
        """
        with _db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(comment_sql, params)
                c_rows = cur.fetchall()
        for ip_location, like_score in c_rows:
            province = _province_from_ip(ip_location)
            if not province:
                continue
            agg[province]["event_count"] += 1
            agg[province]["like_sum"] += int(like_score or 0)

    province_heat = []
    for province, st in agg.items():
        heat = float(st["event_count"] * 3 + st["like_sum"])
        province_heat.append((province, heat, st["event_count"]))

    if not province_heat:
        return jsonify({"success": True, "data": [], "meta": {"platform": platform, "platform_label": cfg["label"]}})

    logs = [math.log1p(h) for _, h, _ in province_heat]
    min_log = min(logs)
    max_log = max(logs)

    data = []
    for province, heat, event_count in province_heat:
        if max_log == min_log:
            score = 60.0
        else:
            score = round((math.log1p(heat) - min_log) / (max_log - min_log) * 100.0, 2)
        data.append(
            {
                "name": province,
                "value": score,
                "event_count": int(event_count),
                "heat_score": round(heat, 2),
            }
        )

    return jsonify({"success": True, "data": data, "meta": {"platform": platform, "platform_label": cfg["label"]}})


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
                where_sql = " AND ".join(where)
                sql = f"SELECT COUNT(1) FROM {cfg['note_table']} n WHERE {where_sql}"
                cur.execute(sql, params)
                cnt = int(cur.fetchone()[0] or 0)
                data.append({"name": cfg["label"], "value": cnt, "platform": platform})
    return jsonify({"success": True, "data": data})


@mvp_bp.route("/api/wordcloud")
def api_wordcloud():
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    top_n = max(20, min(200, int(request.args.get("top_n", 80) or 80)))

    where = [f"{cfg['note_time_expr']} BETWEEN %s AND %s"]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
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
    return jsonify({"success": True, "data": data, "meta": {"platform": platform, "platform_label": cfg["label"]}})


@mvp_bp.route("/api/risk-matrix")
def api_risk_matrix():
    platform = _platform_key()
    cfg = PLATFORM_CONFIG[platform]
    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    max_topics = max(10, min(300, int(request.args.get("max_topics", 120) or 120)))

    where = [f"{cfg['note_time_expr']} BETWEEN %s AND %s"]
    params: List = [start_d, end_d]
    _topic_filter_sql(cfg, topic, where, params)
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            {cfg['topic_expr']} AS topic_name,
            {cfg['content_expr']} AS content,
            {cfg['note_time_expr']} AS note_day,
            {cfg['liked_expr']} AS liked_count,
            {cfg['comments_expr']} AS comments_count,
            {cfg['shared_expr']} AS shared_count
        FROM {cfg['note_table']} n
        WHERE {where_sql}
        ORDER BY n.id DESC
        LIMIT 5000
    """

    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    if not rows:
        return jsonify(
            {
                "success": True,
                "data": {"bubbles": [], "risk_distribution": [], "top_risky_topics": []},
                "meta": {"platform": platform, "platform_label": cfg["label"]},
            }
        )

    attack_tokens = {
        "造谣",
        "谣言",
        "网暴",
        "辱骂",
        "攻击",
        "恶意",
        "诽谤",
        "人肉",
        "曝光",
        "封杀",
        "抵制",
        "冲塔",
        "煽动",
        "仇恨",
        "歧视",
    }

    stats: Dict[str, Dict] = defaultdict(
        lambda: {"note_count": 0, "heat_sum": 0.0, "comment_sum": 0.0, "daily": defaultdict(int), "attack_hits": 0}
    )

    for topic_name, content, note_day, liked_count, comments_count, shared_count in rows:
        t = (topic_name or "未分类").strip() or "未分类"
        heat = float(liked_count or 0) + float(comments_count or 0) + float(shared_count or 0)
        st = stats[t]
        st["note_count"] += 1
        st["heat_sum"] += heat
        st["comment_sum"] += float(comments_count or 0)
        st["daily"][str(note_day)] += 1
        txt = (content or "").lower()
        st["attack_hits"] += sum(1 for tk in attack_tokens if tk in txt)

    topic_rows = []
    for topic_name, st in stats.items():
        counts = list(st["daily"].values()) or [0]
        max_cnt = max(counts)
        min_cnt = min(counts)
        mean_cnt = sum(counts) / max(1, len(counts))
        velocity_raw = (max_cnt - min_cnt) / max(1.0, mean_cnt)
        attack_density = st["attack_hits"] / max(1.0, st["note_count"])
        malicious_score = min(100.0, round(attack_density * 40 + min(30.0, st["comment_sum"] / max(1.0, st["note_count"])), 2))
        topic_rows.append(
            {
                "topic_name": topic_name,
                "note_count": int(st["note_count"]),
                "heat_sum": float(st["heat_sum"]),
                "velocity_raw": float(velocity_raw),
                "malicious_score": float(malicious_score),
            }
        )

    topic_rows.sort(key=lambda x: x["heat_sum"], reverse=True)
    topic_rows = topic_rows[:max_topics]

    heat_logs = [math.log1p(x["heat_sum"]) for x in topic_rows]
    min_h, max_h = min(heat_logs), max(heat_logs)
    vel_list = [x["velocity_raw"] for x in topic_rows]
    min_v, max_v = min(vel_list), max(vel_list)

    level_counter = defaultdict(int)
    bubbles = []
    for r in topic_rows:
        h_log = math.log1p(r["heat_sum"])
        if max_h == min_h:
            heat_norm = 60.0
        else:
            heat_norm = (h_log - min_h) / (max_h - min_h) * 100.0

        if max_v == min_v:
            velocity_score = 35.0
        else:
            velocity_score = (r["velocity_raw"] - min_v) / (max_v - min_v) * 100.0

        ri = round(0.3 * heat_norm + 0.5 * r["malicious_score"] + 0.2 * velocity_score, 2)
        level = _risk_level(ri)
        level_counter[level] += 1
        bubbles.append(
            {
                "topic_name": r["topic_name"],
                "velocity_score": round(velocity_score, 2),
                "malicious_score": round(r["malicious_score"], 2),
                "heat_norm": round(heat_norm, 2),
                "ri_score": ri,
                "note_count": r["note_count"],
                "risk_level": level,
            }
        )

    bubbles.sort(key=lambda x: x["ri_score"], reverse=True)
    risk_distribution = [{"name": k, "value": v} for k, v in level_counter.items()]
    top_risky_topics = bubbles[:10]
    return jsonify(
        {
            "success": True,
            "data": {
                "bubbles": bubbles,
                "risk_distribution": risk_distribution,
                "top_risky_topics": top_risky_topics,
            },
            "meta": {"platform": platform, "platform_label": cfg["label"]},
        }
    )

