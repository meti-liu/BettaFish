"""
多语言情感分析工具
基于WeiboMultilingualSentiment (或 fallback 到 tabularisai/multilingual-sentiment-analysis)
为InsightEngine提供情感分析功能
"""

import os
import sys
import re
from typing import Dict, Any, Optional, Tuple, List

try:
    import torch
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
    # 修复 Windows 下可能的路径问题
    torch.classes.__path__ = []
except ImportError:
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    AutoTokenizer = None  # type: ignore
    AutoModelForSequenceClassification = None  # type: ignore
    TRANSFORMERS_AVAILABLE = False


# INFO：若想跳过情感分析，可手动切换此开关为False
SENTIMENT_ANALYSIS_ENABLED = True


# =============================================================================
#  Emoji & 语义 字典定义 (Semantic Dictionaries)
# =============================================================================

# 高危 Emoji：出现这些通常意味着强烈的情绪或特定含义
# Key: Emoji字符, Value: 增加的Impact系数
RISK_EMOJIS = {
    "🕯️": 0.5,  # 蜡烛 -> 默哀/群体性事件 (敏感但未必攻击，加分适中)
    "🕯": 0.5,   # 蜡烛 (变体)
    "🤬": 1.0,  # 咒骂 -> 明确攻击
    "🖕": 1.5,  # 侮辱 -> 强攻击
    "💀": 0.5,  # 骷髅 -> 死亡/极端 (可能是玩笑，加分适中)
    "🔪": 1.5,  # 刀 -> 暴力威胁
    "💣": 1.5,  # 炸弹 -> 暴力/恐吓
    "💩": 0.5,  # 侮辱
    "🤮": 0.5,  # 呕吐 -> 极度厌恶
}

# 嘲讽/阴阳怪气 Emoji：可能反转情感
# Key: Emoji字符, Value: 说明
SARCASM_EMOJIS = {
    "😅": "流汗黄豆",
    "🤡": "小丑",
    "🙃": "倒脸",
    "🌚": "狗头/阴险",
    "🐔": "只因(梗)",
}

# =============================================================================
#  模型加载逻辑 (Model Loading)
# =============================================================================

# 添加项目根目录到路径
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# 1. 优先检查项目约定的模型目录
weibo_sentiment_path = os.path.join(
    project_root, "SentimentAnalysisModel", "WeiboMultilingualSentiment"
)
# 2. 其次检查 predict.py 可能下载的子目录
weibo_sentiment_sub_path = os.path.join(weibo_sentiment_path, "model")

# 3. 最后使用当前 tools 目录下的 model (避免权限问题)
local_tools_model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model")

# 备选模型名称 (如果本地没有，则下载这个)
FALLBACK_MODEL_NAME = "tabularisai/multilingual-sentiment-analysis"

_tokenizer = None
_model = None


def load_model():
    """懒加载模型，避免import时直接加载导致卡顿"""
    global _tokenizer, _model
    if not SENTIMENT_ANALYSIS_ENABLED:
        return False

    if _model is not None:
        return True

    if not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE:
        print("Warning: PyTorch or Transformers not found. Sentiment analysis disabled.")
        return False

    # 确定加载路径
    model_path_to_use = None
    
    # 检查各个候选路径
    candidates = [
        weibo_sentiment_path,
        weibo_sentiment_sub_path,
        local_tools_model_path
    ]
    
    for path in candidates:
        if os.path.exists(os.path.join(path, "config.json")):
            model_path_to_use = path
            # print(f"Found local model at: {path}")
            break
            
    if model_path_to_use is None:
        # 本地没有模型，尝试下载到 local_tools_model_path (因为这里通常有写权限)
        download_target = local_tools_model_path
        print(f"Local model not found. Attempting to download {FALLBACK_MODEL_NAME} to {download_target}...")
        try:
            # 确保目录存在
            if not os.path.exists(download_target):
                os.makedirs(download_target, exist_ok=True)
            
            # 下载并保存
            print(f"Downloading tokenizer and model...")
            # 注意：使用 use_fast=False 以避免 sentencepiece 问题
            tokenizer = AutoTokenizer.from_pretrained(FALLBACK_MODEL_NAME, use_fast=False)
            model = AutoModelForSequenceClassification.from_pretrained(FALLBACK_MODEL_NAME)
            
            tokenizer.save_pretrained(download_target)
            model.save_pretrained(download_target)
            
            print("Model downloaded and saved successfully.")
            model_path_to_use = download_target
        except Exception as e:
            print(f"Error downloading model: {e}")
            # 如果下载失败，可能网络问题或权限问题
            return False

    try:
        # print(f"Loading sentiment model from: {model_path_to_use} ...")
        # Try loading with use_fast=False to solve sentencepiece issues
        _tokenizer = AutoTokenizer.from_pretrained(model_path_to_use, trust_remote_code=True, use_fast=False)
        _model = AutoModelForSequenceClassification.from_pretrained(model_path_to_use, trust_remote_code=True)
        _model.eval()  # 切换到评估模式
        # print("Sentiment model loaded successfully.")
        return True
    except Exception as e:
        print(f"Error loading model: {e}")
        return False


