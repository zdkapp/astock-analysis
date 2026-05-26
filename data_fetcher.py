"""Data fetching layer - 通达信数据源(pytdx) + 资金流向(同花顺)."""

import sys
# py_mini_racer在Python 3.14有循环导入bug，提前打补丁
import types as _types
if 'py_mini_racer' not in sys.modules:
    _fake = _types.ModuleType('py_mini_racer')
    class _MiniRacer:
        def __init__(self): pass
        def eval(self, code): return ''
        def call(self, *args, **kwargs): return ''
    _fake.MiniRacer = _MiniRacer
    _fake.py_mini_racer = _fake
    sys.modules['py_mini_racer'] = _fake

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st
from pytdx.hq import TdxHq_API


# ── 通达信连接 ──

@st.cache_resource
def _get_tdx_api():
    api = TdxHq_API()
    for host, port in [('115.238.90.165', 7709), ('218.75.126.170', 7709)]:
        try:
            api.connect(host, port)
            return api
        except Exception:
            continue
    raise ConnectionError("无法连接通达信服务器")


@st.cache_resource
def _build_stock_name_map():
    """构建全市场股票代码→名称映射"""
    api = _get_tdx_api()
    name_map = {}
    for market in [0, 1]:
        count = api.get_security_count(market)
        for start in range(0, count, 500):
            data = api.get_security_list(market, start)
            if data:
                for item in data:
                    code = str(item.get('code', ''))
                    name = item.get('name', '').strip()
                    if code and name:
                        name_map[code] = name
    return name_map


def _get_stock_name(code: str) -> str:
    """获取单只股票名称"""
    name_map = _build_stock_name_map()
    return name_map.get(code, "")


# ── 概念板块列表 ──

@st.cache_data(ttl=3600)
def get_concept_boards() -> pd.DataFrame:
    """获取通达信概念板块列表"""
    api = _get_tdx_api()
    data = api.get_and_parse_block_info('block_gn.dat')
    seen = {}
    boards = []
    for item in data:
        name = item['blockname']
        if name not in seen and len(name) >= 2:
            seen[name] = True
            boards.append({"板块名称": name})
    return pd.DataFrame(boards)


# ── 板块成分股 ──

@st.cache_data(ttl=1800)
def get_concept_board_stocks(board_name: str) -> pd.DataFrame:
    """获取通达信概念板块成分股"""
    api = _get_tdx_api()
    name_map = _build_stock_name_map()
    data = api.get_and_parse_block_info('block_gn.dat')
    stocks = [s for s in data if s['blockname'] == board_name]

    result = []
    for s in stocks:
        code = s['code']
        name = name_map.get(code, "")
        if code and name:
            result.append({"股票代码": code, "股票名称": name})
    return pd.DataFrame(result)


# ── 资金流向（同花顺） ──

@st.cache_data(ttl=1800)
def get_concept_fund_flow(period: str = "即时") -> pd.DataFrame:
    """获取概念板块资金流向"""
    df = ak.stock_fund_flow_concept(symbol=period)
    cols = ["序号", "板块名称", "板块指数", "涨跌幅", "主力净流入", "超大单净流入",
            "大单净流入", "中单净流入"]
    if len(df.columns) > 8:
        cols.append("小单净流入")
    if len(df.columns) > 9:
        cols.extend(["领涨股", "领涨股涨跌幅"])
    df.columns = cols[:len(df.columns)]
    return df


# ── 板块历史指数（同花顺，暂用） ──

@st.cache_data(ttl=3600)
def get_concept_board_history(symbol: str, days: int = 60) -> pd.DataFrame:
    """获取概念板块历史指数"""
    try:
        df = ak.stock_board_concept_index_ths(symbol=symbol)
        df.columns = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"]
        df["日期"] = pd.to_datetime(df["日期"])
        return df.sort_values("日期").tail(days).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


# ── 个股历史行情（通达信） ──

@st.cache_data(ttl=600)
def get_stock_history(symbol: str, days: int = 60) -> pd.DataFrame:
    """获取个股历史行情"""
    api = _get_tdx_api()
    market = 1 if symbol.startswith(('6', '9')) else 0
    bars = api.get_security_bars(9, market, symbol, 0, days + 10)
    if not bars:
        return pd.DataFrame()

    df = api.to_df(bars)
    if df.empty:
        return df
    df.columns = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").reset_index(drop=True)

    if len(df) >= 2:
        df["涨跌幅"] = df["收盘"].pct_change() * 100
        df["涨跌额"] = df["收盘"].diff()
    else:
        df["涨跌幅"] = 0.0
        df["涨跌额"] = 0.0
    df["换手率"] = 0.0
    df["振幅"] = (df["最高"] - df["最低"]) / df["最低"].replace(0, np.nan) * 100

    return df.tail(days).reset_index(drop=True)


# ── 个股资金流向 ──

def get_stock_fund_flow(stock: str, market: str = "sh") -> pd.DataFrame:
    """获取个股资金流向（东方财富）"""
    return ak.stock_individual_fund_flow(stock=stock, market=market)
