"""
RI 风险驾驶舱（独立页面）

本页面聚焦“话题风险”，不使用地理维度。
核心图表：
1) 风险矩阵气泡图（传播速度 vs 恶意程度）
2) 风险等级分布
3) 高风险话题趋势
4) 高风险排行榜 + 评论归属链路样例
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import pymysql
import streamlit as st
import streamlit.components.v1 as components


RI_ALPHA = 0.3
RI_BETA = 0.5
RI_GAMMA = 0.2

NEGATIVE_WORDS = {"谣言", "造谣", "攻击", "网暴", "辱骂", "对立", "曝光", "黑幕", "封杀", "恶心", "崩溃", "歧视"}
POSITIVE_WORDS = {"支持", "理性", "客观", "澄清", "认可", "理解", "建设性", "积极", "感谢", "文明"}
HIGH_RISK_WORDS = {"人肉", "开盒", "网暴", "去死", "杀", "诽谤", "曝光住址", "骚扰", "威胁"}
MEDIUM_RISK_WORDS = {"造谣", "抹黑", "煽动", "带节奏", "攻击", "辱骂", "歧视"}
PROVINCE_ALIASES = {
    "北京": "北京", "天津": "天津", "上海": "上海", "重庆": "重庆", "河北": "河北", "山西": "山西",
    "辽宁": "辽宁", "吉林": "吉林", "黑龙江": "黑龙江", "江苏": "江苏", "浙江": "浙江", "安徽": "安徽",
    "福建": "福建", "江西": "江西", "山东": "山东", "河南": "河南", "湖北": "湖北", "湖南": "湖南",
    "广东": "广东", "海南": "海南", "四川": "四川", "贵州": "贵州", "云南": "云南", "陕西": "陕西",
    "甘肃": "甘肃", "青海": "青海", "台湾": "台湾", "内蒙古": "内蒙古", "广西": "广西", "西藏": "西藏",
    "宁夏": "宁夏", "新疆": "新疆", "香港": "香港", "澳门": "澳门",
}

PLATFORM_CONFIG = {
    "微博": {
        "time_unit": "sec",
        "sql": """
            SELECT '微博' AS platform,
                   COALESCE(n.source_keyword, '') AS topic,
                   CAST(n.note_id AS CHAR) AS note_key,
                   COALESCE(CAST(n.liked_count AS UNSIGNED), 0) AS note_like_count,
                   COALESCE(CAST(n.comments_count AS UNSIGNED), 0) AS note_comment_count,
                   COALESCE(CAST(n.shared_count AS UNSIGNED), 0) AS note_share_count,
                   n.create_time AS note_time,
                   c.create_time AS comment_time,
                   c.ip_location AS ip_location,
                   c.content AS comment_content
            FROM weibo_note n
            JOIN weibo_note_comment c ON n.note_id = c.note_id
            WHERE n.source_keyword IS NOT NULL
              AND n.source_keyword <> ''
              AND c.create_time BETWEEN %s AND %s
            LIMIT %s
        """,
    },
    "抖音": {
        "time_unit": "sec",
        "sql": """
            SELECT '抖音' AS platform,
                   COALESCE(n.source_keyword, '') AS topic,
                   CAST(n.aweme_id AS CHAR) AS note_key,
                   COALESCE(CAST(n.liked_count AS UNSIGNED), 0) AS note_like_count,
                   COALESCE(CAST(n.comment_count AS UNSIGNED), 0) AS note_comment_count,
                   COALESCE(CAST(n.share_count AS UNSIGNED), 0) AS note_share_count,
                   n.create_time AS note_time,
                   c.create_time AS comment_time,
                   c.ip_location AS ip_location,
                   c.content AS comment_content
            FROM douyin_aweme n
            JOIN douyin_aweme_comment c ON n.aweme_id = c.aweme_id
            WHERE n.source_keyword IS NOT NULL
              AND n.source_keyword <> ''
              AND c.create_time BETWEEN %s AND %s
            LIMIT %s
        """,
    },
    "小红书": {
        "time_unit": "ms",
        "sql": """
            SELECT '小红书' AS platform,
                   COALESCE(n.source_keyword, '') AS topic,
                   CAST(n.note_id AS CHAR) AS note_key,
                   COALESCE(CAST(n.liked_count AS UNSIGNED), 0) AS note_like_count,
                   COALESCE(CAST(n.comment_count AS UNSIGNED), 0) AS note_comment_count,
                   COALESCE(CAST(n.share_count AS UNSIGNED), 0) AS note_share_count,
                   n.time AS note_time,
                   c.create_time AS comment_time,
                   c.ip_location AS ip_location,
                   c.content AS comment_content
            FROM xhs_note n
            JOIN xhs_note_comment c ON n.note_id = c.note_id
            WHERE n.source_keyword IS NOT NULL
              AND n.source_keyword <> ''
              AND c.create_time BETWEEN %s AND %s
            LIMIT %s
        """,
    },
    "知乎": {
        "time_unit": "sec",
        "sql": """
            SELECT '知乎' AS platform,
                   COALESCE(n.source_keyword, '') AS topic,
                   CAST(n.content_id AS CHAR) AS note_key,
                   COALESCE(CAST(n.voteup_count AS UNSIGNED), 0) AS note_like_count,
                   COALESCE(CAST(n.comment_count AS UNSIGNED), 0) AS note_comment_count,
                   0 AS note_share_count,
                   COALESCE(CAST(n.created_time AS UNSIGNED), 0) AS note_time,
                   COALESCE(CAST(c.publish_time AS UNSIGNED), 0) AS comment_time,
                   c.ip_location AS ip_location,
                   c.content AS comment_content
            FROM zhihu_content n
            JOIN zhihu_comment c ON n.content_id = c.content_id
            WHERE n.source_keyword IS NOT NULL
              AND n.source_keyword <> ''
              AND CAST(c.publish_time AS UNSIGNED) BETWEEN %s AND %s
            LIMIT %s
        """,
    },
}


def load_env(path: str = ".env") -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.split("#", 1)[0].strip()
    return env


def get_connection(env: Dict[str, str]):
    return pymysql.connect(
        host=env.get("DB_HOST", "localhost"),
        port=int(env.get("DB_PORT", "3306")),
        user=env.get("DB_USER", "root"),
        password=env.get("DB_PASSWORD", ""),
        database=env.get("DB_NAME", "bettafish"),
        charset=env.get("DB_CHARSET", "utf8mb4"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def normalize_to_0_1(values: List[float], use_log: bool = False) -> List[float]:
    if not values:
        return []
    source: List[float] = []
    for v in values:
        x = max(float(v), 0.0)
        source.append(math.log(x + 1.0) if use_log else x)
    min_v, max_v = min(source), max(source)
    if max_v - min_v < 1e-9:
        return [0.5 for _ in source]
    return [(v - min_v) / (max_v - min_v) for v in source]


def sentiment_score_simple(text: str) -> float:
    text = (text or "").strip()
    if not text:
        return 0.55
    neg_hits = sum(1 for w in NEGATIVE_WORDS if w in text)
    pos_hits = sum(1 for w in POSITIVE_WORDS if w in text)
    return min(1.0, max(0.0, 0.55 + 0.08 * pos_hits - 0.1 * neg_hits))


def attack_factor(text: str) -> float:
    text = (text or "").strip()
    if any(w in text for w in HIGH_RISK_WORDS):
        return 2.0
    if any(w in text for w in MEDIUM_RISK_WORDS):
        return 1.5
    return 1.0


def risk_level(ri_score: float) -> str:
    if ri_score >= 80:
        return "危险(Level1)"
    if ri_score >= 60:
        return "警告(Level2)"
    if ri_score >= 40:
        return "关注(Level3)"
    return "安全(Level4)"


def normalize_ip_location(raw_value: str) -> Optional[str]:
    if not raw_value:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    text = text.replace("IP属地", "").replace("属地", "").replace("来自", "")
    text = text.replace("省", "").replace("市", "").replace("自治区", "")
    text = text.replace("壮族", "").replace("回族", "").replace("维吾尔", "")
    text = text.replace("特别行政区", "").strip(" :：")
    for k, v in PROVINCE_ALIASES.items():
        if text.startswith(k):
            return v
    return None


def build_region_risk_map_html(map_data: List[Dict], title: str) -> str:
    max_value = max([d["value"] for d in map_data], default=100)
    option = {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "item", "formatter": "{b}<br/>地区风险指数: {c}"},
        "visualMap": {
            "type": "piecewise",
            "left": "left",
            "bottom": 20,
            "pieces": [
                {"min": 80, "label": "高危(>=80)", "color": "#cf1322"},
                {"min": 60, "max": 79.99, "label": "警告(60-80)", "color": "#ff7875"},
                {"min": 40, "max": 59.99, "label": "关注(40-60)", "color": "#ffe58f"},
                {"min": 0, "max": 39.99, "label": "安全(<40)", "color": "#b7eb8f"},
            ],
        },
        "series": [{"name": "地区风险", "type": "map", "map": "china", "roam": True, "data": map_data}],
    }
    chart_id = f"ri_map_{int(datetime.now().timestamp() * 1000)}"
    return f"""
