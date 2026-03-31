# 🌐 全球金融情报系统

每小时自动推送全球金融行情 + 财经快讯 + AI投资信号到飞书，完全免费，无需服务器。

## 📊 推送内容

| 模块 | 内容 |
|------|------|
| 📈 股市行情 | 上证、深证、沪深300、道琼斯、纳斯达克、标普500 |
| ₿ 加密货币 | BTC、ETH、SOL 实时价格 + 24h涨跌 |
| 🌍 宏观指标 | 黄金、原油、美债10Y收益率、美元/人民币 |
| 📰 财经快讯 | Reuters、CNBC、Bloomberg、Yahoo财经 RSS |
| 🧠 AI信号分析 | 关键词规则引擎 + VIP人物动态 + 技术信号 |

---

## 🚀 部署步骤（5分钟完成）

### 第一步：Fork 或上传到你的 GitHub 仓库

将以下文件放入你的 GitHub 仓库：
```
your-repo/
├── feishu_finance.py                      ← 主脚本
├── requirements.txt                       ← 依赖
└── .github/
    └── workflows/
        └── feishu_finance.yml             ← 定时任务
```

### 第二步：创建飞书机器人 Webhook

1. 打开飞书，进入你想接收消息的**群组**
2. 点击右上角 **「···」→ 设置 → 机器人 → 添加机器人」**
3. 选择「自定义机器人」，填写名称（如：金融情报）
4. 安全设置推荐选「**签名校验**」（更安全）
5. 复制 **Webhook URL** 和 **签名密钥**（如果开启了的话）

### 第三步：配置 GitHub Secrets

1. 打开你的 GitHub 仓库页面
2. 点击 **Settings → Secrets and variables → Actions → New repository secret**
3. 添加以下 Secret：

| Secret 名称 | 值 | 必填 |
|------------|-----|------|
| `FEISHU_WEBHOOK` | 飞书机器人的完整 Webhook URL | ✅ 必填 |
| `FEISHU_SECRET` | 飞书签名密钥 | 可选（开启签名校验才需要） |

### 第四步：启用 GitHub Actions

1. 进入仓库的 **Actions** 标签页
2. 如果提示「Workflows disabled」，点击 **Enable**
3. 点击 **「🌐 全球金融情报推送」→ Run workflow** 手动测试一次
4. 查看运行日志，确认推送成功 ✅

---

## ⏰ 推送时间表

默认每小时整点触发（UTC），对应北京时间：

| UTC | 北京时间 |
|-----|---------|
| 01:00 | 09:00 |
| 02:00 | 10:00 |
| ... | ... |
| 23:00 | 07:00(次日) |

如需修改推送频率，编辑 `.github/workflows/feishu_finance.yml` 中的 cron 表达式：
```yaml
# 每2小时推送一次
- cron: '0 */2 * * *'

# 只在工作日推送（周一到周五）
- cron: '0 * * * 1-5'

# 只推送北京时间 9:00 和 15:00（收盘后）
- cron: '0 1,7 * * *'
```

---

## 🔧 常见问题

**Q: Actions 运行成功但飞书没收到消息？**
- 检查 `FEISHU_WEBHOOK` Secret 是否正确（注意不要有多余空格）
- 飞书机器人如果开启了「关键词」安全校验，发送内容必须包含该关键词
- 如开启签名校验，需同时配置 `FEISHU_SECRET`

**Q: 数据显示 N/A？**
- Yahoo Finance 偶尔会限流，属正常现象，下次运行会恢复
- A股数据在非交易时间可能显示上一个交易日收盘价

**Q: 如何增加更多股票？**
- 编辑 `feishu_finance.py` 中的 `symbols` 字典，加入 Yahoo Finance 股票代码

**Q: GitHub Actions 免费额度够用吗？**
- 公开仓库：完全免费，无限制
- 私有仓库：每月 2000 分钟免费额度，每次运行约 1-2 分钟，每小时一次完全够用

---

## 📌 数据来源

- 股票/期货/汇率：Yahoo Finance（免费，无需 API Key）
- 加密货币：CoinGecko（免费，无需 API Key）
- 财经新闻：Reuters / CNBC / Bloomberg / Yahoo Finance RSS

---

> ⚠️ 免责声明：本系统数据仅供参考，不构成任何投资建议。投资有风险，决策需谨慎。