# =============================================================================
#  核心算法逻辑 (Core Algorithm)
# =============================================================================

def compute_s_score(probs: Dict[str, float]) -> float:
    """
    计算 S_score (友善度)
    支持 3分类 (pos,neu,neg) 和 5分类 (0=VeryNeg ... 4=VeryPos)
    """
    # 归一化处理 (防止概率之和不为1)
    total_prob = sum(probs.values())
    if total_prob == 0:
        return 0.5
        
    # 尝试检测 key 的类型
    keys = list(probs.keys())
    
    # 策略 A: 语义标签 (positive, neutral, negative)
    # 检查是否包含 5分类的标签
    is_5_class = False
    for k in probs:
        if isinstance(k, str) and ("very" in k or "star" in k):
            is_5_class = True
            break
            
    if not is_5_class and "positive" in probs:
        # 3分类: positive, neutral, negative
        p_pos = probs.get("positive", 0.0)
        p_neu = probs.get("neutral", 0.0)
        return (p_pos * 1.0 + p_neu * 0.5) / total_prob

    # 策略 B: 数字标签 (0, 1, 2, 3, 4) 或 (LABEL_0, ...)
    # 假设 5 分类: 0=极负, 1=负, 2=中, 3=正, 4=极正
    # 或者 BERT模型输出的标签可能是 '1 star', '2 stars' 等
    weighted_sum = 0.0
    
    for k, p in probs.items():
        weight = 0.5 # default
        idx = -1
        
        k_lower = str(k).lower()
        
        # 解析 Index
        if isinstance(k, int): idx = k
        elif isinstance(k, str):
            if k.isdigit(): idx = int(k)
            elif k.startswith("LABEL_"):
                try: idx = int(k.split("_")[1])
                except: pass
            elif "star" in k_lower: # e.g. "1 star", "5 stars"
                try: idx = int(k.split()[0]) - 1 # 1-5 -> 0-4
                except: pass
        
        # 映射权重
        if idx != -1:
            if 0 <= idx <= 4:
                weight = idx / 4.0  # 0->0.0, 4->1.0
            else:
                weight = 0.5
        # 兼容其他语义标签 (不区分大小写)
        elif k_lower == "very negative": weight = 0.0
        elif k_lower == "negative": weight = 0.25
        elif k_lower == "neutral": weight = 0.5
        elif k_lower == "positive": weight = 0.75
        elif k_lower == "very positive": weight = 1.0
        
        weighted_sum += p * weight
        
    return weighted_sum / total_prob


