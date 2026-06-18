# 个股分析追踪文档 — 设计文档

> 状态：设计中 | 日期：2026-06-18

## 需求背景

用户在飞书群中通过 `/analyze <股票代码>` 触发个股分析后，希望将分析结果归档到飞书文档中，形成持续追踪。核心诉求：

1. 同一只股票的多次分析归档到**同一个文档**，按时间倒序追加
2. 自动对比**上次分析的结论**，呈现评分/趋势/建议的变化
3. 列出两次分析之间的**关键事件**，解释为什么结论变了
4. 文档标题直接带结论，滚动浏览时一目了然
5. 预留**复盘笔记区**，方便后续手动补充

## 用户动线

```
用户在飞书群 @机器人 /analyze 600519
  │
  ├─ Bot 立即回复："✅ 分析任务已提交，完成后将更新追踪文档"
  │
  ├─ 后台异步执行完整分析流程（2-3分钟）
  │
  ├─ 分析完成 →
  │   ├─ 查找/创建 600519 追踪文档
  │   ├─ 提取上次分析结论 → 生成对比表
  │   ├─ 搜索期间重大事件
  │   ├─ 拼装完整分析块 → 追加到文档
  │   └─ 推送通知到群 + 飞书文档链接
  │
  └─ 用户在文档末尾 ✍️复盘笔记 区手动补充
```

## 文档结构

```
DSA自动日报/
└── 个股分析追踪/
    ├── 600519 贵州茅台.md
    ├── 300750 宁德时代.md
    └── ...
```

### 单文档内容

```markdown
# 600519 贵州茅台 — 分析追踪

---
## 📅 06-18 持有·震荡(55) → 短期企稳量能不足，观望为主

### 📊 本次结论
| 指标 | 值 |
|------|-----|
| 评分 | 55/100 |
| 趋势 | 震荡 |
| 建议 | 持有 |
| 收盘价 | 1632.00 |

### 📈 与上次 06-11 卖出·看空(45) 对比
| 指标 | 06-11 | 06-18 | 变化 |
|------|-------|-------|------|
| 评分 | 45 | 55 | +10 ▲ |
| 趋势 | 看空 | 震荡 | 改善 |
| 建议 | 卖出 | 持有 | 逆转 |
| 收盘 | 1580 | 1632 | +3.3% |

### 🔍 期间关键事件
- 06-12 中报预告净利润+18%，超预期
- 06-13 北向净买入 8.2 亿
- 06-16 突破 30 日均线压力位

### 📉 技术面
（完整技术指标数据...）

### ⚠️ 风险警报 / ✨ 利好催化
（完整分析内容...）

### 🎯 操作点位
（完整分析内容...）

### ✍️ 复盘笔记
> （留空，用户手动补充）

---
## 📅 06-11 卖出·看空(45) → 均线破位北向持续流出
...
```

### 标题格式

```
📅 MM-DD 建议·趋势(评分) → 一句话摘要
```

建议取值：买入/持有/观望/减仓/卖出
趋势取值：看多/震荡/看空

滚动示例：
```
06-18 持有·震荡(55) → 短期企稳量能不足
06-11 卖出·看空(45) → 均线破位北向流出
06-04 买入·看多(78) → 放量突破多头排列
```

## 文件规划

```
新增文件:
  src/services/stock_tracker.py      # 追踪编排器（主逻辑）
  src/repositories/tracking_repo.py  # SQLite 存取上次分析摘要
  src/schemas/tracking.py            # 数据模型

修改文件:
  src/feishu_doc.py                  # + find/create/append 追踪文档方法
  src/core/pipeline.py               # + 分析完成后回调钩子
  bot/commands/analyze.py            # 无需大改（已有异步提交）
  .env / .env.example                # + FEISHU_TRACKING_ENABLED
```

## 后端架构

```
                    ┌─────────────────────┐
                    │  Feishu Stream Bot   │
                    │  收到 /analyze 600519 │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  AnalyzeCommand      │
                    │  submit_analysis()   │──▶ 立即回复 "已提交"
                    └─────────┬───────────┘
                              │ async
                    ┌─────────▼───────────┐
                    │  StockAnalysisPipeline│
                    │  完整分析流程        │
                    └─────────┬───────────┘
                              │ 完成
                    ┌─────────▼───────────┐
                    │  分析完成回调钩子     │  ← 新增
                    │  on_analysis_done()  │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
    │ TrackingRepo   │ │ FeishuDoc  │ │ SearchService│
    │ 读上次分析摘要  │ │ 追加文档块 │ │ 搜期间事件   │
    └────────┬───────┘ └─────┬──────┘ └──────┬──────┘
             │               │               │
             └───────────────┼───────────────┘
                             │
                   ┌─────────▼───────────┐
                   │ 通知渠道 + 群消息     │
                   │ "追踪文档已更新 [链接]"│
                   └─────────────────────┘
```

