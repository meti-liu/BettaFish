"""
语情热点地理分布演示页（中国地图）

功能:
1) 连接本地 bettafish MySQL
2) 按平台读取 Top 话题
3) 按话题聚合评论 IP 属地热度
4) 使用 streamlit-echarts 渲染中国热力地图
"""

from __future__ import annotations

import os
import re
import json
import uuid
import math
from collections import Counter
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import jieba
import pandas as pd
import plotly.express as px
import pymysql
import streamlit as st
import streamlit.components.v1 as components
from wordcloud import WordCloud


PROVINCE_ALIASES: Dict[str, str] = {
    "北京": "北京",
    "天津": "天津",
    "上海": "上海",
    "重庆": "重庆",
    "河北": "河北",
    "山西": "山西",
    "辽宁": "辽宁",
    "吉林": "吉林",
    "黑龙江": "黑龙江",
    "江苏": "江苏",
    "浙江": "浙江",
    "安徽": "安徽",
    "福建": "福建",
    "江西": "江西",
    "山东": "山东",
    "河南": "河南",
    "湖北": "湖北",
    "湖南": "湖南",
    "广东": "广东",
    "海南": "海南",
    "四川": "四川",
    "贵州": "贵州",
    "云南": "云南",
    "陕西": "陕西",
    "甘肃": "甘肃",
    "青海": "青海",
    "台湾": "台湾",
    "内蒙古": "内蒙古",
    "广西": "广西",
    "西藏": "西藏",
    "宁夏": "宁夏",
    "新疆": "新疆",
    "香港": "香港",
    "澳门": "澳门",
}

REGION_GROUPS: Dict[str, List[str]] = {
    "东北": ["辽宁", "吉林", "黑龙江"],
    "华北": ["北京", "天津", "河北", "山西", "内蒙古"],
    "华东": ["上海", "江苏", "浙江", "安徽", "福建", "江西", "山东"],
    "华中": ["河南", "湖北", "湖南"],
    "华南": ["广东", "广西", "海南", "香港", "澳门"],
    "西南": ["重庆", "四川", "贵州", "云南", "西藏"],
    "西北": ["陕西", "甘肃", "青海", "宁夏", "新疆"],
    "台港澳": ["台湾", "香港", "澳门"],
}

