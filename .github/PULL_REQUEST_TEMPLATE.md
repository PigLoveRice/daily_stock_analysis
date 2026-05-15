<!--
For Chinese contributors: 请直接用中文填写。
For English contributors: please fill in English. All fields marked (EN) accept English.
-->

## PR Type

- [ ] fix
- [ ] feat
- [ ] refactor
- [ ] docs
- [ ] chore
- [ ] test

## Background And Problem

请描述当前问题、影响范围与触发场景。  
*(EN) Describe the problem, its impact, and what triggers it.*

## Scope Of Change

请列出本 PR 修改的模块和文件范围。  
*(EN) List the modules and files changed in this PR.*

## Issue Link（拆分提交 / umbrella issue 请使用 Refs）

必须仅填写以下之一 / Fill in exactly one of:
- `Fixes #<issue_number>` / 非 umbrella issue 或修复问题直达（本 PR 全量修复该 issue）
- `Refs #<issue_number>` / umbrella issue / 多个子任务拆分场景（本 PR 属于分阶段推进时使用）。**umbrella issue 不要使用 Fixes，避免自动关闭总 issue** / For umbrella/split-plan issues, use `Refs` and avoid `Fixes` to prevent auto-closing parent issue.
- 无 Issue 时说明原因与验收标准 / If no issue, explain the motivation and acceptance criteria

> 统一约定：`Closes` 与 `Fixes` 在 GitHub 上语义一致，`#1309` 为 umbrella issue 的 PR 一律改为 `Refs #1309`，不得触发自动关闭该父 issue。

> 拆分场景（如 #1309）请固定填写 `Refs #<issue_number>`，除非本 PR 直接闭环且无需后续子任务，否则不得使用 `Fixes / Closes` 触发自动关闭。

示例 / Example:

- #1309 为 umbrella issue 分解场景：`Refs #1309`
- 仅在 PR 直接闭环 #1309 全部验收且无需后续拆分时才使用：`Fixes #1309`

> 建议：若你的 PR 是第 N 轮分解任务（如本仓库的 #1309），请务必避免 `Fixes`，固定使用 `Refs`，避免自动关闭总 issue。

## Verification Commands And Results

请填写你实际执行过的命令和关键结果（不要只写"已测试"）。  
*(EN) Paste the commands you actually ran and their key output (don't just write "tested"):*

```bash
# example
./scripts/ci_gate.sh
python -m pytest -m "not network"
```

关键输出/结论 / Key output & conclusion:

## Compatibility And Risk

请说明兼容性影响、潜在风险（如无请写 `None`）。  
*(EN) Describe compatibility impact and potential risks (write `None` if not applicable).*

- 如本 PR 为拆分任务（如 #1309），先填以下结论可减少审查歧义：
  - 本 PR 未新增/修改 `provider`、`model`、`Base URL`、`litellm_model`、`llm_model_list`、LiteLLM/LLM 运行时默认值，也未新增 `.env` 配置迁移或运行时保存/清理/回填逻辑。
  - 本轮未改动 `src/config.py`、`.env.example`、LLM provider/model/Base URL 默认值与 provider/list 配置清理/回填路径；兼容性风险判断以本次 `tests/test_extensions_runtime.py` 与 CI 结果为准。
  - 当前检测命中来自兼容性说明文本/既有关键词，不代表本 PR 新增模型/API 配置语义变更；如未改动 provider/model/Base URL/配置清理链路，请在结论中明确写明 `本 PR 未改动`。
  - 若外部模型/API 兼容检测有命中，多为仓库既有文档/说明里的关键词导致的静态告警，不代表本轮改动引入了新的模型/API 兼容语义或迁移；实际影响仅为现有运行时路径的常规回归覆盖范围。
  - 本 PR 回退路径：版本回滚到上一个版本（`revert this PR`），无须执行配置补偿步骤。

- 若本 PR 修改第三方模型 / API 的兼容语义、请求参数、路由前缀或 provider fallback，请提供**官方来源链接或公告**，并说明这是长期约束、当前运行时约束还是临时兼容处理。  
  *(EN) If this PR changes third-party model/API compatibility, request parameters, routing prefixes, or provider fallback behavior, include an **official source link or announcement** and clarify whether the rule is permanent, runtime-specific, or a temporary compatibility workaround.)*
- 若本 PR 依赖特定运行时 / 锁定依赖窗口（例如 LiteLLM 版本范围、OpenAI-compatible 路由、YAML alias 行为），请写明当前验证过的兼容范围与覆盖路径。  
  *(EN) If this PR depends on a specific runtime or pinned dependency window (for example a LiteLLM version range, OpenAI-compatible routing, or YAML alias behavior), state the compatibility window you verified and which code paths were covered.)*
- 若本 PR 触及运行时配置保存、清理、迁移或回填逻辑，请明确说明旧配置是否会被自动改写、清空、迁移或保持不变，以及用户如何恢复原行为。  
  *(EN) If this PR touches runtime config save/cleanup/migration/backfill logic, explicitly describe whether existing config is rewritten, cleared, migrated, or left intact, and how users can restore the previous behavior.)*

## Rollback Plan

请至少写一句可执行的回滚方案（必填）。  
*(EN) Provide at least one actionable rollback step (required).*

- 如果是兼容性修复，默认应写出**最小回滚方式**（例如 `revert this PR`），并说明是否需要额外回滚配置或数据迁移。  
  *(EN) For compatibility fixes, include the **minimal rollback path** (for example `revert this PR`) and whether any additional config or data rollback is required.)*

## EXTRACT_PROMPT Change (if applicable)

若本 PR 修改了 `src/services/image_stock_extractor.py` 中的 `EXTRACT_PROMPT`，请在此处粘贴完整变更后的 prompt。  
*If this PR changes `EXTRACT_PROMPT` in `src/services/image_stock_extractor.py`, paste the full updated prompt here:*

<details>
<summary>展开 / Expand: Full EXTRACT_PROMPT</summary>

```
(paste full prompt here)
```

</details>

## Checklist

- [ ] 本 PR 有明确动机和业务价值 / This PR has a clear motivation and value
- [ ] 已提供可复现的验证命令与结果 / Reproducible verification commands and results are included
- [ ] 已评估兼容性与风险 / Compatibility and risk have been assessed
- [ ] 本 PR 已按 umbrella issue 规则填写 Issue Link（若为拆分提交请使用 Refs） / Issue link follows umbrella split rule (use `Refs` when applicable)
- [ ] 已提供回滚方案 / A rollback plan is provided
- [ ] 若涉及用户可见变更，已同步更新相关文档与 `docs/CHANGELOG.md`；`README.md` 仅在首页级信息变化时更新，细节优先写入 `docs/*.md` / If user-visible changes are included, relevant docs and `docs/CHANGELOG.md` are updated; `README.md` is updated only for homepage-level changes, with details kept in `docs/*.md`
