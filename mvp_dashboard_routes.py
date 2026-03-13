from __future__ import annotations

import math
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


def _risk_index_from_heat(heat: float) -> float:
    if heat <= 0:
        return 0.0
    return min(100.0, round(math.log1p(heat) * 18, 2))


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
    page = max(1, int(request.args.get("page", 1) or 1))
    page_size = max(1, min(50, int(request.args.get("page_size", 10) or 10)))
    start_d, end_d = _parse_date_range()
    offset = (page - 1) * page_size

    topic_like = f"%{topic}%"
    where = [
        "DATE(FROM_UNIXTIME(create_time + 28800)) BETWEEN %s AND %s",
    ]
    params: List = [start_d, end_d]
    if topic:
        where.append("(source_keyword LIKE %s OR corpus_topic LIKE %s OR content LIKE %s)")
        params.extend([topic_like, topic_like, topic_like])
    where_sql = " AND ".join(where)

    count_sql = f"SELECT COUNT(1) FROM weibo_note WHERE {where_sql}"
    data_sql = f"""
        SELECT
            id,
            COALESCE(corpus_topic, source_keyword, '未分类') AS topic_name,
            COALESCE(content, '') AS content,
            COALESCE(nickname, '') AS nickname,
            DATE_FORMAT(FROM_UNIXTIME(create_time + 28800), '%%Y-%%m-%%d %%H:%%i:%%s') AS create_time,
            CAST(COALESCE(liked_count, '0') AS UNSIGNED) AS liked_count,
            CAST(COALESCE(comments_count, '0') AS UNSIGNED) AS comments_count,
            CAST(COALESCE(shared_count, '0') AS UNSIGNED) AS shared_count
        FROM weibo_note
        WHERE {where_sql}
        ORDER BY create_time DESC, id DESC
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
        }
    )


@mvp_bp.route("/api/ranking")
def api_ranking():
    topic = (request.args.get("topic") or "").strip()
    top_n = max(1, min(50, int(request.args.get("top_n", 10) or 10)))
    start_d, end_d = _parse_date_range()
    topic_like = f"%{topic}%"
    where = [
        "DATE(FROM_UNIXTIME(create_time + 28800)) BETWEEN %s AND %s",
    ]
    params: List = [start_d, end_d]
    if topic:
        where.append("(source_keyword LIKE %s OR corpus_topic LIKE %s OR content LIKE %s)")
        params.extend([topic_like, topic_like, topic_like])
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            COALESCE(corpus_topic, source_keyword, '未分类') AS topic_name,
            COALESCE(nickname, '') AS nickname,
            DATE_FORMAT(FROM_UNIXTIME(create_time + 28800), '%%Y-%%m-%%d %%H:%%i:%%s') AS create_time,
            CAST(COALESCE(liked_count, '0') AS UNSIGNED) AS liked_count,
            CAST(COALESCE(comments_count, '0') AS UNSIGNED) AS comments_count,
            CAST(COALESCE(shared_count, '0') AS UNSIGNED) AS shared_count
        FROM weibo_note
        WHERE {where_sql}
        ORDER BY (CAST(COALESCE(liked_count, '0') AS UNSIGNED)
                + CAST(COALESCE(comments_count, '0') AS UNSIGNED)
                + CAST(COALESCE(shared_count, '0') AS UNSIGNED)) DESC
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
            }
        )
    return jsonify({"success": True, "data": data})


@mvp_bp.route("/api/trend-30d")
def api_trend_30d():
    topic = (request.args.get("topic") or "").strip()
    start_d, end_d = _parse_date_range()
    topic_like = f"%{topic}%"
    where = [
        "DATE(FROM_UNIXTIME(create_time + 28800)) BETWEEN %s AND %s",
    ]
    params: List = [start_d, end_d]
    if topic:
        where.append("(source_keyword LIKE %s OR corpus_topic LIKE %s OR content LIKE %s)")
        params.extend([topic_like, topic_like, topic_like])
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT
            DATE(FROM_UNIXTIME(create_time + 28800)) AS d,
            COUNT(1) AS cnt,
            AVG(
                CAST(COALESCE(liked_count, '0') AS UNSIGNED)
                + CAST(COALESCE(comments_count, '0') AS UNSIGNED)
                + CAST(COALESCE(shared_count, '0') AS UNSIGNED)
            ) AS avg_heat
        FROM weibo_note
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
        }
    )


@mvp_bp.route("/api/heatmap-china")
def api_heatmap_china():
    start_d, end_d = _parse_date_range()
    topic = (request.args.get("topic") or "").strip()
    topic_like = f"%{topic}%"
    where = [
        "DATE(FROM_UNIXTIME(c.create_time + 28800)) BETWEEN %s AND %s",
    ]
    params: List = [start_d, end_d]
    if topic:
        where.append("(n.source_keyword LIKE %s OR n.corpus_topic LIKE %s OR n.content LIKE %s)")
        params.extend([topic_like, topic_like, topic_like])
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            COALESCE(c.ip_location, '') AS ip_location,
            CAST(COALESCE(c.comment_like_count, '0') AS UNSIGNED) AS comment_like_count
        FROM weibo_note_comment c
        JOIN weibo_note n ON c.note_id = n.note_id
        WHERE {where_sql}
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    agg = defaultdict(lambda: {"event_count": 0, "like_sum": 0})
    for ip_location, like_count in rows:
        province = _province_from_ip(ip_location)
        if not province:
            continue
        agg[province]["event_count"] += 1
        agg[province]["like_sum"] += int(like_count or 0)

    data = []
    for province, st in agg.items():
        heat = st["event_count"] * 3 + st["like_sum"]
        data.append(
            {
                "name": province,
                "value": _risk_index_from_heat(float(heat)),
                "event_count": st["event_count"],
            }
        )

    return jsonify({"success": True, "data": data})