PLATFORM_SQL = {
    "微博": {
        "topic_sql": """
            SELECT source_keyword, COUNT(*) AS cnt
            FROM weibo_note
            WHERE source_keyword IS NOT NULL AND source_keyword <> ''
            GROUP BY source_keyword
            ORDER BY cnt DESC
            LIMIT %s
        """,
        "heat_sql": """
            SELECT n.source_keyword AS topic,
                   n.note_id AS note_key,
                   c.ip_location AS ip_location,
                   COALESCE(CAST(c.comment_like_count AS UNSIGNED), 0) AS likes,
                   COALESCE(CAST(n.liked_count AS UNSIGNED), 0) AS note_like_count,
                   COALESCE(CAST(n.comments_count AS UNSIGNED), 0) AS note_comment_count,
                   COALESCE(CAST(n.shared_count AS UNSIGNED), 0) AS note_share_count,
                   n.create_time AS note_time,
                   c.create_time AS comment_time,
                   c.content AS comment_content
            FROM weibo_note n
            JOIN weibo_note_comment c ON n.note_id = c.note_id
            WHERE n.source_keyword = %s
              AND c.ip_location IS NOT NULL
              AND c.ip_location <> ''
            LIMIT 50000
        """,
    },
    "抖音": {
        "topic_sql": """
            SELECT source_keyword, COUNT(*) AS cnt
            FROM douyin_aweme
            WHERE source_keyword IS NOT NULL AND source_keyword <> ''
            GROUP BY source_keyword
            ORDER BY cnt DESC
            LIMIT %s
        """,
        "heat_sql": """
            SELECT n.source_keyword AS topic,
                   n.aweme_id AS note_key,
                   c.ip_location AS ip_location,
                   COALESCE(CAST(c.like_count AS UNSIGNED), 0) AS likes,
                   COALESCE(CAST(n.liked_count AS UNSIGNED), 0) AS note_like_count,
                   COALESCE(CAST(n.comment_count AS UNSIGNED), 0) AS note_comment_count,
                   COALESCE(CAST(n.share_count AS UNSIGNED), 0) AS note_share_count,
                   n.create_time AS note_time,
                   c.create_time AS comment_time,
                   c.content AS comment_content
            FROM douyin_aweme n
            JOIN douyin_aweme_comment c ON n.aweme_id = c.aweme_id
            WHERE n.source_keyword = %s
              AND c.ip_location IS NOT NULL
              AND c.ip_location <> ''
            LIMIT 50000
        """,
    },
    "小红书": {
        "topic_sql": """
            SELECT source_keyword, COUNT(*) AS cnt
            FROM xhs_note
            WHERE source_keyword IS NOT NULL AND source_keyword <> ''
            GROUP BY source_keyword
            ORDER BY cnt DESC
            LIMIT %s
        """,
        "heat_sql": """
            SELECT n.source_keyword AS topic,
                   n.note_id AS note_key,
                   c.ip_location AS ip_location,
                   COALESCE(CAST(c.like_count AS UNSIGNED), 0) AS likes,
                   COALESCE(CAST(n.liked_count AS UNSIGNED), 0) AS note_like_count,
                   COALESCE(CAST(n.comment_count AS UNSIGNED), 0) AS note_comment_count,
                   COALESCE(CAST(n.share_count AS UNSIGNED), 0) AS note_share_count,
                   n.time AS note_time,
                   c.create_time AS comment_time,
                   c.content AS comment_content
            FROM xhs_note n
            JOIN xhs_note_comment c ON n.note_id = c.note_id
            WHERE n.source_keyword = %s
              AND c.ip_location IS NOT NULL
              AND c.ip_location <> ''
            LIMIT 50000
        """,
    },
    "知乎": {
        "topic_sql": """
            SELECT source_keyword, COUNT(*) AS cnt
            FROM zhihu_content
            WHERE source_keyword IS NOT NULL AND source_keyword <> ''
            GROUP BY source_keyword
            ORDER BY cnt DESC
            LIMIT %s
        """,
        "heat_sql": """
            SELECT n.source_keyword AS topic,
                   n.content_id AS note_key,
                   c.ip_location AS ip_location,
                   COALESCE(CAST(c.like_count AS UNSIGNED), 0) AS likes,
                   COALESCE(CAST(n.voteup_count AS UNSIGNED), 0) AS note_like_count,
                   COALESCE(CAST(n.comment_count AS UNSIGNED), 0) AS note_comment_count,
                   0 AS note_share_count,
                   CAST(n.created_time AS UNSIGNED) AS note_time,
                   CAST(c.publish_time AS UNSIGNED) AS comment_time,
                   c.content AS comment_content
            FROM zhihu_content n
            JOIN zhihu_comment c ON n.content_id = c.content_id
            WHERE n.source_keyword = %s
              AND c.ip_location IS NOT NULL
              AND c.ip_location <> ''
            LIMIT 50000
        """,
    },
}


WORDCLOUD_STOPWORDS = {
    "今天",
    "最新",
    "相关",
    "消息",
    "官方",
    "我们",
    "你们",
    "这个",
    "那个",
    "进行",
    "已经",
    "一个",
    "可以",
    "如何",
    "什么",
    "还是",
    "就是",
    "因为",
    "没有",
    "不是",
    "以及",
    "发布",
}

RI_ALPHA = 0.3
RI_BETA = 0.5
RI_GAMMA = 0.2

NEGATIVE_WORDS = {"谣言", "造谣", "攻击", "网暴", "辱骂", "对立", "曝光", "黑幕", "封杀", "恶心", "崩溃", "歧视"}
POSITIVE_WORDS = {"支持", "理性", "客观", "澄清", "认可", "理解", "建设性", "积极", "感谢", "文明"}
HIGH_RISK_WORDS = {"人肉", "开盒", "网暴", "去死", "杀", "诽谤", "曝光住址", "骚扰", "威胁"}
MEDIUM_RISK_WORDS = {"造谣", "抹黑", "煽动", "带节奏", "攻击", "辱骂", "歧视"}


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
            # 兼容 value 里的行内注释
            value = value.split("#", 1)[0].strip()
            env[key.strip()] = value
    return env


