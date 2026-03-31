#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全球金融情报系统 - 飞书推送机器人
每小时自动获取全球财经数据并推送到飞书
新闻标题通过 Google 翻译自动转成中文（完全免费，无需 API Key）
"""

import os
import json
import time
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from deep_translator import GoogleTranslator

# ============================================================
# 配置区
# ============================================================
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
FEISHU_SECRET  = os.environ.get("FEISHU_SECRET", "")   # 可选：飞书签名密钥

# 免费 API（无需 Key）
YAHOO_QUOTE_URL  = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
COINGECKO_URL    = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,binancecoin,matic-network,dogecoin,cardano,ripple,tron,litecoin&vs_currencies=usd&include_24hr_change=true"
GOLD_URL         = "https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=1d&range=1d"
OIL_URL          = "https://query1.finance.yahoo.com/v8/finance/chart/CL%3DF?interval=1d&range=1d"
TREASURY_URL     = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1d&range=1d"
USDC_CNY_URL     = "https://query1.finance.yahoo.com/v8/finance/chart/USDCNY%3DX?interval=1d&range=1d"

# RSS 新闻源
RSS_FEEDS = {
    "Reuters 财经": "https://feeds.reuters.com/reuters/businessNews",
    "CNBC":         "https://feeds.content.dowjones.io/public/rss/mktgnews",
    "Bloomberg":    "https://feeds.bloomberg.com/markets/news.rss",
    "Yahoo财经":    "https://finance.yahoo.com/news/rssindex",
}

# VIP 关注人物关键词
VIP_KEYWORDS = ["Musk", "马斯克", "Trump", "特朗普", "Buffett", "巴菲特",
                "Powell", "鲍威尔", "Fed", "美联储", "FOMC", "tariff", "关税",
                "recession", "衰退", "rate cut", "降息", "rate hike", "加息"]

# 投资信号关键词规则引擎
SIGNAL_RULES = {
    "🔴 风险警报": ["crash", "collapse", "crisis", "panic", "meltdown", "暴跌", "崩盘", "危机"],
    "🟢 利好信号": ["rally", "surge", "breakout", "bull", "record high", "暴涨", "突破", "牛市"],
    "⚠️ 政策风险": ["sanction", "tariff", "ban", "制裁", "关税", "禁令", "战争", "war"],
    "💡 机会信号": ["acquisition", "merger", "IPO", "earnings beat", "收购", "合并", "超预期"],
}

# ============================================================
# 工具函数
# ============================================================

def get_beijing_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M")

def fetch_yahoo(url):
    """从 Yahoo Finance 获取单个标的最新价格和涨跌幅"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        meta   = data["chart"]["result"][0]["meta"]
        price  = meta.get("regularMarketPrice", 0)
        prev   = meta.get("chartPreviousClose", price)
        change = ((price - prev) / prev * 100) if prev else 0
        return price, change
    except Exception as e:
        print(f"Yahoo fetch error: {e}")
        return None, None

def fmt_price(price, decimals=2):
    if price is None:
        return "N/A"
    return f"{price:,.{decimals}f}"

def fmt_change(change):
    if change is None:
        return "N/A"
    arrow = "▲" if change >= 0 else "▼"
    color = "+" if change >= 0 else ""
    return f"{arrow} {color}{change:.2f}%"

# ============================================================
# 数据采集模块
# ============================================================

def get_stock_data():
    """A股指数、美股、纳指"""
    symbols = {
        "上证指数": "000001.SS",
        "深证成指": "399001.SZ",
        "沪深300":  "000300.SS",
        "道琼斯":   "^DJI",
        "纳斯达克": "^IXIC",
        "标普500":  "^GSPC",
    }
    results = {}
    for name, sym in symbols.items():
        url = YAHOO_QUOTE_URL.format(symbol=requests.utils.quote(sym))
        price, change = fetch_yahoo(url)
        results[name] = (price, change)
        time.sleep(0.3)
    return results

def get_crypto_data():
    """BTC / ETH / SOL / BNB / POL / DOGE / ADA / XRP / TRX / LTC"""
    try:
        r = requests.get(COINGECKO_URL, timeout=10)
        data = r.json()
        return {
            "BTC":  (data["bitcoin"]["usd"],        data["bitcoin"]["usd_24h_change"]),
            "ETH":  (data["ethereum"]["usd"],        data["ethereum"]["usd_24h_change"]),
            "BNB":  (data["binancecoin"]["usd"],     data["binancecoin"]["usd_24h_change"]),
            "SOL":  (data["solana"]["usd"],          data["solana"]["usd_24h_change"]),
            "XRP":  (data["ripple"]["usd"],          data["ripple"]["usd_24h_change"]),
            "DOGE": (data["dogecoin"]["usd"],        data["dogecoin"]["usd_24h_change"]),
            "ADA":  (data["cardano"]["usd"],         data["cardano"]["usd_24h_change"]),
            "TRX":  (data["tron"]["usd"],            data["tron"]["usd_24h_change"]),
            "LTC":  (data["litecoin"]["usd"],        data["litecoin"]["usd_24h_change"]),
            "POL":  (data["matic-network"]["usd"],   data["matic-network"]["usd_24h_change"]),
        }
    except Exception as e:
        print(f"Crypto fetch error: {e}")
        return {}

