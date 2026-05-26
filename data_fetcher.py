"""Data fetching layer - all AkShare calls wrapped with caching."""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st


def get_concept_boards() -> pd.DataFrame:
    """获取同花顺概念板块列表"""
    df = ak.stock_board_concept_name_ths()
    df.columns = ["板块名称", "板块代码"]
    return df


def get_concept_board_history(symbol: str, days: int = 20) -> pd.DataFrame:
    """获取概念板块历史指数数据

    Args:
        symbol: 板块名称
        days: 最近N天数据
    """
    end = datetime.now()
    start = end - timedelta(days=days * 2)  # 多取一些以免非交易日
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    df = ak.stock_board_concept_index_ths(symbol=symbol)
    df.columns = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"]
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").tail(days).reset_index(drop=True)
    return df


def get_concept_board_summary() -> pd.DataFrame:
    """获取同花顺概念板块每日快照（涨跌幅、领涨股等）"""
    df = ak.stock_board_concept_summary_ths()
    # 重命名列
    col_map = {
        "日期": "日期",
        "涨跌幅": "涨跌幅",
        "上涨数": "上涨数",
        "领涨股": "领涨股",
        "成分股总数": "成分股总数",
    }
    # 实际列名可能不同，取前几列重命名
    df.columns = list(col_map.values())[: len(df.columns)]
    return df


def get_concept_fund_flow(period: str = "即时") -> pd.DataFrame:
    """获取同花顺概念板块资金流向

    Args:
        period: 即时 / 3日排行 / 5日排行 / 10日排行 / 20日排行
    """
    df = ak.stock_fund_flow_concept(symbol=period)
    # 重命名列
    cols = ["序号", "板块名称", "板块指数", "涨跌幅", "主力净流入", "超大单净流入",
            "大单净流入", "中单净流入", "小单净流入", "领涨股", "领涨股涨跌幅"]
    df.columns = [c for c in cols if c][: len(df.columns)]
    return df


def get_concept_board_stocks(symbol: str) -> pd.DataFrame:
    """获取概念板块成分股

    Args:
        symbol: 板块名称
    """
    df = ak.stock_board_concept_info_ths(symbol=symbol)
    return df


def get_stock_history(symbol: str, days: int = 60) -> pd.DataFrame:
    """获取个股历史行情

    Args:
        symbol: 股票代码
        days: 最近N天
    """
    end = datetime.now()
    start = end - timedelta(days=days * 2)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    # 判断市场前缀
    if symbol.startswith("6"):
        full_symbol = f"sh{symbol}"
    elif symbol.startswith("0") or symbol.startswith("3"):
        full_symbol = f"sz{symbol}"
    else:
        full_symbol = f"sh{symbol}"

    df = ak.stock_zh_a_daily(symbol=full_symbol,
                             start_date=start_str, end_date=end_str,
                             adjust="qfq")
    df.columns = ["日期", "开盘", "最高", "最低", "收盘", "成交量",
                  "成交额", "流通股本", "换手率"]
    df["日期"] = pd.to_datetime(df["日期"])
    # 计算涨跌幅
    if len(df) >= 2:
        df["涨跌幅"] = df["收盘"].pct_change() * 100
        df["涨跌额"] = df["收盘"].diff()
    else:
        df["涨跌幅"] = 0.0
        df["涨跌额"] = 0.0
    return df.sort_values("日期").tail(days).reset_index(drop=True)


def get_stock_fund_flow(stock: str, market: str = "sh") -> pd.DataFrame:
    """获取个股资金流向

    Args:
        stock: 股票代码
        market: sh/sz/bj
    """
    df = ak.stock_individual_fund_flow(stock=stock, market=market)
    return df


def get_daily_concept_flow() -> pd.DataFrame | None:
    """获取当日概念板块资金流向（用于板块扫描页）"""
    try:
        return get_concept_fund_flow("即时")
    except Exception:
        return None