def normalize_ip_location(raw_value: str) -> Optional[str]:
    if not raw_value:
        return None
    text = str(raw_value).strip()
    if not text:
        return None

    text = re.sub(r"^(IP属地|属地|来自)[:：\s]*", "", text)
    text = text.replace("省", "").replace("市", "").replace("自治区", "")
    text = text.replace("壮族", "").replace("回族", "").replace("维吾尔", "")
    text = text.replace("特别行政区", "")
    text = text.strip()

    for k, v in PROVINCE_ALIASES.items():
        if text.startswith(k):
            return v
    return None


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


def fetch_top_topics(conn, platform: str, limit: int = 10) -> List[Tuple[str, int]]:
    sql = PLATFORM_SQL[platform]["topic_sql"]
    with conn.cursor() as cursor:
        cursor.execute(sql, (limit,))
        rows = cursor.fetchall()
    return [(r["source_keyword"], int(r["cnt"])) for r in rows if r["source_keyword"]]


def fetch_topic_heatmap_data(conn, platform: str, topic: str) -> Tuple[List[Dict], Dict]:
    sql = PLATFORM_SQL[platform]["heat_sql"]
    with conn.cursor() as cursor:
        cursor.execute(sql, (topic,))
        rows = cursor.fetchall()

    province_comment_count: Dict[str, int] = {}
    province_like_score: Dict[str, int] = {}

    for row in rows:
        province = normalize_ip_location(row.get("ip_location", ""))
        if not province:
            continue
        likes = int(row.get("likes") or 0)
        province_comment_count[province] = province_comment_count.get(province, 0) + 1
        province_like_score[province] = province_like_score.get(province, 0) + likes

    # 地图用的分值：评论量 + 点赞权重(压缩)
    map_data: List[Dict] = []
    for province, comment_count in province_comment_count.items():
        weighted = comment_count + int((province_like_score.get(province, 0) ** 0.5) * 0.8)
        map_data.append({"name": province, "value": weighted})

    # 区域汇总（帮助验证“东北高”“沿海高”）
    region_totals: Dict[str, int] = {}
    province_score = {d["name"]: int(d["value"]) for d in map_data}
    for region, provinces in REGION_GROUPS.items():
        region_totals[region] = sum(province_score.get(p, 0) for p in provinces)

    map_data.sort(key=lambda x: x["value"], reverse=True)
    return map_data, region_totals


def safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_to_0_1(values: List[float], use_log: bool = False) -> List[float]:
    if not values:
        return []
    source = []
    for v in values:
        x = max(float(v), 0.0)
        source.append((x + 1.0) if use_log else x)
    if use_log:
        source = [math.log(v) for v in source]
    min_v = min(source)
    max_v = max(source)
    if max_v - min_v < 1e-9:
        return [0.5 for _ in source]
    return [(v - min_v) / (max_v - min_v) for v in source]


def sentiment_score_simple(text: str) -> float:
    text = (text or "").strip()
    if not text:
        return 0.55
    neg_hits = sum(1 for w in NEGATIVE_WORDS if w in text)
    pos_hits = sum(1 for w in POSITIVE_WORDS if w in text)
    raw = 0.55 + 0.08 * pos_hits - 0.1 * neg_hits
    return min(1.0, max(0.0, raw))


def attack_factor(text: str) -> float:
    text = (text or "").strip()
    if any(w in text for w in HIGH_RISK_WORDS):
        return 2.0
    if any(w in text for w in MEDIUM_RISK_WORDS):
        return 1.5
    return 1.0


def risk_level(ri_score: float) -> str:
    if ri_score >= 80:
        return "🔴 危险 (Level 1)"
    if ri_score >= 60:
        return "🟠 警告 (Level 2)"
    if ri_score >= 40:
        return "🟡 关注 (Level 3)"
    return "🟢 安全 (Level 4)"