def calculate_impact_coefficient(probs: Dict[str, float], text: str, s_score: float) -> float:
    """
    计算 I_impact (攻击性系数/影响力系数)
    """
    impact = 1.0  # 默认为普通负面/普通影响

    # --- 1. 极端情绪加成 (Based on Probability) ---
    # 计算负面概率总和 (Negative + Very Negative)
    neg_prob = 0.0
    for k, p in probs.items():
        is_neg = False
        k_lower = str(k).lower()
        
        # 语义判断
        if k_lower == "negative" or k_lower == "very negative": is_neg = True
        # 数字判断 (0=VeryNeg, 1=Neg)
        elif isinstance(k, int) and k <= 1: is_neg = True
        elif isinstance(k, str):
            if k.isdigit() and int(k) <= 1: is_neg = True
            elif k.startswith("LABEL_"):
                try: 
                    if int(k.split("_")[1]) <= 1: is_neg = True
                except: pass
            elif "star" in k_lower: # e.g. "1 star", "2 stars"
                try: 
                    if int(k.split()[0]) <= 2: is_neg = True
                except: pass
        
        if is_neg:
            neg_prob += p
    
    # 如果模型非常确信是负面 (例如 0.95)，则说明言辞激烈
    # 阈值设为 0.7 开始加成
    if neg_prob > 0.7:
        # 线性加成：0.7 -> +0.0, 1.0 -> +0.6 (即 max base impact 1.6)
        boost = (neg_prob - 0.7) * 2.0
        impact += boost

    # --- 2. Emoji 加成 (Based on Semantics) ---
    emoji_boost = 0.0
    for emoji_char, weight_add in RISK_EMOJIS.items():
        if emoji_char in text:
            emoji_boost += weight_add
            
    # 限制 Emoji 单纯带来的加成不超过 2.0
    emoji_boost = min(emoji_boost, 2.0)
    impact += emoji_boost

    # --- 3. 嘲讽/阴阳怪气加成 ---
    has_sarcasm = False
    for emoji_char in SARCASM_EMOJIS:
        if emoji_char in text:
            has_sarcasm = True
            break
            
    if has_sarcasm:
        # 如果文本看起来是正面的 (S > 0.4)，但有嘲讽 Emoji，Impact + 0.8
        if s_score > 0.4:
            impact += 0.8

    # 硬性上限：防止系数爆炸
    return min(impact, 5.0) 


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    主函数：分析单条文本的情感和风险
    """
    if not load_model():
        return {
            "error": "Model not loaded",
            "sentiment_score": 0.5,
            "impact_coefficient": 1.0,
            "risk_index": 0.0,
            "probabilities": {}
        }

    # 1. 模型推理
    inputs = _tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
    with torch.no_grad():
        outputs = _model(**inputs)
        probs = F.softmax(outputs.logits, dim=1).squeeze().tolist()
    
    # 2. 解析概率分布
    id2label = _model.config.id2label
    prob_dict = {}
    
    # 如果 id2label 存在，使用它
    if id2label:
        for idx, prob in enumerate(probs):
            label = id2label[idx] # 可能是 "LABEL_0" 或 "positive"
            prob_dict[label] = float(prob)
    else:
        # 如果没有 id2label，直接用索引
        for idx, prob in enumerate(probs):
            prob_dict[idx] = float(prob)

    # DEBUG: 打印原始概率分布，方便调试
    # print(f"DEBUG: text='{text[:10]}...', probs={prob_dict}")

    # 3. 计算 S_score (友善度)
    s_score = compute_s_score(prob_dict)
    
    # --- 特殊处理：阴阳怪气修正 S_score ---
    has_sarcasm = any(e in text for e in SARCASM_EMOJIS)
    if has_sarcasm and s_score > 0.5:
        # 发现嘲讽，将“友善度”打折
        s_score = s_score * 0.5

    # 4. 计算 I_impact (攻击性系数)
    impact = calculate_impact_coefficient(prob_dict, text, s_score)
    
    # 5. 计算 Risk Index (风险指数)
    # Risk = (1 - S_score) * I_impact
    risk = (1.0 - s_score) * impact
    
    return {
        "text": text,
        "sentiment_score": round(s_score, 4),
        "impact_coefficient": round(impact, 2),
        "risk_index": round(risk, 4),
        "probabilities": prob_dict
    }

if __name__ == "__main__":
    # 测试用例
    test_texts = [
        "这个产品真是太棒了！",                # 正面
        "一般般吧，勉强能用。",                # 中性
        "垃圾东西，浪费我时间，去死吧！",        # 极负 + 攻击性
        "笑死我了 😅",                        # 嘲讽 (文字可能被识别为中性/正面)
        "我们要在这个日子点燃蜡烛 🕯️",         # 敏感事件 (文字中性)
        "既然你这么说，我也没办法 🙃",           # 阴阳怪气
        "你全家都死了 🤬"                      # 极度恶意 + Emoji
    ]
    
    print("Initializing model for test...")
    if load_model():
        print("=" * 60)
        print(f"{'Text':<20} | {'S_score':<8} | {'Impact':<6} | {'Risk':<6}")
        print("-" * 60)
        for t in test_texts:
            res = analyze_sentiment(t)
            # 截断显示文本
            display_text = (t[:18] + '..') if len(t) > 18 else t
            print(f"{display_text:<20} | {res['sentiment_score']:<8} | {res['impact_coefficient']:<6} | {res['risk_index']:<6}")
            
            # 打印详细概率，方便Debug
            print(f"  > Probs: {res['probabilities']}")
            print("-" * 60)
        print("=" * 60)
