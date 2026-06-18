# -*- coding: utf-8 -*-
"""
个股分析追踪 — 编排器

分析完成后自动将结果归档到飞书追踪文档。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.repositories.tracking_repo import TrackingRepository
from src.schemas.tracking import AnalysisSnapshot, ComparisonRow, TrackingResult

logger = logging.getLogger(__name__)

# 单例缓存
_doc_manager = None
_tracking_repo: Optional[TrackingRepository] = None


def _is_tracking_enabled() -> bool:
    return os.getenv("FEISHU_TRACKING_ENABLED", "false").lower() == "true"


def _get_doc_manager():
    """延迟初始化 FeishuDocManager（避免启动时导入开销）"""
    global _doc_manager
    if _doc_manager is None:
        from src.feishu_doc import FeishuDocManager
        _doc_manager = FeishuDocManager()
    return _doc_manager


def _get_repo() -> TrackingRepository:
    global _tracking_repo
    if _tracking_repo is None:
        _tracking_repo = TrackingRepository()
    return _tracking_repo


def _extract_snapshot(result) -> AnalysisSnapshot:
    """从 AnalysisResult 提取分析快照"""
    dashboard = getattr(result, 'dashboard', None) or {}

    # 提取一句话摘要
    one_sentence = ""
    if isinstance(dashboard, dict):
        core = dashboard.get('core_conclusion', {})
        if isinstance(core, dict):
            one_sentence = core.get('one_sentence', '')

    # 提取风险/利好
    risk_alerts = []
    bullish_signals = []
    if isinstance(dashboard, dict):
        intelligence = dashboard.get('intelligence', {})
        if isinstance(intelligence, dict):
            risk_alerts = intelligence.get('risk_alerts', [])
            bullish_signals = intelligence.get('bullish_signals', [])

    # 提取操作点位
    operation_points = {}
    if isinstance(dashboard, dict):
        core = dashboard.get('core_conclusion', {})
        if isinstance(core, dict):
            operation_points = core.get('position_advice', {})

    return AnalysisSnapshot(
        stock_code=getattr(result, 'code', ''),
        stock_name=getattr(result, 'name', ''),
        score=getattr(result, 'sentiment_score', 50),
        trend=getattr(result, 'trend_prediction', '震荡'),
        advice=getattr(result, 'operation_advice', '观望'),
        close_price=getattr(result, 'current_price', 0.0) or 0.0,
        one_sentence=one_sentence or getattr(result, 'analysis_summary', ''),
        risk_alerts=risk_alerts if isinstance(risk_alerts, list) else [],
        bullish_signals=bullish_signals if isinstance(bullish_signals, list) else [],
        operation_points=operation_points if isinstance(operation_points, dict) else {},
    )


def _search_events(stock_code: str, stock_name: str,
                   from_date: str, to_date: str) -> List[str]:
    """搜索两次分析之间的重大事件"""
    try:
        from src.search_service import SearchService
        svc = SearchService()

        response = svc.search_stock_events(
            stock_code=stock_code,
            stock_name=stock_name,
        )

        if not response or not response.success or not response.results:
            return []

        events = []
        for r in response.results[:5]:
            title = getattr(r, 'title', '') or ''
            source = getattr(r, 'source', '') or ''
            date_str = getattr(r, 'published_date', '') or ''
            date_short = date_str[:10] if date_str else ''
            line = f"- {date_short} {title}"
            if source:
                line += f" ({source})"
            events.append(line)
        return events

    except Exception as e:
        logger.warning("[StockTracker] 搜索期间事件失败: %s", e)
        return []


def _build_comparison_table(prev: Optional[dict],
                            snapshot: AnalysisSnapshot) -> List[ComparisonRow]:
    """生成对比表"""
    if not prev:
        return []

    def _fmt_change(old_val, new_val, is_score=False):
        """格式化变化值，带箭头"""
        try:
            if is_score:
                diff = int(new_val) - int(old_val)
            else:
                diff = float(new_val) - float(old_val)
            arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "")
            return f"{diff:+.1f} {arrow}" if not is_score else f"{diff:+d} {arrow}"
        except (ValueError, TypeError):
            return "—"

    rows = []

    if prev.get("score") is not None and snapshot.score:
        rows.append(ComparisonRow(
            label="评分", previous=str(prev["score"]),
            current=str(snapshot.score),
            change=_fmt_change(prev["score"], snapshot.score, is_score=True),
        ))

    if prev.get("trend") and snapshot.trend:
        change = "改善" if snapshot.trend != prev["trend"] else "持平"
        if "看多" in snapshot.trend and "看空" in prev["trend"]:
            change = "逆转 ▲"
        rows.append(ComparisonRow(
            label="趋势", previous=prev["trend"],
            current=snapshot.trend, change=change,
        ))

    if prev.get("advice") and snapshot.advice:
        rows.append(ComparisonRow(
            label="建议", previous=prev["advice"],
            current=snapshot.advice,
            change="变化" if snapshot.advice != prev["advice"] else "持平",
        ))

    if prev.get("price") and snapshot.close_price:
        rows.append(ComparisonRow(
            label="收盘", previous=str(prev["price"]),
            current=str(snapshot.close_price),
            change=_fmt_change(prev["price"], snapshot.close_price),
        ))

    return rows


def _build_markdown_block(snapshot: AnalysisSnapshot,
                          comparison: List[ComparisonRow],
                          events: List[str],
                          prev_date: Optional[str] = None) -> str:
    """构建要追加的 Markdown 分析块"""

    # 标题行
    lines = [
        f"## 📅 {snapshot.analysis_date[-5:]} {snapshot.advice}·{snapshot.trend}"
        f"({snapshot.score}) → {snapshot.one_sentence}",
        "",
    ]

    # 本次结论
    lines.append("### 📊 本次结论")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 评分 | {snapshot.score}/100 |")
    lines.append(f"| 趋势 | {snapshot.trend} |")
    lines.append(f"| 建议 | {snapshot.advice} |")
    if snapshot.close_price:
        lines.append(f"| 收盘价 | {snapshot.close_price:.2f} |")
    lines.append("")

    # 对比表
    if comparison:
        prev_label = prev_date[-5:] if prev_date else "上次"
        lines.append(f"### 📈 与 {prev_label} 对比")
        lines.append("")
        lines.append(f"| 指标 | {prev_label} | 本次 | 变化 |")
        lines.append(f"|------|------|------|------|")
        for row in comparison:
            lines.append(f"| {row.label} | {row.previous} | {row.current} | {row.change} |")
        lines.append("")

    # 期间事件
    if events:
        lines.append("### 🔍 期间关键事件")
        lines.append("")
        for e in events:
            lines.append(e)
        lines.append("")

    # 风险 & 利好
    if snapshot.risk_alerts:
        lines.append("### ⚠️ 风险警报")
        lines.append("")
        for r in snapshot.risk_alerts:
            lines.append(f"- {r}")
        lines.append("")

    if snapshot.bullish_signals:
        lines.append("### ✨ 利好催化")
        lines.append("")
        for b in snapshot.bullish_signals:
            lines.append(f"- {b}")
        lines.append("")

    # 操作点位
    if snapshot.operation_points:
        lines.append("### 🎯 操作点位")
        lines.append("")
        for k, v in snapshot.operation_points.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    # 复盘笔记区
    lines.append("### ✍️ 复盘笔记")
    lines.append("")
    lines.append("> （点击编辑，记录你的复盘思考）")
    lines.append("")

    return "\n".join(lines)


def archive_stock_analysis(result) -> Optional[TrackingResult]:
    """
    分析完成回调：将结果归档到飞书追踪文档。

    Args:
        result: AnalysisResult 对象

    Returns:
        TrackingResult 或 None（追踪未启用/失败时）
    """

    if not _is_tracking_enabled():
        logger.debug("[StockTracker] 追踪功能未启用，跳过归档")
        return None

    # 提取快照
    snapshot = _extract_snapshot(result)

    if not snapshot.stock_code:
        logger.warning("[StockTracker] 无法提取股票代码，跳过归档")
        return None

    stock_code = snapshot.stock_code.upper()
    stock_name = snapshot.stock_name or stock_code

    logger.info("[StockTracker] 开始归档 %s %s ...", stock_code, stock_name)

    try:
        # 1. 获取 FeishuDocManager 和追踪文件夹
        doc_mgr = _get_doc_manager()
        if not doc_mgr.is_configured():
            logger.warning("[StockTracker] 飞书未配置，跳过归档")
            return None

        folder_token = doc_mgr.get_or_create_tracking_folder()
        if not folder_token:
            logger.error("[StockTracker] 无法获取追踪文件夹")
            return None

        # 2. 查找或创建追踪文档
        doc = doc_mgr.find_tracking_doc(folder_token, stock_code)
        is_first = False

        if not doc:
            doc = doc_mgr.create_tracking_doc(folder_token, stock_code, stock_name)
            is_first = True
            if not doc:
                logger.error("[StockTracker] 无法创建追踪文档")
                return None

        # 3. 获取上次分析数据
        repo = _get_repo()
        prev_data = repo.get_comparison_data(stock_code)

        # 4. 搜索期间事件（有上次数据时才搜）
        events: List[str] = []
        if prev_data and prev_data.get("date"):
            events = _search_events(
                stock_code, stock_name,
                prev_data["date"], snapshot.analysis_date,
            )

        # 5. 生成对比表
        comparison = _build_comparison_table(prev_data, snapshot)

        # 6. 构建 Markdown 块
        md_block = _build_markdown_block(
            snapshot, comparison, events,
            prev_date=prev_data.get("date") if prev_data else None,
        )

        # 7. 追加到文档
        success = doc_mgr.append_analysis_block(doc["token"], md_block)
        if not success:
            logger.error("[StockTracker] 追加分析块失败")
            return None

        # 8. 更新本地追踪记录
        repo.upsert(
            stock_code=stock_code,
            stock_name=stock_name,
            doc_token=doc["token"],
            doc_url=doc["url"],
            snapshot=snapshot,
        )

        analysis_count = (prev_data.get("total_count", 0) + 1) if prev_data else 1

        logger.info("[StockTracker] %s 归档完成 (第 %d 次)", stock_code, analysis_count)

        return TrackingResult(
            stock_code=stock_code,
            stock_name=stock_name,
            doc_url=doc["url"],
            doc_token=doc["token"],
            analysis_count=analysis_count,
            is_first_analysis=is_first,
            comparison=comparison,
            events=events,
        )

    except Exception as e:
        logger.error("[StockTracker] 归档异常: %s", e, exc_info=True)
        return TrackingResult(
            stock_code=stock_code,
            stock_name=stock_name,
            doc_url="",
            doc_token="",
            analysis_count=0,
            is_first_analysis=True,
            error=str(e),
        )