def compute_topic_ri(rows: List[Dict]) -> Tuple[float, str, pd.DataFrame]:
    if not rows:
        return 0.0, risk_level(0.0), pd.DataFrame()

    row_df = pd.DataFrame(rows)
    row_df["note_key"] = row_df["note_key"].astype(str)
    row_df["note_heat"] = (
        row_df["note_like_count"].apply(safe_int)
        + row_df["note_comment_count"].apply(safe_int)
        + row_df["note_share_count"].apply(safe_int)
    )
    row_df["comment_time"] = pd.to_numeric(row_df["comment_time"], errors="coerce").fillna(0)
    row_df["sentiment"] = row_df["comment_content"].fillna("").apply(sentiment_score_simple)
    row_df["impact_factor"] = row_df["comment_content"].fillna("").apply(attack_factor)
    row_df["comment_date"] = pd.to_datetime(row_df["comment_time"], unit="s", errors="coerce").dt.date

    grouped = (
        row_df.groupby("note_key", as_index=False)
        .agg(
            heat=("note_heat", "max"),
            sentiment=("sentiment", "mean"),
            impact_factor=("impact_factor", "mean"),
            comment_count=("comment_content", "count"),
            note_time=("note_time", "max"),
        )
    )

    # 传播速度：按天评论增长率（首尾差/天数）
    velocity_map: Dict[str, float] = {}
    for note_key, g in row_df.groupby("note_key"):
        by_day = g.groupby("comment_date").size().sort_index()
        if len(by_day) < 2:
            velocity_map[note_key] = 0.0
            continue
        days = max((by_day.index[-1] - by_day.index[0]).days, 1)
        velocity_map[note_key] = max(float(by_day.iloc[-1] - by_day.iloc[0]) / days, 0.0)
    grouped["velocity_raw"] = grouped["note_key"].map(velocity_map).fillna(0.0)

    grouped["H_norm"] = normalize_to_0_1(grouped["heat"].tolist(), use_log=True)
    grouped["V_velocity"] = normalize_to_0_1(grouped["velocity_raw"].tolist(), use_log=False)
    grouped["ri_0_1"] = (
        RI_ALPHA * grouped["H_norm"]
        + RI_BETA * (1 - grouped["sentiment"]) * grouped["impact_factor"]
        + RI_GAMMA * grouped["V_velocity"]
    ).clip(lower=0.0, upper=1.0)
    grouped["ri_score"] = (grouped["ri_0_1"] * 100).round(2)
    grouped["risk_level"] = grouped["ri_score"].apply(risk_level)

    topic_ri = float(grouped["ri_score"].mean()) if not grouped.empty else 0.0
    return topic_ri, risk_level(topic_ri), grouped.sort_values("ri_score", ascending=False)


def build_map_html(topic: str, platform: str, map_data: List[Dict]) -> str:
    max_value = max([d["value"] for d in map_data], default=10)
    chart_id = f"map_{uuid.uuid4().hex}"
    option = {
        "title": {
            "text": f"{platform} - {topic} 话题热度地图",
            "subtext": "热度 = 评论数量 + 点赞加权",
            "left": "center",
        },
        "tooltip": {"trigger": "item", "formatter": "{b}<br/>热度值: {c}"},
        "visualMap": {
            "min": 0,
            "max": max_value,
            "left": "left",
            "bottom": 20,
            "text": ["高", "低"],
            "calculable": True,
            "inRange": {"color": ["#e8f7ff", "#91d5ff", "#40a9ff", "#0050b3"]},
        },
        "series": [
            {
                "name": "话题热度",
                "type": "map",
                "map": "china",
                "roam": True,
                "zoom": 1.15,
                "label": {"show": False},
                "emphasis": {"label": {"show": True}},
                "data": map_data,
            }
        ],
    }

    return f"""
<div id="{chart_id}" style="width:100%;height:700px;"></div>
<script src="https://cdn.jsdelivr.net/npm/echarts@4/dist/echarts.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@4/map/js/china.js"></script>
<script>
  const chart = echarts.init(document.getElementById('{chart_id}'));
  const option = {json.dumps(option, ensure_ascii=False)};
  chart.setOption(option);
  window.addEventListener('resize', () => chart.resize());
</script>
"""