def get_macro_data():
    """黄金、原油、美债、美元/人民币"""
    items = {
        "黄金 ($/oz)":    (GOLD_URL,      2),
        "原油 (WTI)":     (OIL_URL,       2),
        "美债10Y (%)":    (TREASURY_URL,  3),
        "美元/人民币":    (USDC_CNY_URL,  4),
    }
    results = {}
    for name, (url, dec) in items.items():
        price, change = fetch_yahoo(url)
        results[name] = (price, change, dec)
        time.sleep(0.3)
    return results

# ============================================================
# 翻译模块（Google 翻译，完全免费，无需 API Key）
# ============================================================

def translate_titles(titles: list) -> list:
    """
    批量将英文新闻标题翻译成中文。
    使用 deep-translator 调用 Google 翻译，免费无限制。
    若翻译失败自动降级返回原文，不影响推送。
    """
    if not titles:
        return titles

    translator = GoogleTranslator(source="auto", target="zh-CN")
    translated = []

    for title in titles:
        try:
            # 标题已是中文则跳过
            if any("\u4e00" <= c <= "\u9fff" for c in title):
                translated.append(title)
            else:
                result = translator.translate(title)
                translated.append(result if result else title)
            time.sleep(0.2)   # 避免触发频率限制
        except Exception as e:
            print(f"⚠️  翻译失败「{title[:30]}...」：{e}")
            translated.append(title)   # 降级保留原文

    print(f"✅ Google 翻译完成，共 {len(translated)} 条")
    return translated


def get_news(max_per_feed=3):
    """从 RSS 获取最新财经新闻，并将标题自动翻译成中文"""
    news_list = []
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                title     = entry.get("title", "")
                link      = entry.get("link", "")
                summary   = entry.get("summary", "")[:100]
                published = entry.get("published", "")
                news_list.append({
                    "source":    source,
                    "title":     title,       # 原始标题（用于关键词信号分析）
                    "title_zh":  title,       # 中文标题（翻译后覆盖）
                    "link":      link,
                    "summary":   summary,
                    "published": published,
                })
        except Exception as e:
            print(f"RSS error [{source}]: {e}")

    # 批量翻译所有标题（一次 API 请求）
    if news_list:
        raw_titles = [n["title"] for n in news_list]
        zh_titles  = translate_titles(raw_titles)
        for i, n in enumerate(news_list):
            n["title_zh"] = zh_titles[i]

    return news_list

# ============================================================
# 投资分析引擎
# ============================================================

def analyze_signals(news_list, stocks, crypto, macro):
    signals = []

    # 新闻关键词扫描
    all_titles = " ".join([n["title"] for n in news_list])
    for label, keywords in SIGNAL_RULES.items():
        hits = [k for k in keywords if k.lower() in all_titles.lower()]
        if hits:
            signals.append(f"{label}：检测到关键词 [{', '.join(hits[:3])}]")

    # VIP 人物动态
    vip_news = []
    for n in news_list:
        for kw in VIP_KEYWORDS:
            if kw.lower() in n["title"].lower():
                title_display = n.get("title_zh") or n["title"]
                vip_news.append(f"• [{n['source']}] {title_display[:60]}")
                break
    if vip_news:
        signals.append("👤 VIP 人物动态：\n" + "\n".join(vip_news[:4]))

    # 技术信号：BTC 大幅波动
    btc_price, btc_change = crypto.get("BTC", (None, None))
    if btc_change and abs(btc_change) > 5:
        emoji = "🚀" if btc_change > 0 else "💥"
        signals.append(f"{emoji} BTC 24h 波动超5%，当前 {fmt_change(btc_change)}，需关注市场情绪")

    # 黄金/原油联动分析
    gold_data = macro.get("黄金 ($/oz)")
    oil_data  = macro.get("原油 (WTI)")
    if gold_data and oil_data:
        g_chg = gold_data[1]
        o_chg = oil_data[1]
        if g_chg and g_chg > 1:
            signals.append("🥇 黄金上涨，市场避险情绪升温，关注地缘政治风险")
        if o_chg and o_chg < -2:
            signals.append("🛢️ 原油大跌，可能预示需求走弱或供给冲击")

    return signals if signals else ["📊 当前市场信号平稳，无明显异常"]