## 数据模型

**tracking_repo (SQLite)**

```sql
CREATE TABLE IF NOT EXISTS stock_tracking (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code  TEXT NOT NULL,          -- '600519'
    stock_name  TEXT,                   -- '贵州茅台'
    doc_token   TEXT NOT NULL,          -- 飞书文档 token
    doc_url     TEXT,                   -- 飞书文档 URL
    last_score  INTEGER,                -- 上次评分 0-100
    last_trend  TEXT,                   -- 上次趋势: 看多/震荡/看空
    last_advice TEXT,                   -- 上次建议: 买入/持有/观望/减仓/卖出
    last_price  REAL,                   -- 上次收盘价
    last_date   TEXT,                   -- 上次分析日期 YYYY-MM-DD
    total_count INTEGER DEFAULT 1,      -- 累计分析次数
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tracking_code
    ON stock_tracking(stock_code);
```

## FeishuDocManager 新增方法

```python
class FeishuDocManager:

    # ========== 现有方法 ==========
    def get_or_create_folder() -> str
        """获取或创建 DSA自动日报 文件夹，返回 folder_token"""

    def create_daily_doc(title: str, content_md: str) -> Optional[str]
        """创建日报文档"""

    # ========== 新增方法 ==========

    def get_or_create_tracking_folder(self) -> str:
        """
        获取或创建「个股分析追踪」子文件夹
        位置: DSA自动日报/个股分析追踪/
        返回 folder_token
        """

    def find_tracking_doc(self, folder_token: str, stock_code: str) -> Optional[str]:
        """
        在追踪文件夹中按文件名前缀查找已有文档
        匹配规则: 文件名以 "{stock_code} " 开头
        返回 doc_token，不存在则 None
        """

    def create_tracking_doc(self, folder_token: str, stock_code: str,
                            stock_name: str) -> dict:
        """
        创建追踪文档
        标题: "600519 贵州茅台 — 分析追踪"
        返回 {"token": "...", "url": "..."}
        """

    def get_doc_content(self, doc_token: str) -> str:
        """
        读取文档完整 Markdown 内容
        用于追加前获取现有内容
        """

    def write_doc_content(self, doc_token: str, content_md: str) -> bool:
        """
        全量写入文档内容（替换）
        追加逻辑: 先 get → 拼接新块 → write
        """

    def append_analysis_block(self, doc_token: str,
                              markdown_block: str) -> bool:
        """
        向文档末尾追加一个分析块
        内部: get_doc_content() + markdown_block → write_doc_content()
        """
```

## 对比数据来源

| 对比项 | 数据来源 |
|--------|----------|
| 上次评分/趋势/建议 | `tracking_repo` (SQLite) |
| 上次收盘价 | `tracking_repo` |
| 本次完整分析 | `pipeline.run()` 返回结果 |
| 期间重大事件 | `search_service.search_events(code, start_date, end_date)` |

## 错误处理策略

| 场景 | 处理方式 |
|------|----------|
| 文档不存在（首次分析） | 新建追踪文档，跳过对比，标注"首次分析，无历史对比" |
| 上次分析数据缺失 | 跳过对比表，标注"历史数据暂不可用" |
| 事件搜索失败 | 跳过事件区，标注"事件数据暂不可用" |
| 文档追加 API 失败 | 记录 ERROR 日志，分析结果仍通过通知渠道正常推送 |
| 飞书 API 限流 (429) | 指数退避重试 3 次，仍失败则跳过归档，日志告警 |
| 整个追踪流程异常 | try/except 包裹，不阻断分析主流程和通知推送 |

## 新增配置

```env
# 个股分析追踪文档
# 分析完成后自动将结果归档到飞书文档，支持持续追踪和对比
FEISHU_TRACKING_ENABLED=true
```

配置项读取方式：`os.getenv("FEISHU_TRACKING_ENABLED", "false").lower() == "true"`

---

## 待确认 / 开放问题

1. **期间事件搜索**：调用现有 `search_service` 搜索两次分析日期之间的重大新闻。需要确认返回格式能否直接嵌入文档。

2. **文档追加 API 限制**：飞书文档 "Update Document Block" vs "全量写入" 两种方案。如果飞书不支持 block 级追加，用全量读取→拼接→写回的方式（文档大小增长缓慢，可接受）。

3. **并发安全**：同一股票短期内多次分析（用户连续发送命令），通过任务队列的 FIFO 顺序 + `tracking_repo` 的 SQLite 写入锁保证一致性。

4. **追踪文档数量上限**：飞书云盘对文件数量有限制，但个股追踪文档数量 ≤ 用户分析的股票种类数（通常几十只），远低于限制。