def fetch_daily_news(
    conn,
    start_date: date,
    end_date: date,
    platforms: Optional[List[str]] = None,
    limit: int = 5000,
) -> List[Dict]:
    where_parts = ["crawl_date >= %s", "crawl_date <= %s"]
    params: List = [start_date, end_date]
    if platforms:
        placeholders = ",".join(["%s"] * len(platforms))
        where_parts.append(f"source_platform IN ({placeholders})")
        params.extend(platforms)

    query = f"""
        SELECT id, news_id, source_platform, title, url, description, crawl_date, rank_position
        FROM daily_news
        WHERE {' AND '.join(where_parts)}
        ORDER BY crawl_date DESC, rank_position ASC
        LIMIT %s
    """
    params.append(limit)
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        return cursor.fetchall()


def choose_wordcloud_font() -> Optional[str]:
    candidate_fonts = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for font_path in candidate_fonts:
        if os.path.exists(font_path):
            return font_path
    return None


def tokenize_for_wordcloud(titles: List[str]) -> Dict[str, int]:
    counter: Counter = Counter()
    for title in titles:
        text = (title or "").strip()
        if not text:
            continue
        for token in jieba.lcut(text):
            token = token.strip()
            if not token or token in WORDCLOUD_STOPWORDS:
                continue
            if len(token) < 2:
                continue
            if re.fullmatch(r"[0-9A-Za-z_.-]+", token):
                continue
            counter[token] += 1
    return dict(counter)


def build_wordcloud_image(freq_map: Dict[str, int]):
    font_path = choose_wordcloud_font()
    cloud = WordCloud(
        width=1300,
        height=520,
        background_color="white",
        font_path=font_path,
        max_words=220,
        collocations=False,
    ).generate_from_frequencies(freq_map)
    return cloud.to_array()