<div id="{chart_id}" style="width:100%;height:650px;"></div>
<script src="https://cdn.jsdelivr.net/npm/echarts@4/dist/echarts.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@4/map/js/china.js"></script>
<script>
const chart = echarts.init(document.getElementById('{chart_id}'));
const option = {json.dumps(option, ensure_ascii=False)};
chart.setOption(option);
window.addEventListener('resize', () => chart.resize());
</script>
"""


def fetch_risk_rows(
    conn,
    selected_platforms: List[str],
    start_date: date,
    end_date: date,
    limit_per_platform: int,
) -> List[Dict]:
    rows: List[Dict] = []
    start_sec = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    end_sec = int(datetime.combine(end_date + timedelta(days=1), datetime.min.time()).timestamp()) - 1
    start_ms = start_sec * 1000
    end_ms = end_sec * 1000

    with conn.cursor() as cursor:
        for platform in selected_platforms:
            cfg = PLATFORM_CONFIG[platform]
            if cfg["time_unit"] == "ms":
                cursor.execute(cfg["sql"], (start_ms, end_ms, limit_per_platform))
            else:
                cursor.execute(cfg["sql"], (start_sec, end_sec, limit_per_platform))
            rows.extend(cursor.fetchall())
    return rows


def compute_topic_risk(rows: List[Dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df[(df["topic"].notna()) & (df["topic"].astype(str).str.strip() != "")].copy()
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    for c in ["note_like_count", "note_comment_count", "note_share_count", "note_time", "comment_time"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["comment_content"] = df["comment_content"].fillna("").astype(str)
    df["topic"] = df["topic"].astype(str).str.strip()
    df["note_key"] = df["note_key"].astype(str)
    df["heat"] = df["note_like_count"] + df["note_comment_count"] + df["note_share_count"]
    df["sentiment"] = df["comment_content"].apply(sentiment_score_simple)
    df["impact_factor"] = df["comment_content"].apply(attack_factor)
    df["malice"] = (1 - df["sentiment"]) * df["impact_factor"]

    # 统一时间（秒或毫秒）
    c_ms_mask = df["comment_time"] > 1_000_000_000_000
    n_ms_mask = df["note_time"] > 1_000_000_000_000
    df.loc[c_ms_mask, "comment_time"] = df.loc[c_ms_mask, "comment_time"] / 1000
    df.loc[n_ms_mask, "note_time"] = df.loc[n_ms_mask, "note_time"] / 1000
    df["comment_dt"] = pd.to_datetime(df["comment_time"], unit="s", errors="coerce")
    df["comment_date"] = df["comment_dt"].dt.date
    df["province"] = df["ip_location"].fillna("").apply(normalize_ip_location)

    note_df = (
        df.groupby(["platform", "topic", "note_key"], as_index=False)
        .agg(
            heat=("heat", "max"),
            S_score=("sentiment", "mean"),
            I_impact=("impact_factor", "mean"),
            malice=("malice", "mean"),
            comment_count=("comment_content", "count"),
            note_time=("note_time", "max"),
        )
    )

    velocity_map = {}
    for key, g in df.groupby(["platform", "topic", "note_key"]):
        by_day = g.groupby("comment_date").size().sort_index()
        if len(by_day) < 2:
            velocity_map[key] = 0.0
        else:
            days = max((by_day.index[-1] - by_day.index[0]).days, 1)
            velocity_map[key] = max(float(by_day.iloc[-1] - by_day.iloc[0]) / days, 0.0)
    note_df["velocity_raw"] = note_df.apply(
        lambda r: velocity_map.get((r["platform"], r["topic"], r["note_key"]), 0.0), axis=1
    )

    note_df["H_norm"] = normalize_to_0_1(note_df["heat"].tolist(), use_log=True)
    note_df["V_velocity"] = normalize_to_0_1(note_df["velocity_raw"].tolist(), use_log=False)
    note_df["ri_0_1"] = (
        RI_ALPHA * note_df["H_norm"]
        + RI_BETA * (1 - note_df["S_score"]) * note_df["I_impact"]
        + RI_GAMMA * note_df["V_velocity"]
    ).clip(lower=0.0, upper=1.0)
    note_df["ri_score"] = (note_df["ri_0_1"] * 100).round(2)
    note_df["note_date"] = pd.to_datetime(note_df["note_time"], unit="s", errors="coerce").dt.date

    topic_df = (
        note_df.groupby(["platform", "topic"], as_index=False)
        .agg(
            RI=("ri_score", "mean"),
            热度=("heat", "sum"),
            传播速度=("V_velocity", "mean"),
            恶意度=("malice", "mean"),
            帖子数=("note_key", "nunique"),
            评论数=("comment_count", "sum"),
        )
    )
    topic_df["RI"] = topic_df["RI"].round(2)
    topic_df["传播速度分"] = (topic_df["传播速度"] * 100).round(2)
    topic_df["恶意度分"] = (topic_df["恶意度"].clip(0, 2) * 50).round(2)
    topic_df["风险等级"] = topic_df["RI"].apply(risk_level)
    topic_df["气泡大小"] = topic_df["热度"].apply(lambda x: max(10, min(80, int(math.sqrt(max(x, 1)) * 0.6))))
    return topic_df.sort_values("RI", ascending=False), note_df


def compute_region_risk(rows: List[Dict], note_df: pd.DataFrame) -> pd.DataFrame:
    if not rows or note_df.empty:
        return pd.DataFrame()
    comments_df = pd.DataFrame(rows).copy()
    comments_df["topic"] = comments_df["topic"].astype(str).str.strip()
    comments_df["note_key"] = comments_df["note_key"].astype(str)
    comments_df["province"] = comments_df["ip_location"].fillna("").apply(normalize_ip_location)
    comments_df = comments_df[comments_df["province"].notna()].copy()
    if comments_df.empty:
        return pd.DataFrame()

    note_key_df = note_df[["platform", "topic", "note_key", "ri_score"]].copy()
    note_key_df["topic"] = note_key_df["topic"].astype(str).str.strip()
    note_key_df["note_key"] = note_key_df["note_key"].astype(str)
    merged = comments_df.merge(note_key_df, on=["platform", "topic", "note_key"], how="left")
    merged["ri_score"] = pd.to_numeric(merged["ri_score"], errors="coerce").fillna(0.0)

    agg = (
        merged.groupby("province", as_index=False)
        .agg(comment_count=("note_key", "count"), region_ri=("ri_score", "mean"))
        .sort_values("region_ri", ascending=False)
    )
    count_norm = normalize_to_0_1(agg["comment_count"].astype(float).tolist(), use_log=True)
    agg["coverage_factor"] = [v * 100 for v in count_norm]
    agg["region_risk_score"] = (0.7 * agg["region_ri"] + 0.3 * agg["coverage_factor"]).round(2)
    return agg


def build_region_risk_detail(rows: List[Dict], note_df: pd.DataFrame) -> pd.DataFrame:
    if not rows or note_df.empty:
        return pd.DataFrame()
    comments_df = pd.DataFrame(rows).copy()
    comments_df["topic"] = comments_df["topic"].astype(str).str.strip()
    comments_df["note_key"] = comments_df["note_key"].astype(str)
    comments_df["province"] = comments_df["ip_location"].fillna("").apply(normalize_ip_location)
    comments_df["comment_time"] = pd.to_numeric(comments_df["comment_time"], errors="coerce").fillna(0)
    ms_mask = comments_df["comment_time"] > 1_000_000_000_000
    comments_df.loc[ms_mask, "comment_time"] = comments_df.loc[ms_mask, "comment_time"] / 1000
    comments_df["comment_date"] = pd.to_datetime(comments_df["comment_time"], unit="s", errors="coerce").dt.date
    comments_df = comments_df[comments_df["province"].notna()].copy()
    if comments_df.empty:
        return pd.DataFrame()

    note_key_df = note_df[["platform", "topic", "note_key", "ri_score"]].copy()
    note_key_df["topic"] = note_key_df["topic"].astype(str).str.strip()
    note_key_df["note_key"] = note_key_df["note_key"].astype(str)
    merged = comments_df.merge(note_key_df, on=["platform", "topic", "note_key"], how="left")
    merged["ri_score"] = pd.to_numeric(merged["ri_score"], errors="coerce").fillna(0.0)
    return merged


def main():
    st.set_page_config(page_title="RI 风险驾驶舱", layout="wide")
    st.title("RI 风险驾驶舱")
    st.caption("画面一：全国语情风险热力图 + 高危事件Top10 + 风险变化趋势。")

    env = load_env()
    if not env:
        st.error("未读取到 .env，无法连接数据库。")
        return

    today = date.today()
    start_default = today - timedelta(days=6)
    date_range = st.date_input(
        "分析时间范围",
        value=(start_default, today),
        min_value=today - timedelta(days=90),
        max_value=today,
    )
    if not isinstance(date_range, tuple) or len(date_range) != 2:
        st.warning("请完整选择日期范围。")
        return
    start_date, end_date = date_range

    platform_options = list(PLATFORM_CONFIG.keys())
    selected_platforms = st.multiselect("平台选择", platform_options, default=platform_options)
    limit_per_platform = st.slider("每个平台最大评论样本", 5000, 120000, 50000, 5000)
    if not selected_platforms:
        st.warning("至少选择一个平台。")
        return

    with get_connection(env) as conn:
        rows = fetch_risk_rows(conn, selected_platforms, start_date, end_date, limit_per_platform)

    if not rows:
        st.warning("当前筛选条件无可用评论数据。")
        return

    topic_df, note_df = compute_topic_risk(rows)
    if topic_df.empty:
        st.warning("未计算出有效 RI 数据。")
        return
    region_detail_df = build_region_risk_detail(rows, note_df)
    region_df = compute_region_risk(rows, note_df)

    theme_options = sorted(topic_df["topic"].dropna().astype(str).unique().tolist())
    selected_themes = st.multiselect("主题筛选（可多选）", options=theme_options, default=[])

    province_options = sorted(region_detail_df["province"].dropna().astype(str).unique().tolist()) if not region_detail_df.empty else []
    selected_provinces = st.multiselect("省份筛选（可多选）", options=province_options, default=[])

    filtered_topic_df = topic_df.copy()
    filtered_detail_df = region_detail_df.copy()
    if selected_themes:
        filtered_topic_df = filtered_topic_df[filtered_topic_df["topic"].isin(selected_themes)].copy()
        if not filtered_detail_df.empty:
            filtered_detail_df = filtered_detail_df[filtered_detail_df["topic"].isin(selected_themes)].copy()
    if selected_provinces and not filtered_detail_df.empty:
        filtered_detail_df = filtered_detail_df[filtered_detail_df["province"].isin(selected_provinces)].copy()
        allowed_topic_keys = set(zip(filtered_detail_df["platform"], filtered_detail_df["topic"]))
        filtered_topic_df = filtered_topic_df[
            filtered_topic_df.apply(lambda r: (r["platform"], r["topic"]) in allowed_topic_keys, axis=1)
        ].copy()

    if filtered_topic_df.empty:
        st.warning("筛选后无可用风险数据，请调整主题/省份筛选条件。")
        return

    filtered_region_df = pd.DataFrame()
    if not filtered_detail_df.empty:
        filtered_region_df = (
            filtered_detail_df.groupby("province", as_index=False)
            .agg(comment_count=("note_key", "count"), region_ri=("ri_score", "mean"))
            .sort_values("region_ri", ascending=False)
        )
        count_norm = normalize_to_0_1(filtered_region_df["comment_count"].astype(float).tolist(), use_log=True)
        filtered_region_df["coverage_factor"] = [v * 100 for v in count_norm]
        filtered_region_df["region_risk_score"] = (
            0.7 * filtered_region_df["region_ri"] + 0.3 * filtered_region_df["coverage_factor"]
        ).round(2)

    # 风险事件数量与变化趋势
    trend_notes = note_df.copy()
    trend_notes["topic"] = trend_notes["topic"].astype(str)
    if selected_themes:
        trend_notes = trend_notes[trend_notes["topic"].isin(selected_themes)].copy()
    if selected_provinces and not filtered_detail_df.empty:
        allowed_notes = set(filtered_detail_df["note_key"].astype(str).unique().tolist())
        trend_notes = trend_notes[trend_notes["note_key"].astype(str).isin(allowed_notes)].copy()
    daily_risk = (
        trend_notes.groupby("note_date", as_index=False)
        .agg(
            high_risk_count=("ri_score", lambda s: int((s >= 80).sum())),
            warning_count=("ri_score", lambda s: int(((s >= 60) & (s < 80)).sum())),
            attention_count=("ri_score", lambda s: int(((s >= 40) & (s < 60)).sum())),
            total_notes=("ri_score", "count"),
        )
        .sort_values("note_date")
    )

    current_high_risk = int((filtered_topic_df["RI"] >= 80).sum())
    current_warning = int(((filtered_topic_df["RI"] >= 60) & (filtered_topic_df["RI"] < 80)).sum())
    current_attention = int(((filtered_topic_df["RI"] >= 40) & (filtered_topic_df["RI"] < 60)).sum())

    delta_high = None
    if len(daily_risk) >= 2:
        delta_high = int(daily_risk.iloc[-1]["high_risk_count"] - daily_risk.iloc[-2]["high_risk_count"])

    a, b, c = st.columns(3)
    a.metric("高危事件数 (RI>=80)", f"{current_high_risk}", delta=None if delta_high is None else delta_high)
    b.metric("警告事件数 (60<=RI<80)", f"{current_warning}")
    c.metric("关注事件数 (40<=RI<60)", f"{current_attention}")

    st.subheader("画面一：全国语情风险热力图")
    if filtered_region_df.empty:
        st.info("当前筛选条件下缺少可识别地区数据。")
    else:
        map_data = [
            {"name": r["province"], "value": float(r["region_risk_score"])}
            for _, r in filtered_region_df.iterrows()
        ]
        map_title = "全国语情风险分布（可按平台/主题/省份筛选）"
        components.html(build_region_risk_map_html(map_data, map_title), height=680, scrolling=False)

    r1, r2 = st.columns([3, 2])
    with r1:
        st.subheader("风险事件数量趋势")
        if daily_risk.empty:
            st.caption("暂无趋势数据。")
        else:
            trend_plot = daily_risk.melt(
                id_vars=["note_date"],
                value_vars=["high_risk_count", "warning_count", "attention_count"],
                var_name="risk_type",
                value_name="count",
            )
            fig_trend = px.line(
                trend_plot,
                x="note_date",
                y="count",
                color="risk_type",
                markers=True,
                title="高危/警告/关注 事件数量变化",
                height=360,
            )
            st.plotly_chart(fig_trend, use_container_width=True)
    with r2:
        st.subheader("高危事件排行榜 Top10")
        top10 = filtered_topic_df.sort_values("RI", ascending=False).head(10).copy()
        top10.insert(0, "排名", range(1, len(top10) + 1))
        st.dataframe(
            top10[["排名", "platform", "topic", "RI", "风险等级", "热度", "评论数"]],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("风险矩阵气泡图")
    st.caption("横轴=传播速度分，纵轴=恶意度分，气泡大小=热度，颜色=RI。")
    fig_matrix = px.scatter(
        filtered_topic_df,
        x="传播速度分",
        y="恶意度分",
        size="气泡大小",
        color="RI",
        hover_name="topic",
        hover_data=["platform", "热度", "帖子数", "评论数", "风险等级"],
        color_continuous_scale="OrRd",
        height=560,
    )
    fig_matrix.add_hline(y=50, line_dash="dot")
    fig_matrix.add_vline(x=50, line_dash="dot")
    st.plotly_chart(fig_matrix, use_container_width=True)

    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("高风险话题趋势（Top5）")
        top_topics = filtered_topic_df.sort_values("RI", ascending=False).head(5)[["platform", "topic"]]
        top_set = {(r["platform"], r["topic"]) for _, r in top_topics.iterrows()}
        trend_df = note_df[note_df.apply(lambda r: (r["platform"], r["topic"]) in top_set, axis=1)].copy()
        trend_df["主题"] = trend_df["platform"] + " | " + trend_df["topic"]
        trend_group = trend_df.groupby(["note_date", "主题"], as_index=False)["ri_score"].mean()
        fig_line = px.line(
            trend_group,
            x="note_date",
            y="ri_score",
            color="主题",
            markers=True,
            title="Top5 话题 RI 日趋势",
            height=420,
        )
        fig_line.update_layout(yaxis_title="RI", xaxis_title="日期")
        st.plotly_chart(fig_line, use_container_width=True)

    with col2:
        st.subheader("风险等级分布")
        dist = filtered_topic_df["风险等级"].value_counts().reset_index()
        dist.columns = ["风险等级", "话题数"]
        fig_bar = px.bar(dist, x="风险等级", y="话题数", color="风险等级", height=420)
        st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("高风险排行榜")
    rank_df = filtered_topic_df.sort_values("RI", ascending=False).head(30).copy()
    rank_df.insert(0, "排名", range(1, len(rank_df) + 1))
    st.dataframe(
        rank_df[["排名", "platform", "topic", "RI", "风险等级", "热度", "帖子数", "评论数", "传播速度分", "恶意度分"]],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("评论归属链路样例（评论 -> 帖子 -> 话题）", expanded=False):
        sample = pd.DataFrame(rows).copy().head(20)
        sample.rename(
            columns={
                "platform": "平台",
                "topic": "话题",
                "note_key": "帖子ID",
                "comment_time": "评论时间",
                "comment_content": "评论内容",
            },
            inplace=True,
        )
        st.dataframe(sample[["平台", "话题", "帖子ID", "评论时间", "评论内容"]], use_container_width=True, hide_index=True)
        st.caption("映射规则：`comment表` 通过 `note_id/aweme_id` 关联 `note表`，再由 `source_keyword/topic_id` 归属到话题。")

    st.subheader("地区风险地图（RI 视角）")
    st.caption("这不是热度地图，而是地区内评论所关联话题的风险强度聚合，适合识别“定向攻击区域”。")
    display_region_df = filtered_region_df if not filtered_region_df.empty else region_df
    if display_region_df.empty:
        st.info("当前筛选下缺少可识别地区的评论数据。")
    else:
        map_data = [{"name": r["province"], "value": float(r["region_risk_score"])} for _, r in display_region_df.iterrows()]
        components.html(build_region_risk_map_html(map_data, "全国地区风险指数分布"), height=680, scrolling=False)
        st.dataframe(
            display_region_df.rename(
                columns={
                    "province": "地区",
                    "comment_count": "评论数",
                    "region_ri": "平均RI",
                    "coverage_factor": "覆盖因子",
                    "region_risk_score": "地区风险指数",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()

