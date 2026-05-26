"""SQLite caching layer for stock data."""

import sqlite3
import pandas as pd
from datetime import datetime, date
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "cache.db")


def get_conn() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concept_boards (
            name TEXT PRIMARY KEY,
            code TEXT,
            updated_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concept_flow (
            period TEXT,
            data TEXT,
            updated_at TEXT,
            PRIMARY KEY (period)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_data (
            code TEXT,
            date TEXT,
            open REAL,
            close REAL,
            high REAL,
            low REAL,
            volume REAL,
            amount REAL,
            change_pct REAL,
            turnover_rate REAL,
            PRIMARY KEY (code, date)
        )
    """)

    conn.commit()
    conn.close()


def get_cache(key: str, max_age_hours: int = 4) -> str | None:
    """读取缓存"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT value, updated_at FROM cache WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    value, updated_at = row
    cached_time = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
    if (datetime.now() - cached_time).total_seconds() > max_age_hours * 3600:
        return None

    return value


def set_cache(key: str, value: str):
    """写入缓存"""
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT OR REPLACE INTO cache (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, now),
    )
    conn.commit()
    conn.close()


def save_concept_boards(df: pd.DataFrame):
    """缓存概念板块列表"""
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _, row in df.iterrows():
        conn.execute(
            "INSERT OR REPLACE INTO concept_boards (name, code, updated_at) VALUES (?, ?, ?)",
            (row["板块名称"], row["板块代码"], now),
        )
    conn.commit()
    conn.close()


def load_concept_boards() -> pd.DataFrame | None:
    """读取缓存的概念板块列表"""
    conn = get_conn()
    df = pd.read_sql("SELECT name AS 板块名称, code AS 板块代码 FROM concept_boards", conn)
    conn.close()
    if len(df) == 0:
        return None
    # 检查缓存是否过期（24小时）
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT updated_at FROM concept_boards LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        updated = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - updated).total_seconds() > 86400:
            return None
    return df


def get_cached_board_names() -> list[str]:
    """获取缓存中的板块名称列表"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM concept_boards ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


def is_db_initialized() -> bool:
    """检查数据库是否已初始化"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM concept_boards")
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0