# ============================================================
# 飞书消息构建
# ============================================================

def build_feishu_card(stocks, crypto, macro, news_list, signals):
    """构建飞书卡片消息（card 格式）"""
    now = get_beijing_time()

    # --- 行情板块 ---
    stock_lines = []
    for name, (price, change) in stocks.items():
        stock_lines.append(f"**{name}** {fmt_price(price)}  {fmt_change(change)}")

    crypto_lines = []
    for name, (price, change) in crypto.items():
        crypto_lines.append(f"**{name}** ${fmt_price(price)}  {fmt_change(change)}")

    macro_lines = []
    for name, data in macro.items():
        price, change, dec = data
        macro_lines.append(f"**{name}** {fmt_price(price, dec)}  {fmt_change(change)}")

    # --- 新闻板块（取前6条，显示中文标题）---
    news_lines = []
    for n in news_list[:6]:
        title_display = n.get("title_zh") or n["title"]
        news_lines.append(f"• [{n['source']}] [{title_display[:55]}]({n['link']})")

    # --- 信号板块 ---
    signal_lines = [f"• {s}" for s in signals]

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "content": f"🌐 全球金融情报  |  {now} (北京时间)",
                    "tag": "plain_text"
                },
                "template": "blue"
            },
            "elements": [
                # 股市行情
                {
                    "tag": "div",
                    "text": {
                        "content": "**📈 股市行情**\n" + "\n".join(stock_lines),
                        "tag": "lark_md"
                    }
                },
                {"tag": "hr"},
                # 加密货币
                {
                    "tag": "div",
                    "text": {
                        "content": "**₿ 加密货币**\n" + "\n".join(crypto_lines),
                        "tag": "lark_md"
                    }
                },
                {"tag": "hr"},
                # 宏观指标
                {
                    "tag": "div",
                    "text": {
                        "content": "**🌍 宏观指标**\n" + "\n".join(macro_lines),
                        "tag": "lark_md"
                    }
                },
                {"tag": "hr"},
                # 财经快讯
                {
                    "tag": "div",
                    "text": {
                        "content": "**📰 全球财经快讯**\n" + "\n".join(news_lines) if news_lines else "**📰 全球财经快讯**\n暂无最新快讯",
                        "tag": "lark_md"
                    }
                },
                {"tag": "hr"},
                # 投资信号
                {
                    "tag": "div",
                    "text": {
                        "content": "**🧠 AI 投资信号分析**\n" + "\n".join(signal_lines),
                        "tag": "lark_md"
                    }
                },
                {"tag": "hr"},
                # 免责声明
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "⚠️ 以上数据仅供参考，不构成任何投资建议。市场有风险，投资需谨慎。"
                        }
                    ]
                }
            ]
        }
    }
    return card

# ============================================================
# 签名函数（如果飞书开启了签名校验）
# ============================================================

def gen_sign(timestamp, secret):
    import hmac, hashlib, base64
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")

# ============================================================
# 发送到飞书
# ============================================================

def send_to_feishu(payload):
    if not FEISHU_WEBHOOK:
        print("❌ 未设置 FEISHU_WEBHOOK 环境变量")
        return False

    # 如果有签名密钥，加入签名
    if FEISHU_SECRET:
        ts = str(int(time.time()))
        sign = gen_sign(ts, FEISHU_SECRET)
        payload["timestamp"] = ts
        payload["sign"] = sign

    try:
        headers = {"Content-Type": "application/json"}
        r = requests.post(FEISHU_WEBHOOK, json=payload, headers=headers, timeout=15)
        result = r.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            print(f"✅ 飞书推送成功：{get_beijing_time()}")
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
    print(f"🚀 开始采集全球金融情报... {get_beijing_time()}")

    print("📊 获取股市数据...")
    stocks = get_stock_data()

    print("₿ 获取加密货币数据...")
    crypto = get_crypto_data()

    print("🌍 获取宏观指标...")
    macro = get_macro_data()

    print("📰 抓取财经新闻...")
    news_list = get_news(max_per_feed=3)
    print(f"   共获取 {len(news_list)} 条新闻")

    print("🧠 分析投资信号...")
    signals = analyze_signals(news_list, stocks, crypto, macro)

    print("📨 构建并推送飞书消息...")
    card = build_feishu_card(stocks, crypto, macro, news_list, signals)
    success = send_to_feishu(card)

    if not success:
        # 降级：发送简单文本消息
        text = f"⚠️ 卡片消息发送失败，尝试文本格式\n时间：{get_beijing_time()}\n请检查 Webhook 配置"
        send_to_feishu({"msg_type": "text", "content": {"text": text}})

if __name__ == "__main__":
    main()
