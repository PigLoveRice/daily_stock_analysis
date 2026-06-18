# -*- coding: utf-8 -*-
"""
个股分析追踪 — 数据访问层

使用 SQLite 存储每次分析的摘要，供下次分析时做对比。
复用项目已有的 stock_analysis.db，新建 stock_tracking 表。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.schemas.tracking import AnalysisSnapshot

logger = logging.getLogger(__name__)

# 复用项目已有的数据库文件
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stock_analysis.db"

# 线程本地连接，避免并发冲突
_local = threading.local()

DDL = """
CREATE TABLE IF NOT EXISTS stock_tracking (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code  TEXT NOT NULL,
    stock_name  TEXT,
    doc_token   TEXT NOT NULL,
    doc_url     TEXT,
    last_score  INTEGER,
    last_trend  TEXT,
    last_advice TEXT,
    last_price  REAL,
    last_date   TEXT,
    one_sentence TEXT,
    total_count INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tracking_code
    ON stock_tracking(stock_code);
"""


class TrackingRepository:
    """个股追踪数据访问层"""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = str(db_path or DB_PATH)
        self._init_table()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(_local, "conn") or _local.conn is None:
            _local.conn = sqlite3.connect(self._db_path)
            _local.conn.row_factory = sqlite3.Row
        return _local.conn

    def _init_table(self) -> None:
        try:
            conn = self._get_conn()
            conn.executescript(DDL)
            conn.commit()
        except Exception as e:
            logger.error("[TrackingRepo] 初始化表失败: %s", e)

    # ── 查询 ──────────────────────────────────────────────

    def get_by_code(self, stock_code: str) -> Optional[dict]:
        """获取某只股票的追踪记录，不存在则返回 None"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM stock_tracking WHERE stock_code = ?",
                (stock_code.upper(),)
            ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error("[TrackingRepo] 查询失败: %s", e)
            return None

    # ── 写入 ──────────────────────────────────────────────

    def upsert(self, stock_code: str, stock_name: str,
               doc_token: str, doc_url: str, snapshot: AnalysisSnapshot) -> bool:
        """
        插入或更新追踪记录。
        如果该股票已有记录，则覆盖上次分析摘要并递增计数。
        """
        stock_code = stock_code.upper()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            conn = self._get_conn()
            existing = conn.execute(
                "SELECT id, total_count FROM stock_tracking WHERE stock_code = ?",
                (stock_code,)
            ).fetchone()

            if existing:
                new_count = existing["total_count"] + 1
                conn.execute(
                    """UPDATE stock_tracking
                       SET stock_name = ?, last_score = ?, last_trend = ?,
                           last_advice = ?, last_price = ?, last_date = ?,
                           one_sentence = ?, total_count = ?, updated_at = ?
                       WHERE stock_code = ?""",
                    (stock_name, snapshot.score, snapshot.trend,
                     snapshot.advice, snapshot.close_price,
                     snapshot.analysis_date, snapshot.one_sentence,
                     new_count, now, stock_code)
                )
            else:
                conn.execute(
                    """INSERT INTO stock_tracking
                       (stock_code, stock_name, doc_token, doc_url,
                        last_score, last_trend, last_advice, last_price,
                        last_date, one_sentence, total_count, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                    (stock_code, stock_name, doc_token, doc_url,
                     snapshot.score, snapshot.trend, snapshot.advice,
                     snapshot.close_price, snapshot.analysis_date,
                     snapshot.one_sentence, now, now)
                )

            conn.commit()
            logger.info("[TrackingRepo] %s 追踪记录已更新 (第 %d 次)",
                        stock_code,
                        existing["total_count"] + 1 if existing else 1)
            return True

        except Exception as e:
            logger.error("[TrackingRepo] 写入失败: %s", e)
            return False

    def get_comparison_data(self, stock_code: str) -> Optional[dict]:
        """获取用于对比的上次分析摘要"""
        row = self.get_by_code(stock_code)
        if not row:
            return None
        return {
            "score": row.get("last_score"),
            "trend": row.get("last_trend"),
            "advice": row.get("last_advice"),
            "price": row.get("last_price"),
            "date": row.get("last_date"),
            "one_sentence": row.get("one_sentence"),
            "total_count": row.get("total_count", 0),
        }
