# AlphaSift 选股集成说明

AlphaSift 作为第三方选股能力接入 DSA。DSA 默认不启用它，也不把 AlphaSift 的策略逻辑复制进主仓库；启用后只通过 `alphasift.dsa_adapter` 稳定适配层调用 AlphaSift。

## 当前方案

- 默认关闭：`ALPHASIFT_ENABLED=false`。
- 启用入口：设置页或选股页点击开启，或在 `.env` 中配置 `ALPHASIFT_ENABLED=true`。
- 安装来源：默认 `ALPHASIFT_INSTALL_SPEC=git+https://github.com/ZhuLinsen/alphasift.git@2c76b2b6074ae3bae01d52e5e830a4af3e3246b2`。
- 自动安装：Web 端开启时会调用后端 `/api/v1/alphasift/install`，后端只允许默认受信任来源自动安装；本地路径、wheel 或其他来源需要用户先手动安装到当前 Python 环境。
- 策略归属：策略列表、策略参数、选股计算和 LLM 重排由 AlphaSift 负责，DSA 只负责开关、安装、调用、展示和错误提示。
- LLM 环境：AlphaSift 直接复用 DSA 进程环境变量，包括 `LLM_CHANNELS`、`LITELLM_CONFIG`、各模型密钥和 `LLM_TIMEOUT_SEC`，不要求单独维护一套 AlphaSift `.env`。
- 风险提示：前端设置页和选股页展示第三方来源与投资风险说明；不会弹窗打断用户。

## AlphaSift 适配层要求

AlphaSift 需要提供 `alphasift.dsa_adapter` 模块，并保持以下稳定函数：

```python
def get_status() -> dict: ...
def list_strategies() -> list[dict]: ...
def screen(strategy: str, *, market: str = "cn", max_results: int = 20, use_llm: bool = True) -> dict: ...
```

`get_status()` 建议返回：

```json
{
  "available": true,
  "contract_version": "1",
  "version": "0.2.0",
  "strategy_count": 8,
  "supported_markets": ["cn"]
}
```

`list_strategies()` 至少返回 `id`，建议同时返回 `name`、`description`、`category`、`tags`、`market_scope`。

`screen()` 返回值建议包含：

```json
{
  "run_id": "20260531-...",
  "strategy": "dual_low",
  "market": "cn",
  "snapshot_count": 100,
  "after_filter_count": 5,
  "llm_ranked": true,
  "llm_coverage": 1.0,
  "warnings": [],
  "source_errors": [],
  "candidates": []
}
```

候选项建议包含 `code`、`name`、`score`、`reason`、`risk_level`、`risk_flags`、`price`、`change_pct`、`amount`、`industry`、`factor_scores`，以及 LLM 字段：`llm_score`、`llm_confidence`、`llm_thesis`、`llm_catalysts`、`llm_risks`、`llm_watch_items` 等。

AlphaSift 侧已在 `ZhuLinsen/alphasift@2c76b2b6074ae3bae01d52e5e830a4af3e3246b2` 提供 DSA adapter contract，并支持复用 DSA 的 `LLM_TIMEOUT_SEC`。

## DSA 后端行为

- `/api/v1/alphasift/status`：返回开关、可用性、默认安装来源标识和适配层元信息；不会暴露完整安装来源。
- `/api/v1/alphasift/install`：只在启用后执行；只允许默认受信任安装来源自动安装；安装后校验适配层。
- `/api/v1/alphasift/strategies`：读取 AlphaSift 策略列表。
- `/api/v1/alphasift/screen`：调用适配层 `screen(..., use_llm=True)`，返回候选、运行元信息和 LLM 展示字段。

错误策略：

- 未开启返回 `403 alphasift_disabled`。
- 安装来源不受信任返回 `403 alphasift_install_spec_not_allowed`。
- AlphaSift 未安装、缺少适配层或适配层不可调用返回 `424`。
- 市场或策略被适配层拒绝时返回 `400/422`。
- 运行失败返回 `424 alphasift_screen_failed`。

## Web 行为

- 设置页提供 AlphaSift 开关，开启后写入 `ALPHASIFT_ENABLED=true` 并触发依赖检查。
- 选股页未开启时展示开启按钮；开启后读取 AlphaSift 策略列表。
- 当前只暴露 A 股 `cn` 市场。
- 默认返回数量为 3，避免一次选股过慢或结果过多。
- 选股请求使用独立长超时，避免 LLM 重排未完成时被普通 API 超时截断。
- 结果页展示运行 ID、样本数量、过滤后数量、LLM 是否重排、LLM 覆盖率；展开候选后展示 LLM 判断、主要因子、风险、关注项和催化因素。

## 桌面端说明

源码运行的桌面端复用同一个 Python 后端环境，因此与 Web 端一致，可以通过设置页或 `.env` 开启。

打包后的桌面端不应依赖运行期 `pip install` 作为唯一方案，因为用户机器可能没有 git、pip 网络访问或可写 Python 环境。更稳妥的发布方式是：打包时把 AlphaSift 作为可选 Python 依赖一起放入发行产物，默认仍关闭；用户在 Web 设置页开启后只切换 `ALPHASIFT_ENABLED` 并检查适配层可用性。

## 验证记录

- `python -m pytest tests/test_alphasift_api.py -q`
- `python -m py_compile api/v1/endpoints/alphasift.py tests/test_alphasift_api.py src/config.py src/core/config_registry.py`
- `cd apps/dsa-web && npm.cmd test -- alphasift.test.ts StockScreeningPage.test.tsx SettingsPage.test.tsx --run`
- `cd apps/dsa-web && npm.cmd run lint`
- `cd apps/dsa-web && npm.cmd run build`

本地联调已验证：`/api/v1/alphasift/status` 可读取适配层，`/api/v1/alphasift/screen` 在 `use_llm=True` 下返回 LLM 重排结果，选股页可运行并展开查看候选详情。

## 回滚

- 关闭功能：设置页关闭 AlphaSift，或配置 `ALPHASIFT_ENABLED=false`。
- 禁止自动安装：移除或清空 `ALPHASIFT_INSTALL_SPEC`，或保持默认关闭。
- 回滚代码：移除 AlphaSift API 注册、Web 选股入口和相关配置项即可恢复到集成前流程；默认关闭状态下不会影响原有股票分析、报告生成和通知流程。
