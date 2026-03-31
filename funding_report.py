#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web3 / 加密融资日报推送机器人
每天 09:00 和 15:00（北京时间）推送当日融资项目报表到飞书
数据来源：CoinDesk、The Block、Decrypt、Cointelegraph RSS（完全免费）
包含：项目名、融资金额、投资机构、赛道分析、优缺点点评
"""

import os
import re
import time
import hashlib
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from deep_translator import GoogleTranslator

# ============================================================
# 配置区
# ============================================================
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
FEISHU_SECRET  = os.environ.get("FEISHU_SECRET", "")

# ============================================================
# 融资新闻 RSS 源（免费，无需 Key）
# ============================================================
FUNDING_RSS = {
    "CoinDesk":      "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "The Block":     "https://www.theblock.co/rss/all.xml",
    "Decrypt":       "https://decrypt.co/feed",
    "Cointelegraph": "https://cointelegraph.com/rss",
}

# 融资相关关键词过滤（英文）
FUNDING_KEYWORDS = [
    "raises", "raised", "funding", "investment", "round", "seed",
    "series a", "series b", "series c", "backed", "led by", "million",
    "billion", "venture", "capital", "valuation", "pre-seed", "grant",
]

# 赛道关键词识别
TRACK_KEYWORDS = {
    "🏦 DeFi":          ["defi", "dex", "lending", "yield", "liquidity", "amm", "swap"],
    "🎮 GameFi":        ["game", "gaming", "nft game", "play-to-earn", "p2e", "metaverse"],
    "🖼️ NFT":           ["nft", "marketplace", "collectible", "digital art"],
    "🔗 基础设施":      ["infrastructure", "layer", "l1", "l2", "rollup", "node", "rpc", "bridge"],
    "🔒 安全":          ["security", "audit", "insurance", "protection"],
    "💳 支付/RWA":      ["payment", "rwa", "real world", "stablecoin", "remittance"],
    "🤖 AI+Crypto":     ["ai", "artificial intelligence", "agent", "llm", "machine learning"],
    "🏛️ CeFi/交易所":  ["exchange", "cefi", "custody", "brokerage", "otc"],
    "⛏️ 挖矿/质押":    ["mining", "staking", "validator", "pos"],
    "🛠️ 开发工具":     ["developer", "sdk", "api", "tooling", "devtools", "wallet"],
}

# 投资轮次识别
ROUND_KEYWORDS = {
    "Pre-Seed 轮": ["pre-seed", "pre seed", "angel"],
    "Seed 轮":     ["seed round", "seed funding", "seed stage"],
    "A 轮":        ["series a"],
    "B 轮":        ["series b"],
    "C 轮":        ["series c"],
    "D+ 轮":       ["series d", "series e", "series f"],
    "战略融资":    ["strategic", "strategic investment", "strategic round"],
    "私募轮":      ["private", "private round", "private placement"],
    "代币融资":    ["token sale", "token round", "ido", "ico", "ieo"],
}

# 金额规模评级
def get_amount_level(amount_usd_m: float) -> str:
    if amount_usd_m >= 100:  return "🔥 超大额（$100M+）"
    if amount_usd_m >= 50:   return "💰 大额（$50M-100M）"
    if amount_usd_m >= 20:   return "📈 中大额（$20M-50M）"
    if amount_usd_m >= 5:    return "💵 中额（$5M-20M）"
    return                          "🌱 小额（<$5M）"

# ============================================================
# 工具函数
# ============================================================

def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

def get_beijing_str():
    return get_beijing_time().strftime("%Y-%m-%d %H:%M")

def translate_text(text: str) -> str:
    """单条翻译，失败返回原文"""
    try:
        if not text or any("\u4e00" <= c <= "\u9fff" for c in text):
            return text
        result = GoogleTranslator(source="auto", target="zh-CN").translate(text[:500])
        return result if result else text
    except Exception:
        return text

def gen_sign(timestamp, secret):
    import hmac, hashlib, base64
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")

# ============================================================
# 融资数据提取
# ============================================================

def extract_amount(text: str):
    """从标题/摘要中提取融资金额，返回 (金额数字, 单位字符串)"""
    text_lower = text.lower()

    # 匹配 $XXX million / $XX.X billion 等格式
    patterns = [
        r"\$\s*([\d,]+(?:\.\d+)?)\s*billion",
        r"\$\s*([\d,]+(?:\.\d+)?)\s*million",
        r"([\d,]+(?:\.\d+)?)\s*million\s*(?:dollar|usd)?",
        r"([\d,]+(?:\.\d+)?)\s*billion\s*(?:dollar|usd)?",
    ]
    for i, pat in enumerate(patterns):
        m = re.search(pat, text_lower)
        if m:
            num = float(m.group(1).replace(",", ""))
            if i < 2 or "billion" in pat:   # billion
                return num * 1000, f"${num}B"
            else:
                return num, f"${num}M"
    return None, "金额未披露"

def extract_round(text: str) -> str:
    """识别融资轮次"""
    text_lower = text.lower()
    for round_name, keywords in ROUND_KEYWORDS.items():
        if any(k in text_lower for k in keywords):
            return round_name
    return "战略/其他"

def extract_track(text: str) -> str:
    """识别项目赛道"""
    text_lower = text.lower()
    for track, keywords in TRACK_KEYWORDS.items():
        if any(k in text_lower for k in keywords):
            return track
    return "🔷 综合/其他"

def extract_investors(text: str) -> str:
    """从摘要中提取主要投资机构"""
    # 常见机构名单
    known_vcs = [
        "a16z", "andreessen horowitz", "paradigm", "pantera", "multicoin",
        "coinbase ventures", "binance labs", "sequoia", "tiger global",
        "polychain", "dragonfly", "animoca", "spartan", "delphi",
        "galaxy", "hack vc", "electric capital", "variant", "1kx",
        "framework", "placeholder", "union square", "blockchain capital",
        "lightspeed", "insight partners", "softbank", "khosla",
    ]
    text_lower = text.lower()
    found = [vc for vc in known_vcs if vc in text_lower]
    if found:
        return "、".join([v.title() for v in found[:4]])
    # 尝试提取 "led by X" 模式
    m = re.search(r"led by ([A-Z][A-Za-z\s&]+?)(?:[,.]|\sand\s|$)", text)
    if m:
        return m.group(1).strip()
    return "未披露"

# ============================================================
# 项目分析引擎
# ============================================================

def analyze_project(title: str, summary: str, amount_m, round_name: str, track: str) -> dict:
    """基于规则引擎生成项目优缺点分析"""
    pros = []
    cons = []
    full_text = f"{title} {summary}".lower()

    # ---- 优势分析 ----
    if amount_m and amount_m >= 50:
        pros.append("融资规模大，资金充裕，具备长期运营能力")
    if amount_m and amount_m >= 10:
        pros.append("获得市场认可，资本信心较强")

    if any(vc in full_text for vc in ["a16z", "paradigm", "sequoia", "coinbase ventures"]):
        pros.append("顶级机构背书，品牌效应显著，资源丰富")
    if any(vc in full_text for vc in ["binance labs", "animoca", "polychain"]):
        pros.append("知名产业资本参与，生态资源协同效应强")

    if "layer 2" in full_text or "l2" in full_text or "rollup" in full_text:
        pros.append("L2/扩容赛道热度持续，市场需求明确")
    if "ai" in full_text or "artificial intelligence" in full_text:
        pros.append("AI+Crypto 叙事强劲，市场关注度高")
    if "rwa" in full_text or "real world asset" in full_text:
        pros.append("RWA 赛道机构采用加速，合规化程度高")
    if "defi" in full_text:
        pros.append("DeFi 基础设施需求稳定，用户基础成熟")

    if round_name in ["Seed 轮", "Pre-Seed 轮"]:
        pros.append("早期项目估值低，成长空间大")
    if round_name in ["B 轮", "C 轮", "D+ 轮"]:
        pros.append("多轮融资验证，商业模式趋于成熟")

    # ---- 风险/缺点分析 ----
    if not amount_m:
        cons.append("融资金额未披露，市场透明度存疑")
    if amount_m and amount_m < 3:
        cons.append("融资规模较小，后续扩张资金可能受限")

    if round_name in ["Seed 轮", "Pre-Seed 轮"]:
        cons.append("早期项目风险高，产品落地存在不确定性")
    if round_name == "代币融资":
        cons.append("代币融资存在监管合规风险，需关注各地法规")

    if "nft" in full_text and "game" not in full_text:
        cons.append("纯 NFT 赛道流动性下滑，市场热度已过高峰")
    if "metaverse" in full_text:
        cons.append("元宇宙叙事降温，用户增长面临挑战")
    if "cefi" in full_text or "exchange" in full_text:
        cons.append("CeFi 赛道监管趋严，合规成本持续上升")

    if "infrastructure" in full_text or "layer" in full_text:
        cons.append("基础设施赛道竞争激烈，差异化壁垒需进一步验证")

    # 保底
    if not pros:
        pros.append("项目获得机构关注，具备一定市场潜力")
    if not cons:
        cons.append("需持续关注项目落地进展与代币经济模型")

    return {
        "pros": pros[:3],
        "cons": cons[:2],
    }

# ============================================================
# 去重工具（基于标题哈希，避免同一条出现两次）
# ============================================================

_seen_hashes: set = set()

def is_duplicate(title: str) -> bool:
    h = hashlib.md5(title.strip().lower().encode()).hexdigest()
    if h in _seen_hashes:
        return True
    _seen_hashes.add(h)
    return False

# ============================================================
# 主采集函数
# ============================================================

def fetch_funding_news(max_per_feed: int = 8) -> list:
    """从多个 RSS 源采集融资新闻并结构化"""
    raw_items = []

    for source, url in FUNDING_RSS.items():
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                if count >= max_per_feed:
                    break
                title   = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                link    = entry.get("link", "")

                # 过滤：只保留含融资关键词的条目
                combined = f"{title} {summary}".lower()
                if not any(kw in combined for kw in FUNDING_KEYWORDS):
                    continue
                if is_duplicate(title):
                    continue

                raw_items.append({
                    "source":  source,
                    "title":   title,
                    "summary": summary[:300],
                    "link":    link,
                })
                count += 1
        except Exception as e:
            print(f"RSS 采集失败 [{source}]: {e}")

    print(f"📰 共采集到 {len(raw_items)} 条融资相关新闻")
    return raw_items

def process_funding_items(raw_items: list) -> list:
    """结构化处理：提取金额/轮次/赛道/分析"""
    processed = []
    for item in raw_items:
        full = f"{item['title']} {item['summary']}"
        amount_m, amount_str = extract_amount(full)
        round_name  = extract_round(full)
        track       = extract_track(full)
        investors   = extract_investors(full)
        analysis    = analyze_project(item["title"], item["summary"], amount_m, round_name, track)

        # 翻译标题
        title_zh = translate_text(item["title"])
        time.sleep(0.2)

        processed.append({
            "source":     item["source"],
            "title":      item["title"],
            "title_zh":   title_zh,
            "link":       item["link"],
            "amount_m":   amount_m,
            "amount_str": amount_str,
            "round":      round_name,
            "track":      track,
            "investors":  investors,
            "pros":       analysis["pros"],
            "cons":       analysis["cons"],
        })

    # 按金额从大到小排序
    processed.sort(key=lambda x: x["amount_m"] or 0, reverse=True)
    return processed

# ============================================================
# 飞书卡片构建
# ============================================================

def build_funding_card(items: list, session: str) -> dict:
    """
    构建融资报表飞书卡片
    session: "morning"（早报）或 "afternoon"（午报）
    """
    now  = get_beijing_str()
    date = get_beijing_time().strftime("%m月%d日")
    label = "🌅 早报" if session == "morning" else "🌆 午报"

    # 统计数据
    total_amount = sum(i["amount_m"] for i in items if i["amount_m"])
    disclosed    = [i for i in items if i["amount_m"]]

    elements = []

    # 摘要统计栏
    stats = (
        f"**📊 今日融资概览**\n"
        f"共 **{len(items)}** 个项目融资"
        + (f"，已披露总额 **${total_amount:,.0f}M**" if total_amount else "")
        + f"\n数据来源：CoinDesk · The Block · Decrypt · Cointelegraph"
    )
    elements.append({"tag": "div", "text": {"content": stats, "tag": "lark_md"}})
    elements.append({"tag": "hr"})

    # 逐条项目详情
    if not items:
        elements.append({
            "tag": "div",
            "text": {"content": "📭 今日暂无披露融资项目，请关注后续更新", "tag": "lark_md"}
        })
    else:
        for idx, item in enumerate(items[:10], 1):   # 最多展示10条
            amount_level = get_amount_level(item["amount_m"]) if item["amount_m"] else "💬 金额未披露"
            pros_text = "\n".join([f"  ✅ {p}" for p in item["pros"]])
            cons_text = "\n".join([f"  ⚠️ {c}" for c in item["cons"]])

            content = (
                f"**{idx}. [{item['title_zh']}]({item['link']})**\n"
                f"来源：{item['source']}\n"
                f"💰 融资金额：**{item['amount_str']}**  {amount_level}\n"
                f"📋 轮次：{item['round']}　　🏷️ 赛道：{item['track']}\n"
                f"🏛️ 投资方：{item['investors']}\n"
                f"**👍 优势：**\n{pros_text}\n"
                f"**👎 风险：**\n{cons_text}"
            )
            elements.append({"tag": "div", "text": {"content": content, "tag": "lark_md"}})
            if idx < len(items[:10]):
                elements.append({"tag": "hr"})

    # 免责
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text",
                      "content": "⚠️ 以上融资信息来自公开媒体，分析仅供参考，不构成投资建议。"}]
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "content": f"💎 Web3 融资日报 {label}  |  {date}  {now}",
                    "tag": "plain_text"
                },
                "template": "green"
            },
            "elements": elements
        }
    }

# ============================================================
# 发送到飞书
# ============================================================

def send_to_feishu(payload: dict) -> bool:
    if not FEISHU_WEBHOOK:
        print("❌ 未设置 FEISHU_WEBHOOK 环境变量")
        return False

    if FEISHU_SECRET:
        import hmac, hashlib, base64
        ts   = str(int(time.time()))
        sign_str = f"{ts}\n{FEISHU_SECRET}"
        sign = base64.b64encode(
            hmac.new(sign_str.encode(), digestmod=hashlib.sha256).digest()
        ).decode()
        payload["timestamp"] = ts
        payload["sign"]      = sign

    try:
        r = requests.post(
            FEISHU_WEBHOOK,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        result = r.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            print(f"✅ 飞书推送成功：{get_beijing_str()}")
            return True
        else:
            print(f"❌ 飞书返回错误：{result}")
            return False
    except Exception as e:
        print(f"❌ 推送异常：{e}")
        return False

# ============================================================
# 主流程
# ============================================================

def main():
    bj = get_beijing_time()
    hour = bj.hour
    # 09:00 = 早报，15:00 = 午报，其他时间默认早报（手动触发时）
    session = "afternoon" if hour >= 12 else "morning"

    print(f"🚀 开始采集 Web3 融资数据... {get_beijing_str()}（{session}）")

    raw   = fetch_funding_news(max_per_feed=8)
    items = process_funding_items(raw)

    print(f"📊 处理完成，共 {len(items)} 个融资项目")

    card = build_funding_card(items, session)
    send_to_feishu(card)

if __name__ == "__main__":
    main()
