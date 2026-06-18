# -*- coding: utf-8 -*-
"""
个股分析追踪 — 数据模型

用于 stock_tracker 和 tracking_repo 之间传递数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AnalysisSnapshot:
    """单次分析的关键摘要，用于存入 tracking_repo 供下次对比"""

    stock_code: str
    stock_name: str
    score: int                     # 0-100
    trend: str                     # 看多/震荡/看空
    advice: str                    # 买入/持有/观望/减仓/卖出
    close_price: float             # 收盘价
    one_sentence: str              # 一句话摘要

    analysis_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    # 从 LLM 结果中提取的原始字段，用于文档格式化
    risk_alerts: list[str] = field(default_factory=list)
    bullish_signals: list[str] = field(default_factory=list)
    operation_points: dict = field(default_factory=dict)
    technical_data: dict = field(default_factory=dict)
    raw_report_md: str = ""


@dataclass
class ComparisonRow:
    """对比表中的一行"""
    label: str
    previous: str
    current: str
    change: str                   # "+10 ▲" / "-5 ▼" / "持平"


@dataclass
class TrackingResult:
    """tracker 编排完成后的结果"""
    stock_code: str
    stock_name: str
    doc_url: str
    doc_token: str
    analysis_count: int
    is_first_analysis: bool
    comparison: list[ComparisonRow] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    error: Optional[str] = None