def build_bubble_dataframe(rows: List[Dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["title"] = df["title"].fillna("").astype(str).str.strip()
    df = df[df["title"] != ""].copy()
    if df.empty:
        return pd.DataFrame()

    df["crawl_date"] = pd.to_datetime(df["crawl_date"], errors="coerce")
    df["rank_position"] = pd.to_numeric(df["rank_position"], errors="coerce").fillna(100)
    df = df.dropna(subset=["crawl_date"])

    grouped = (
        df.groupby(["title", "source_platform", "crawl_date"], as_index=False)
        .agg(
            mention_count=("id", "count"),
            best_rank=("rank_position", "min"),
            sample_url=("url", "first"),
        )
    )
    # 影响力定义：高排名(小数字) + 出现次数
    grouped["impact_score"] = (
        (101 - grouped["best_rank"].clip(lower=1, upper=100))
        * (1 + (grouped["mention_count"]).pow(0.5))
    ).round(2)
    grouped["bubble_size"] = (grouped["mention_count"] * 8).clip(lower=8, upper=70)
    return grouped.sort_values("impact_score", ascending=False)


def main():
    st.set_page_config(page_title="语情热点地图", layout="wide")
    st.title("语情热点中国地图（Demo）")
    st.caption("按平台切换话题后，可观察不同话题在不同地区的热度差异。")

    env = load_env()
    if not env:
        st.error("未读取到 .env，无法连接数据库。")
        return

    platform = st.selectbox("平台", options=list(PLATFORM_SQL.keys()), index=0)
    topic_count = st.slider("候选热点事件数量", min_value=5, max_value=30, value=10, step=1)

    try:
        conn = get_connection(env)
    except Exception as e:
        st.error(f"MySQL 连接失败: {e}")
        return

    with conn:
        topics = fetch_top_topics(conn, platform, limit=topic_count)
        if not topics:
            st.warning("该平台没有可用的 source_keyword 话题数据。")
            return

        topic_labels = [f"{t} (样本{c})" for t, c in topics]
        selected_label = st.selectbox("热点事件（话题）", options=topic_labels, index=0)
        selected_topic = selected_label.split(" (样本", 1)[0]

        map_data, region_totals = fetch_topic_heatmap_data(conn, platform, selected_topic)

    if not map_data:
        st.warning("该话题暂无可用 IP 评论数据，换一个话题试试。")
        return

    map_html = build_map_html(selected_topic, platform, map_data)
    components.html(map_html, height=720, scrolling=False)

    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("省份热度 Top 10")
        st.dataframe(map_data[:10], use_container_width=True, hide_index=True)

    with col2:
        st.subheader("区域汇总")
        ranked_regions = sorted(region_totals.items(), key=lambda x: x[1], reverse=True)
        st.dataframe(
            [{"区域": name, "热度": score} for name, score in ranked_regions],
            use_container_width=True,
            hide_index=True,
        )

    st.info(
        "说明：本页面聚焦地理热度分布。RI 风险分析已拆分为独立页面。"
    )

    st.divider()
    st.subheader("热点事件分析（daily_news）")
    st.caption("包含热点词云、时间-影响力气泡图、热门事件排行榜。")

    today = date.today()
    default_start = today - timedelta(days=6)
    date_range = st.date_input(
        "统计时间范围",
        value=(default_start, today),
        min_value=today - timedelta(days=60),
        max_value=today,
    )
    if not isinstance(date_range, tuple) or len(date_range) != 2:
        st.warning("请完整选择开始和结束日期。")
        return
    start_date, end_date = date_range

    with get_connection(env) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT source_platform FROM daily_news ORDER BY source_platform")
            platform_rows = cursor.fetchall()
        all_platforms = [r["source_platform"] for r in platform_rows if r["source_platform"]]

        selected_platforms = st.multiselect(
            "新闻来源平台筛选",
            options=all_platforms,
            default=all_platforms[:6] if len(all_platforms) > 6 else all_platforms,
        )
        news_rows = fetch_daily_news(
            conn,
            start_date=start_date,
            end_date=end_date,
            platforms=selected_platforms if selected_platforms else None,
            limit=5000,
        )

    if not news_rows:
        st.warning("当前筛选条件下，daily_news 没有可用数据。")
        return

    st.write(f"样本数：`{len(news_rows)}` 条")
    bubble_df = build_bubble_dataframe(news_rows)
    if bubble_df.empty:
        st.warning("daily_news 数据缺少有效标题，无法生成可视化。")
        return

    tabs = st.tabs(["热点事件词云图", "时间-影响力气泡图", "热门事件排行榜"])

    with tabs[0]:
        freq_map = tokenize_for_wordcloud(bubble_df["title"].tolist())
        if not freq_map:
            st.warning("分词后没有足够词条，无法生成词云。")
        else:
            wc_img = build_wordcloud_image(freq_map)
            st.image(wc_img, use_column_width=True)
            top_words = sorted(freq_map.items(), key=lambda x: x[1], reverse=True)[:20]
            st.dataframe(
                [{"词": w, "频次": c} for w, c in top_words],
                use_container_width=True,
                hide_index=True,
            )

    with tabs[1]:
        fig = px.scatter(
            bubble_df,
            x="crawl_date",
            y="impact_score",
            size="bubble_size",
            color="source_platform",
            hover_name="title",
            hover_data={
                "best_rank": True,
                "mention_count": True,
                "sample_url": True,
                "bubble_size": False,
            },
            title="热点事件气泡图（横轴=时间，纵轴=事件影响力）",
        )
        fig.update_layout(height=560, xaxis_title="时间", yaxis_title="影响力")
        st.plotly_chart(fig, use_container_width=True)

    with tabs[2]:
        rank_df = bubble_df.sort_values("impact_score", ascending=False).head(30).copy()
        rank_df.insert(0, "排名", range(1, len(rank_df) + 1))
        rank_df.rename(
            columns={
                "title": "事件标题",
                "source_platform": "平台",
                "crawl_date": "日期",
                "best_rank": "最佳榜单排名",
                "mention_count": "出现次数",
                "impact_score": "影响力",
                "sample_url": "链接",
            },
            inplace=True,
        )
        st.dataframe(
            rank_df[
                ["排名", "事件标题", "平台", "日期", "最佳榜单排名", "出现次数", "影响力", "链接"]
            ],
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
