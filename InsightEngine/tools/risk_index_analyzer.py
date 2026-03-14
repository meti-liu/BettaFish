"""
RI 风险指数分析工具

设计原则：
1) 不改动原 sentiment_analyzer 的接口与行为；
2) 复用情感分析结果，在外层计算 RI；
3) 可单条/批量分析，输出可视化友好的结构化结果。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from .sentiment_analyzer import (
    BatchSentimentResult,
    SentimentResult,
    analyze_sentiment,
)


# 高危 Emoji 加成（影响 I_impact）
RISK_EMOJIS: Dict[str, float] = {
    "🕯️": 0.5,
    "🕯": 0.5,
    "🤬": 1.0,
    "🖕": 1.5,
    "💀": 0.5,
    "🔪": 1.5,
    "💣": 1.5,
    "💩": 0.5,
    "🤮": 0.5,
}

# 嘲讽/阴阳怪气 Emoji（用于修正 S_score）
SARCASM_EMOJIS = {"😅", "🤡", "🙃", "🌚", "🐔"}

# 网络语境中的“积极高唤醒”表达，避免被纯情感模型误打为高风险
POSITIVE_INTENSE_HINTS = {
    "好看疯了",
    "笑死",
    "笑死我了",
    "笑出声了",
    "哈哈",
    "哈哈哈",
    "哈哈哈哈",
    "搞笑",
    "太好笑了",
    "有趣",
    "绝了",
    "太绝了",
    "太牛了",
    "牛逼",
    "封神",
    "热血拉满",
    "太感动了",
    "太喜欢了",
    "支持",
    "维权",
}

HELP_QUERY_HINTS = {
    "怎么办",
    "怎么弄",
    "怎么做",
    "是不是",
    "请问",
    "求助",
    "求分享",
    "求教",
    "能不能",
    "可以吗",
    "吗",
    "呢",
}

# 显式攻击词（中文场景）
STRONG_ATTACK_TERMS = {
    "去死",
    "全家死",
    "该死",
    "畜生",
    "垃圾",
    "人肉",
    "诽谤",
    "网暴",
}

MEDIUM_ATTACK_TERMS = {
    "恶心",
    "滚",
    "毒",
    "丧尽天良",
    "纳粹",
    "歧视",
    "仇恨",
    "侮辱",
}


@dataclass
class RiskIndexResult:
    text: str
    sentiment_score: float
    impact_coefficient: float
    risk_index: float
    risk_level: str
    confidence: float
    probability_distribution: Dict[str, float]
    risk_reason: str = ""
    success: bool = True
    error_message: Optional[str] = None
    analysis_performed: bool = True


@dataclass
class BatchRiskIndexResult:
    results: List[RiskIndexResult]
    total_processed: int
    success_count: int
    failed_count: int
    analysis_performed: bool = True


def _risk_level(ri_100: float) -> str:
    if ri_100 >= 80:
        return "危险"
    if ri_100 >= 60:
        return "警告"
    if ri_100 >= 40:
        return "关注"
    return "安全"


def _normalize_probabilities(prob_dist: Dict[str, float]) -> Dict[str, float]:
    total = float(sum(prob_dist.values()))
    if total <= 0:
        return {}
    return {k: float(v) / total for k, v in prob_dist.items()}


def _compute_s_score_from_prob_dist(prob_dist: Dict[str, float]) -> float:
    """
    将 sentiment_analyzer 的 5 级标签映射到 [0,1] 友善度。
    兼容：中文标签、英文标签、LABEL_x。
    """
    probs = _normalize_probabilities(prob_dist)
    if not probs:
        return 0.5

    weighted_sum = 0.0
    for label, p in probs.items():
        l = str(label).strip().lower()
        weight = 0.5

        # 兼容中文标签
        if label == "非常负面":
            weight = 0.0
        elif label == "负面":
            weight = 0.25
        elif label == "中性":
            weight = 0.5
        elif label == "正面":
            weight = 0.75
        elif label == "非常正面":
            weight = 1.0
        # 兼容英文标签
        elif l in {"very negative", "extremely negative"}:
            weight = 0.0
        elif l == "negative":
            weight = 0.25
        elif l == "neutral":
            weight = 0.5
        elif l == "positive":
            weight = 0.75
        elif l in {"very positive", "extremely positive"}:
            weight = 1.0
        # 兼容 LABEL_0...LABEL_4
        elif l.startswith("label_"):
            try:
                idx = int(l.split("_")[1])
                if 0 <= idx <= 4:
                    weight = idx / 4.0
            except Exception:
                pass

        weighted_sum += p * weight

    return max(0.0, min(1.0, weighted_sum))


def _negative_probability(prob_dist: Dict[str, float]) -> float:
    probs = _normalize_probabilities(prob_dist)
    if not probs:
        return 0.0

    neg_prob = 0.0
    for label, p in probs.items():
        l = str(label).strip().lower()
        if label in {"非常负面", "负面"}:
            neg_prob += p
        elif l in {"very negative", "negative", "extremely negative"}:
            neg_prob += p
        elif l.startswith("label_"):
            try:
                idx = int(l.split("_")[1])
                if idx <= 1:
                    neg_prob += p
            except Exception:
                pass
    return min(1.0, max(0.0, neg_prob))


def _calculate_impact_coefficient(
    text: str,
    prob_dist: Dict[str, float],
    s_score: float,
) -> float:
    """
    I_impact 基础规则：
    - 初值 1.0；
    - 高负面概率加成；
    - 风险 Emoji 加成；
    - 嘲讽 Emoji + 高友善度冲突加成；
    - 上限截断。
    """
    impact = 1.0

    neg_prob = _negative_probability(prob_dist)
    if neg_prob > 0.7:
        impact += (neg_prob - 0.7) * 2.0

    emoji_boost = 0.0
    for emo, boost in RISK_EMOJIS.items():
        if emo in text:
            emoji_boost += boost
    impact += min(2.0, emoji_boost)

    has_sarcasm = any(emo in text for emo in SARCASM_EMOJIS)
    if has_sarcasm and s_score > 0.4:
        impact += 0.8

    text_l = text.lower()
    if any(t in text_l for t in STRONG_ATTACK_TERMS):
        impact += 0.8
    elif any(t in text_l for t in MEDIUM_ATTACK_TERMS):
        impact += 0.35

    return min(5.0, max(1.0, impact))


def _apply_text_calibration(text: str, s_score: float, impact: float) -> tuple[float, float]:
    """
    轻量语境校准：
    - 对“高唤醒但正向”的网络表达，抬高友善度并压低 impact 上限；
    - 对显式攻击词，再次下调友善度（防漏检）。
    """
    txt = (text or "").strip()
    txt_l = txt.lower()
    has_strong_attack = any(t in txt_l for t in STRONG_ATTACK_TERMS)
    has_medium_attack = any(t in txt_l for t in MEDIUM_ATTACK_TERMS)
    has_positive_hint = any(t in txt for t in POSITIVE_INTENSE_HINTS)

    if has_positive_hint and not (has_strong_attack or has_medium_attack):
        s_score = max(s_score, 0.62)
        impact = min(impact, 1.12)

    if has_strong_attack:
        s_score *= 0.72
    elif has_medium_attack:
        s_score *= 0.86

    # 求助/疑问语气通常不应直接等同高危攻击
    has_help_query = any(k in txt for k in HELP_QUERY_HINTS)
    if has_help_query and not (has_strong_attack or has_medium_attack):
        s_score = max(s_score, 0.55)
        impact = min(impact, 1.05)

    return max(0.0, min(1.0, s_score)), max(1.0, min(5.0, impact))


def _build_risk_reason(
    text: str,
    s_score: float,
    impact: float,
    h_norm: float,
    v_velocity: float,
) -> str:
    txt = (text or "").lower()
    reasons: List[str] = []
    if any(t in txt for t in STRONG_ATTACK_TERMS):
        reasons.append("命中强攻击词")
    elif any(t in txt for t in MEDIUM_ATTACK_TERMS):
        reasons.append("命中中等攻击词")
    if any(emo in text for emo in RISK_EMOJIS):
        reasons.append("命中风险Emoji")
    if any(k in text for k in POSITIVE_INTENSE_HINTS):
        reasons.append("命中正向高唤醒短语")
    if s_score < 0.35:
        reasons.append("情感分偏负面")
    if impact > 1.3:
        reasons.append("攻击系数抬升")
    if h_norm > 0.75:
        reasons.append("热度较高")
    if v_velocity > 0.75:
        reasons.append("传播速度较快")
    return "；".join(reasons) if reasons else "常规波动"


class RiskIndexAnalyzer:
    """
    独立 RI 分析器（不改动 sentiment_analyzer）。

    RI = alpha * H_norm + beta * (1 - S_score) * I_impact + gamma * V_velocity
    输出区间统一映射到 [0, 100]。
    """

    def __init__(self, alpha: float = 0.3, beta: float = 0.5, gamma: float = 0.2):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma

    def analyze_single_text(
        self,
        text: str,
        h_norm: float = 0.0,
        v_velocity: float = 0.0,
        initialize_if_needed: bool = True,
    ) -> RiskIndexResult:
        sentiment_result = analyze_sentiment(
            text, initialize_if_needed=initialize_if_needed
        )
        if not isinstance(sentiment_result, SentimentResult):
            return RiskIndexResult(
                text=text,
                sentiment_score=0.5,
                impact_coefficient=1.0,
                risk_index=0.0,
                risk_level="安全",
                confidence=0.0,
                probability_distribution={},
                success=False,
                error_message="内部错误：单条分析返回类型异常",
                analysis_performed=False,
            )
        return self._merge_with_sentiment(text, sentiment_result, h_norm, v_velocity)

    def analyze_batch_texts(
        self,
        texts: Sequence[str],
        h_norm_list: Optional[Sequence[float]] = None,
        v_velocity_list: Optional[Sequence[float]] = None,
        initialize_if_needed: bool = True,
    ) -> BatchRiskIndexResult:
        batch = analyze_sentiment(
            list(texts), initialize_if_needed=initialize_if_needed
        )
        if not isinstance(batch, BatchSentimentResult):
            return BatchRiskIndexResult(
                results=[],
                total_processed=0,
                success_count=0,
                failed_count=0,
                analysis_performed=False,
            )

        h_list = list(h_norm_list) if h_norm_list is not None else [0.0] * len(texts)
        v_list = (
            list(v_velocity_list) if v_velocity_list is not None else [0.0] * len(texts)
        )
        if len(h_list) < len(texts):
            h_list.extend([0.0] * (len(texts) - len(h_list)))
        if len(v_list) < len(texts):
            v_list.extend([0.0] * (len(texts) - len(v_list)))

        results: List[RiskIndexResult] = []
        success_count = 0
        for idx, senti in enumerate(batch.results):
            text = senti.text if isinstance(senti.text, str) else str(senti.text)
            ri_result = self._merge_with_sentiment(text, senti, h_list[idx], v_list[idx])
            if ri_result.success and ri_result.analysis_performed:
                success_count += 1
            results.append(ri_result)

        total = len(results)
        return BatchRiskIndexResult(
            results=results,
            total_processed=total,
            success_count=success_count,
            failed_count=total - success_count,
            analysis_performed=batch.analysis_performed,
        )

    def _merge_with_sentiment(
        self,
        text: str,
        sentiment_result: SentimentResult,
        h_norm: float,
        v_velocity: float,
    ) -> RiskIndexResult:
        if not sentiment_result.success or not sentiment_result.analysis_performed:
            return RiskIndexResult(
                text=text,
                sentiment_score=0.5,
                impact_coefficient=1.0,
                risk_index=0.0,
                risk_level="安全",
                confidence=0.0,
                probability_distribution=sentiment_result.probability_distribution or {},
                success=False,
                error_message=sentiment_result.error_message
                or "情感分析未执行，RI 已降级为默认值",
                analysis_performed=False,
            )

        s_score = _compute_s_score_from_prob_dist(
            sentiment_result.probability_distribution or {}
        )

        # 阴阳怪气修正：文本偏正但带嘲讽符号时，降低友善度
        if any(emo in text for emo in SARCASM_EMOJIS) and s_score > 0.5:
            s_score *= 0.5

        impact = _calculate_impact_coefficient(
            text=text,
            prob_dist=sentiment_result.probability_distribution or {},
            s_score=s_score,
        )
        s_score, impact = _apply_text_calibration(text, s_score, impact)

        h = min(1.0, max(0.0, float(h_norm)))
        v = min(1.0, max(0.0, float(v_velocity)))

        # 评论级试算采用保守缩放，避免 h/v 代理项把 RI 过度顶格
        h_eff = h**0.7
        v_eff = v * 0.35
        impact_eff = min(2.2, impact)

        ri_0_1 = self.alpha * h_eff + self.beta * (1.0 - s_score) * impact_eff + self.gamma * v_eff
        ri_100 = min(100.0, max(0.0, round(ri_0_1 * 100.0, 2)))

        # 轻量纠偏：无攻击词 + 正向高唤醒语境时，避免冲到极高风险
        txt_l = (text or "").lower()
        has_attack = any(t in txt_l for t in STRONG_ATTACK_TERMS) or any(
            t in txt_l for t in MEDIUM_ATTACK_TERMS
        )
        has_positive_hint = any(k in text for k in POSITIVE_INTENSE_HINTS)
        has_risk_emoji = any(e in text for e in RISK_EMOJIS)
        if has_positive_hint and not has_attack and s_score >= 0.62:
            ri_100 = min(ri_100, 68.0)
        # 无攻击词且无风险 Emoji：使用软压缩，避免“分数卡台阶”
        if not has_attack and not has_risk_emoji:
            ri_100 = round(78.0 * (1.0 - math.exp(-ri_100 / 48.0)), 2)
            short_text = len((text or "").strip()) <= 14
            laugh_hint = any(k in text for k in {"哈哈", "笑", "搞笑", "有趣"})
            if short_text and laugh_hint:
                ri_100 = round(ri_100 * 0.82, 2)

        risk_reason = _build_risk_reason(text, s_score, impact_eff, h_eff, v_eff)

        return RiskIndexResult(
            text=text,
            sentiment_score=round(s_score, 4),
            impact_coefficient=round(impact, 3),
            risk_index=ri_100,
            risk_level=_risk_level(ri_100),
            confidence=round(float(sentiment_result.confidence), 4),
            probability_distribution=sentiment_result.probability_distribution or {},
            risk_reason=risk_reason,
            success=True,
            analysis_performed=True,
        )


# 全局实例，便于与现有工具调用风格保持一致
risk_index_analyzer = RiskIndexAnalyzer()

