"""Data fetching layer - 纯通达信数据源(pytdx)."""

import sys
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

import pandas as pd
import numpy as np
from datetime import datetime
import streamlit as st
from pytdx.hq import TdxHq_API
import re


# ── 连接 ──

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


def _is_valid_board_name(name: str) -> bool:
    if len(name) < 2:
        return False
    if '\x00' in name:
        return False
    if name[0].isdigit():
        return False
    if re.match(r'^[\s\d]+$', name):
        return False
    return True


# ── 全市场股票报价缓存 ──

@st.cache_data(ttl=300)
def _get_all_quotes() -> dict:
    """获取全市场股票实时报价，返回 {code: {price, chg_pct, b_vol, s_vol}}"""
    api = _get_tdx_api()
    # 从板块文件获取所有股票代码
    data = api.get_and_parse_block_info('block_gn.dat')
    codes = list(set(item['code'] for item in data))
    codes.sort()

    quotes = {}
    batch_size = 80
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        qlist = [(1 if c.startswith(('6', '9')) else 0, c) for c in batch]
        try:
            result = api.get_security_quotes(qlist)
            if result:
                for q in result:
                    c = q.get('code', '')
                    price = q.get('price', 0)
                    last_close = q.get('last_close', 0)
                    chg = (price - last_close) / last_close * 100 if last_close > 0 else 0
                    quotes[c] = {
                        'price': price,
                        'change_pct': round(chg, 2),
                        'b_vol': q.get('b_vol', 0),
                        's_vol': q.get('s_vol', 0),
                        'vol': q.get('vol', 0),
                    }
        except Exception:
            continue
    return quotes


# ── 概念板块列表 ──

@st.cache_data(ttl=3600)
def get_concept_boards() -> pd.DataFrame:
    """获取通达信概念板块列表"""
    api = _get_tdx_api()
    data = api.get_and_parse_block_info('block_gn.dat')
    seen = {}
    boards = []
    for item in data:
        name = item['blockname'].replace('\x00', '').strip()
        if name not in seen and _is_valid_board_name(name):
            seen[name] = True
            boards.append({"板块名称": name})
    return pd.DataFrame(boards)


# ── 板块全景排行（通达信数据） ──

@st.cache_data(ttl=300)
def get_board_rankings() -> pd.DataFrame:
    """获取所有板块的博弈排行（纯通达信计算）"""
    api = _get_tdx_api()
    data = api.get_and_parse_block_info('block_gn.dat')
    quotes = _get_all_quotes()
    name_map = _build_stock_name_map()

    # 构建板块→股票映射
    board_map = {}
    for item in data:
        name = item['blockname'].replace('\x00', '').strip()
        code = item['code']
        if not _is_valid_board_name(name):
            continue
        if name not in board_map:
            board_map[name] = []
        board_map[name].append(code)

    # 按板块聚合
    rows = []
    for bname, codes in board_map.items():
        sq = [quotes.get(c) for c in codes if c in quotes and quotes[c]['price'] > 0]
        if not sq:
            continue
        df = pd.DataFrame(sq)
        up = int((df['change_pct'] > 0).sum())
        down = int((df['change_pct'] < 0).sum())
        avg_chg = df['change_pct'].mean()
        total_b = df['b_vol'].sum()
        total_s = df['s_vol'].sum()

        # 资金博弈指标
        net_buy = total_b - total_s  # 净买入量
        ratio = total_b / max(total_s, 1)  # 内外盘比
        score = avg_chg * 0.4 + (ratio - 1) * 30 + ((up - down) / max(up + down, 1)) * 20

        # 领涨股
        top_idx = df['change_pct'].idxmax()
        top_code = codes[top_idx] if top_idx < len(codes) else ''
        top_name = name_map.get(top_code, '')
        top_chg = df.loc[top_idx, 'change_pct']

        rows.append({
            "板块名称": bname,
            "涨跌幅": round(avg_chg, 2),
            "上涨家数": up,
            "下跌家数": down,
            "外盘": total_b,
            "内盘": total_s,
            "内外盘比": round(ratio, 2),
            "净买入": net_buy,
            "博弈评分": round(max(0, min(100, score)), 1),
            "领涨股": top_name,
            "领涨股涨跌幅": round(top_chg, 2),
        })

    result = pd.DataFrame(rows)
    if len(result) > 0:
        result = result.sort_values("博弈评分", ascending=False).reset_index(drop=True)
        result.index = result.index + 1
        result.insert(0, "序号", result.index)
    return result


# ── 板块成分股 ──

def _build_stock_name_map() -> dict:
    """构建股票代码→名称映射"""
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


@st.cache_data(ttl=1800)
def get_concept_board_stocks(board_name: str) -> pd.DataFrame:
    """获取通达信概念板块成分股"""
    api = _get_tdx_api()
    name_map = _build_stock_name_map()
    data = api.get_and_parse_block_info('block_gn.dat')
    stocks = [s for s in data if s['blockname'].replace('\x00', '').strip() == board_name]

    result = []
    for s in stocks:
        code = s['code']
        name = name_map.get(code, "")
        if code and name:
            result.append({"股票代码": code, "股票名称": name})
    return pd.DataFrame(result)


# ── 板块历史指数 ──

@st.cache_data(ttl=3600)
def get_concept_board_history(symbol: str, days: int = 60) -> pd.DataFrame:
    """获取概念板块历史指数（通过个股聚合计算）"""
    stocks_df = get_concept_board_stocks(symbol)
    if len(stocks_df) == 0:
        return pd.DataFrame()
    codes = stocks_df["股票代码"].tolist()[:50]  # 取前50只代表性个股
    api = _get_tdx_api()

    all_dates = {}
    for code in codes:
        market = 1 if code.startswith(('6', '9')) else 0
        try:
            bars = api.get_security_bars(9, market, code, 0, days + 10)
            if bars:
                df = api.to_df(bars)
                if df.empty:
                    continue
                df.columns = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]
                df["日期"] = pd.to_datetime(df["日期"])
                for _, row in df.iterrows():
                    d = row["日期"]
                    if d not in all_dates:
                        all_dates[d] = {"总涨幅": 0, "count": 0}
                    all_dates[d]["总涨幅"] += row["收盘"]
                    all_dates[d]["count"] += 1
        except Exception:
            continue

    records = []
    for d, v in sorted(all_dates.items()):
        if v["count"] > 0:
            records.append({"日期": d, "收盘价": v["总涨幅"] / v["count"]})
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df = df.sort_values("日期").tail(days).reset_index(drop=True)
    if len(df) >= 2:
        df["涨跌幅(%)"] = df["收盘价"].pct_change() * 100
    return df


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


# ── 个股资金流向（通达信报价数据） ──

def get_stock_fund_flow(stock: str, market: str = "sh") -> pd.DataFrame:
    """获取个股资金流向（通达信b_vol/s_vol）"""
    api = _get_tdx_api()
    mkt = 1 if stock.startswith(('6', '9')) else 0
    q = api.get_security_quotes([(mkt, stock)])
    if not q:
        return pd.DataFrame()
    item = q[0]
    return pd.DataFrame([{
        "外盘": item.get('b_vol', 0),
        "内盘": item.get('s_vol', 0),
        "成交量": item.get('vol', 0),
        "最新价": item.get('price', 0),
    }])
