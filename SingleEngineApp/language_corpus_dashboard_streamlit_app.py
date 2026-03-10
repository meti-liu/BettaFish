"""
语言语情专题看板

数据来源:
- Data/自建语料库.xlsx (或 csv)
- Data/各平台主题类别统计总表.xlsx (或 csv)

页面目标:
1) 展示语言语情语料的结构与分层标签体系
2) 展示四平台在语言主题上的差异与偏向
3) 支持按主题钻取典型话题与检索词
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

DATA_DIR = "Data"
CORPUS_BASE_NAME = "自建语料库"
SUMMARY_BASE_NAME = "各平台主题类别统计总表"
PLATFORMS = ["微博", "抖音", "今日头条", "小红书"]


def render_echarts(option: Dict, height: int = 480, chart_id: str = "chart") -> None:
    html = f"""
<div id="{chart_id}" style="width:100%;height:{height}px;"></div>
<script src="https://cdn.jsdelivr.net/npm/echarts@4/dist/echarts.min.js"></script>
<script>
  var chart = echarts.init(document.getElementById('{chart_id}'));
  var option = {json.dumps(option, ensure_ascii=False)};
  chart.setOption(option);
  window.addEventListener('resize', function() {{ chart.resize(); }});
</script>
"""
    components.html(html, height=height + 10, scrolling=False)


def _read_any_table(base_name: str) -> pd.DataFrame:
    xlsx_path = os.path.join(DATA_DIR, f"{base_name}.xlsx")
    csv_path = os.path.join(DATA_DIR, f"{base_name}.csv")

    if os.path.exists(xlsx_path):
        try:
            return pd.read_excel(xlsx_path)
        except Exception:
            # 某些环境中 openpyxl/defusedxml 兼容性问题会导致 xlsx 无法读取，降级到 csv
            pass
    if os.path.exists(csv_path):
        for enc in ["utf-8-sig", "utf-8", "gbk", "gb18030"]:
            try:
                return pd.read_csv(csv_path, encoding=enc)
            except Exception:
                continue
        raise RuntimeError(f"无法读取文件: {csv_path}")
    raise FileNotFoundError(f"未找到 {base_name}.xlsx 或 {base_name}.csv")


def _read_corpus_preferred() -> pd.DataFrame:
    # 优先读取完整版语料
    candidates = [
        os.path.join(DATA_DIR, "自建语料库 (1).csv"),
        os.path.join(DATA_DIR, "自建语料库 (1).xlsx"),
        os.path.join(DATA_DIR, "自建语料库.xlsx"),
        os.path.join(DATA_DIR, "自建语料库.csv"),
    ]
    for p in candidates:
        if not os.path.exists(p):
            continue
        if p.lower().endswith(".xlsx"):
            try:
                return pd.read_excel(p)
            except Exception:
                continue
        else:
            for enc in ["utf-8-sig", "utf-8", "gbk", "gb18030"]:
                try:
                    return pd.read_csv(p, encoding=enc)
                except Exception:
                    continue
    raise FileNotFoundError("未找到可读取的自建语料库文件（含完整版自建语料库 (1)）")


def load_corpus_data() -> pd.DataFrame:
    df = _read_corpus_preferred().copy()
    df.columns = [str(c).strip() for c in df.columns]
    for col in [
        "检索词", "话题", "主题", "次主题", "次次主题", "媒体", "专家", "普通人",
        "政府", "企业", "热度", "时间", "分类", "标识", "话题链接", "主持人"
    ]:
        if col not in df.columns:
            df[col] = ""
    for col in [
        "检索词", "话题", "主题", "次主题", "次次主题", "媒体", "专家", "普通人",
        "政府", "企业", "分类", "标识", "话题链接", "主持人"
    ]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["热度"] = pd.to_numeric(df["热度"], errors="coerce").fillna(0)
    df["时间"] = pd.to_datetime(df["时间"], errors="coerce")
    df = df[df["话题"] != ""].reset_index(drop=True)
    return df


def load_summary_data() -> pd.DataFrame:
    df = _read_any_table(SUMMARY_BASE_NAME).copy()
    df.columns = [str(c).strip() for c in df.columns]
    for col in ["主题", "次主题", "次次主题", "微博", "抖音", "今日头条", "小红书", "共计"]:
        if col not in df.columns:
            df[col] = 0 if col in PLATFORMS + ["共计"] else ""

    df["主题"] = df["主题"].fillna("").astype(str).str.strip()
    df["次主题"] = df["次主题"].fillna("").astype(str).str.strip()
    df["次次主题"] = df["次次主题"].fillna("").astype(str).str.strip()
    df["主题"] = df["主题"].replace("", pd.NA).ffill().fillna("")
    df["次主题"] = df["次主题"].replace("", pd.NA).ffill().fillna("")

    for p in PLATFORMS + ["共计"]:
        df[p] = pd.to_numeric(df[p], errors="coerce").fillna(0).astype(int)

    # 清除仅用于小计/空白分隔的行
    df = df[df["主题"] != ""].copy()
    df = df[~((df["次次主题"] == "") & (df["共计"] == 0) & (df[PLATFORMS].sum(axis=1) == 0))]
    df = df.reset_index(drop=True)
    return df


def build_theme_platform_matrix(summary_df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        summary_df.groupby("主题", as_index=False)[PLATFORMS + ["共计"]]
        .sum()
        .sort_values("共计", ascending=False)
    )
    return grouped


def build_hierarchy_from_corpus(corpus_df: pd.DataFrame, top_n_theme: int = 12) -> List[Dict]:
    theme_rank = corpus_df["主题"].value_counts().head(top_n_theme).index.tolist()
    work = corpus_df[corpus_df["主题"].isin(theme_rank)].copy()

    hierarchy = []
    for theme, g_theme in work.groupby("主题"):
        theme_node = {"name": theme, "value": int(len(g_theme)), "children": []}
        for sub, g_sub in g_theme.groupby("次主题"):
            sub_label = sub if sub else "未标注次主题"
            sub_node = {"name": sub_label, "value": int(len(g_sub)), "children": []}
            for sub2, g_sub2 in g_sub.groupby("次次主题"):
                leaf = sub2 if sub2 else "未标注次次主题"
                sub_node["children"].append({"name": leaf, "value": int(len(g_sub2))})
            sub_node["children"] = sorted(sub_node["children"], key=lambda x: x["value"], reverse=True)[:12]
            theme_node["children"].append(sub_node)
        theme_node["children"] = sorted(theme_node["children"], key=lambda x: x["value"], reverse=True)[:20]
        hierarchy.append(theme_node)
    hierarchy.sort(key=lambda x: x["value"], reverse=True)
    return hierarchy


def main():
    st.set_page_config(page_title="语言语情专题看板", layout="wide")
    st.title("语言语情专题看板")
    st.caption("聚焦语言文字治理语境，展示语料结构、平台差异与主题钻取。")

    try:
        corpus_df = load_corpus_data()
        summary_df = load_summary_data()
    except Exception as e:
        st.error(f"数据加载失败: {e}")
        return

    matrix_df = build_theme_platform_matrix(summary_df)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("语料条目", f"{len(corpus_df)}")
    m2.metric("一级主题数", f"{corpus_df['主题'].nunique()}")
    m3.metric("二级主题数", f"{corpus_df['次主题'].replace('', pd.NA).nunique()}")
    m4.metric("检索词规模", f"{corpus_df['检索词'].replace('', pd.NA).nunique()}")

    tabs = st.tabs(["语料库画像", "平台主题差异", "主题钻取与样例", "传播态势与来源"])

    with tabs[0]:
        col_left, col_right = st.columns([3, 2])

        with col_left:
            st.subheader("语言主题层级结构（旭日图）")
            hierarchy = build_hierarchy_from_corpus(corpus_df, top_n_theme=12)
            sunburst_option = {
                "tooltip": {"trigger": "item"},
                "series": [
                    {
                        "type": "sunburst",
                        "data": hierarchy,
                        "radius": [0, "92%"],
                        "label": {"rotate": "radial"},
                    }
                ],
            }
            render_echarts(sunburst_option, height=560, chart_id="sunburst_hierarchy")

        with col_right:
            st.subheader("一级主题占比（Top10）")
            top_theme = (
                corpus_df["主题"]
                .value_counts()
                .head(10)
                .reset_index()
            )
            top_theme.columns = ["主题", "数量"]
            pie_option = {
                "tooltip": {"trigger": "item"},
                "legend": {"orient": "vertical", "left": "left"},
                "series": [
                    {
                        "name": "主题占比",
                        "type": "pie",
                        "radius": "70%",
                        "data": [{"name": r["主题"], "value": int(r["数量"])} for _, r in top_theme.iterrows()],
                    }
                ],
            }
            render_echarts(pie_option, height=420, chart_id="theme_pie")

            st.subheader("语料角色标注覆盖")
            role_stats = {
                "媒体": int((corpus_df["媒体"] != "").sum()),
                "专家": int((corpus_df["专家"] != "").sum()),
                "普通人": int((corpus_df["普通人"] != "").sum()),
            }
            st.dataframe(
                pd.DataFrame(
                    [{"角色字段": k, "已标注条数": v, "覆盖率": f"{(v / max(len(corpus_df),1)) * 100:.1f}%"} for k, v in role_stats.items()]
                ),
                width="stretch",
                hide_index=True,
            )

    with tabs[1]:
        left, right = st.columns([2, 3])
        with left:
            st.subheader("四平台语情主题总量对比")
            platform_sum = summary_df[PLATFORMS].sum().reset_index()
            platform_sum.columns = ["平台", "数量"]
            bar_option = {
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "category", "data": platform_sum["平台"].tolist()},
                "yAxis": {"type": "value"},
                "series": [{"type": "bar", "data": platform_sum["数量"].astype(int).tolist()}],
            }
            render_echarts(bar_option, height=420, chart_id="platform_total_bar")

            st.subheader("平台占比")
            donut_option = {
                "tooltip": {"trigger": "item"},
                "series": [
                    {
                        "type": "pie",
                        "radius": ["45%", "75%"],
                        "data": [{"name": r["平台"], "value": int(r["数量"])} for _, r in platform_sum.iterrows()],
                    }
                ],
            }
            render_echarts(donut_option, height=320, chart_id="platform_share_donut")

        with right:
            st.subheader("语言主题 × 平台 热点矩阵（Top15主题）")
            top15 = matrix_df.head(15).copy()
            heat_data = []
            for yi, theme in enumerate(top15["主题"].tolist()):
                for xi, p in enumerate(PLATFORMS):
                    heat_data.append([xi, yi, int(top15.iloc[yi][p])])
            heat_option = {
                "tooltip": {"position": "top"},
                "grid": {"height": "75%", "top": "8%"},
                "xAxis": {"type": "category", "data": PLATFORMS, "splitArea": {"show": True}},
                "yAxis": {"type": "category", "data": top15["主题"].tolist(), "splitArea": {"show": True}},
                "visualMap": {"min": 0, "max": int(max([x[2] for x in heat_data]) if heat_data else 10), "calculable": True, "orient": "horizontal", "left": "center", "bottom": "2%"},
                "series": [{"name": "主题热度", "type": "heatmap", "data": heat_data, "label": {"show": False}}],
            }
            render_echarts(heat_option, height=640, chart_id="theme_platform_heatmap")

    with tabs[2]:
        theme_options = sorted([x for x in corpus_df["主题"].unique().tolist() if x])
        selected_theme = st.selectbox("选择一级主题", options=theme_options, index=0)
        theme_df = corpus_df[corpus_df["主题"] == selected_theme].copy()

        c1, c2 = st.columns([2, 3])
        with c1:
            st.subheader("该主题下次主题分布")
            sub_counts = (
                theme_df["次主题"].replace("", "未标注次主题")
                .value_counts()
                .head(12)
                .reset_index()
            )
            sub_counts.columns = ["次主题", "数量"]
            sub_bar = {
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": sub_counts["次主题"].tolist()},
                "series": [{"type": "bar", "data": sub_counts["数量"].astype(int).tolist()}],
            }
            render_echarts(sub_bar, height=460, chart_id="subtheme_bar")

        with c2:
            st.subheader("该主题下高频检索词（Top20）")
            kw_counts = (
                theme_df["检索词"].replace("", pd.NA).dropna()
                .value_counts()
                .head(20)
                .reset_index()
            )
            kw_counts.columns = ["检索词", "频次"]
            kw_bar = {
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "category", "data": kw_counts["检索词"].tolist(), "axisLabel": {"rotate": 35}},
                "yAxis": {"type": "value"},
                "series": [{"type": "bar", "data": kw_counts["频次"].astype(int).tolist()}],
            }
            render_echarts(kw_bar, height=460, chart_id="keyword_bar")

        st.subheader("典型话题样例（按检索词聚合后抽样）")
        sample_df = (
            theme_df[["检索词", "话题", "次主题", "次次主题"]]
            .drop_duplicates()
            .head(80)
            .copy()
        )
        st.dataframe(sample_df, width="stretch", hide_index=True)
        st.info("建议：这一页可直接作为“语情语料底座说明页”给组长展示，重点强调主题体系、平台差异、可追溯话题样例。")

    with tabs[3]:
        left, right = st.columns([3, 2])
        with left:
            st.subheader("语情事件热度 Top15")
            heat_top = (
                corpus_df.sort_values("热度", ascending=False)[["话题", "热度"]]
                .drop_duplicates(subset=["话题"])
                .head(15)
            )
            heat_option = {
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": heat_top["话题"].tolist()},
                "series": [{"type": "bar", "data": heat_top["热度"].astype(int).tolist()}],
            }
            render_echarts(heat_option, height=520, chart_id="heat_top15")

            st.subheader("语情事件时间趋势（月）")
            trend_df = corpus_df.dropna(subset=["时间"]).copy()
            if len(trend_df) > 0:
                trend_df["月份"] = trend_df["时间"].dt.to_period("M").astype(str)
                month_cnt = trend_df.groupby("月份", as_index=False).size().sort_values("月份")
                line_option = {
                    "tooltip": {"trigger": "axis"},
                    "xAxis": {"type": "category", "data": month_cnt["月份"].tolist()},
                    "yAxis": {"type": "value"},
                    "series": [{"type": "line", "smooth": True, "data": month_cnt["size"].astype(int).tolist()}],
                }
                render_echarts(line_option, height=300, chart_id="month_trend")
            else:
                st.caption("未检测到可解析的时间字段，无法绘制趋势图。")

        with right:
            st.subheader("话题分类分布")
            cls_df = (
                corpus_df["分类"].replace("", "未标注")
                .value_counts()
                .head(10)
                .reset_index()
            )
            cls_df.columns = ["分类", "数量"]
            cls_option = {
                "tooltip": {"trigger": "item"},
                "series": [{"type": "pie", "radius": ["40%", "72%"], "data": [{"name": r["分类"], "value": int(r["数量"])} for _, r in cls_df.iterrows()]}],
            }
            render_echarts(cls_option, height=320, chart_id="category_donut")

            st.subheader("来源主体覆盖（语情治理视角）")
            source_stats = {
                "官方/政府": int((corpus_df["政府"] != "").sum()),
                "企业": int((corpus_df["企业"] != "").sum()),
                "媒体": int((corpus_df["媒体"] != "").sum()),
                "专家": int((corpus_df["专家"] != "").sum()),
                "普通人": int((corpus_df["普通人"] != "").sum()),
            }
            st.dataframe(
                pd.DataFrame(
                    [{"主体类型": k, "条目数": v, "占比": f"{(v / max(len(corpus_df),1))*100:.1f}%"} for k, v in source_stats.items()]
                ),
                width="stretch",
                hide_index=True,
            )


if __name__ == "__main__":
    main()

