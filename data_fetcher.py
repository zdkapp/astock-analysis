"""Data fetching layer - 纯通达信数据源(pytdx)."""

import sys, types as _types
if 'py_mini_racer' not in sys.modules:
    _fake = _types.ModuleType('py_mini_racer')
    class _MiniRacer:
        def __init__(self): pass
        def eval(self, code): return ''
        def call(self, *args, **kwargs): return ''
    _fake.MiniRacer = _MiniRacer; _fake.py_mini_racer = _fake
    sys.modules['py_mini_racer'] = _fake

import pandas as pd, numpy as np, re
from datetime import datetime, timedelta
import streamlit as st
from pytdx.hq import TdxHq_API
from collections import OrderedDict
import akshare as ak


def _get_tdx_api():
    api = TdxHq_API()
    for host, port in [('115.238.90.165', 7709), ('218.75.126.170', 7709)]:
        try: api.connect(host, port); return api
        except Exception: continue
    raise ConnectionError("无法连接通达信服务器")


# ── 全市场扫描：从880xxx指数获取板块排行 ──

def _load_ths_names() -> list:
    """加载同花顺概念名称（仅作为显示标签）"""
    try:
        df = ak.stock_board_concept_name_ths()
        return df['name'].tolist()
    except:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def get_board_rankings() -> pd.DataFrame:
    """扫描所有通达信880xxx概念指数，取前15名"""
    api = _get_tdx_api()
    block_data = _load_block_boards(api)
    index_boards = _scan_index_boards(api)
    ths_names = _load_ths_names()

    # 合并：有成分股的用成分股数据，只有指数的用指数数据
    # 先按涨幅排序
    index_boards.sort(key=lambda x: x['涨跌幅'], reverse=True)
    # 为前N个分配名称
    for i, ib in enumerate(index_boards):
        if i < len(ths_names):
            ib['display_name'] = ths_names[i]
        else:
            ib['display_name'] = f'GN{ib["code"]}'

    seen = set()
    rows = []
    for ib in index_boards:
        code = ib['code']
        name = ib['display_name']
        if code in block_data:
            bd = block_data[code]
            bd['id'] = name
            rows.append({**bd, 'index_code': code})
        else:
            rows.append({
                'id': name, '涨跌幅': ib['涨跌幅'],
                '上涨家数': ib['up'], '下跌家数': ib['down'],
                '外盘': 0, '内盘': 0, '内外盘比': 0, '净买入': 0,
                '博弈评分': ib['score'], '领涨股': '', '领涨股涨跌幅': 0,
                'index_code': code, 'stocks': []
            })
        seen.add(code)

    result = pd.DataFrame(rows)
    if result.empty: return result
    result = result.sort_values('涨跌幅', ascending=False).head(15).reset_index(drop=True)
    result.index += 1; result.insert(0, '序号', result.index)
    return result


def _scan_index_boards(api):
    """扫描所有880xxx指数"""
    boards = []
    for code in range(880500, 881000):
        try:
            bars = api.get_index_bars(9, 1, str(code), 0, 2)
            if not bars or len(bars) < 2: continue
            today, yesterday = bars[-1], bars[-2]
            close = today.get('close', 0); prev_close = yesterday.get('close', 1)
            chg = (close / prev_close - 1) * 100 if prev_close > 0 else 0
            up = today.get('up_count', 0); down = today.get('down_count', 0)
            total = up + down
            ratio = up / max(down, 1)
            score = chg * 0.5 + (ratio - 1) * 25 + ((up - down) / max(total, 1)) * 25
            boards.append({
                'code': str(code), '涨跌幅': round(chg, 2),
                'up': up, 'down': down, 'score': round(max(0, min(100, score)), 1),
            })
        except: continue
    return boards



def _load_block_boards(api) -> dict:
    """从block_gn.dat加载有完整成分股的板块 {index_code: data}"""
    raw = api.get_and_parse_block_info('block_gn.dat')
    valid = set(_build_name_map(api).keys())
    boards = OrderedDict()
    for item in raw:
        bt = str(item['block_type'])
        if bt not in boards:
            boards[bt] = {'id': f'GN{bt}', 'stocks': []}
        for part in item['code'].split('\x00'):
            digits = re.sub(r'\D', '', part)
            if len(digits) == 6:
                boards[bt]['stocks'].append(digits)
                break
    result = {}
    for bt, info in boards.items():
        unique = [c for c in set(info['stocks']) if c in valid]
        if len(unique) < 5: continue
        result[bt] = {'id': info['id'], 'stocks': unique}
    return result


def _build_name_map(api):
    name_map = {}
    for market in [0, 1]:
        count = api.get_security_count(market)
        for start in range(0, count, 500):
            for item in api.get_security_list(market, start) or []:
                c = str(item.get('code','')); n = item.get('name','').strip()
                if c and n: name_map[c] = n
    return name_map


# ── 对外接口 ──

def get_concept_boards() -> pd.DataFrame:
    r = get_board_rankings()
    return pd.DataFrame([{"板块名称": r.iloc[i].get('id', f'GN{r.iloc[i].get("index_code","")}')}
                         for i in range(len(r))]) if not r.empty else pd.DataFrame()


def get_concept_board_stocks(board_id: str) -> pd.DataFrame:
    api = _get_tdx_api()
    name_map = _build_name_map(api)
    # 从block_gn.dat查找
    code = board_id.replace('GN','')
    raw = api.get_and_parse_block_info('block_gn.dat')
    stocks = []
    for item in raw:
        if str(item['block_type']) != code: continue
        for part in item['code'].split('\x00'):
            digits = re.sub(r'\D', '', part)
            if len(digits) == 6:
                name = name_map.get(digits, '')
                if name: stocks.append({'股票代码': digits, '股票名称': name})
                break
    return pd.DataFrame(stocks)


def get_concept_board_history(symbol: str, days: int = 60) -> pd.DataFrame:
    return pd.DataFrame()


@st.cache_data(ttl=600)
def get_stock_history(symbol: str, days: int = 60) -> pd.DataFrame:
    api = _get_tdx_api()
    market = 1 if symbol.startswith(('6','9')) else 0
    bars = api.get_security_bars(9, market, symbol, 0, days+10)
    if not bars: return pd.DataFrame()
    df = api.to_df(bars)
    if df.empty: return df
    df.columns = ["日期","开盘","收盘","最高","最低","成交量","成交额"]
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").reset_index(drop=True)
    if len(df) >= 2:
        df["涨跌幅"] = df["收盘"].pct_change()*100
        df["涨跌额"] = df["收盘"].diff()
    else: df["涨跌幅"], df["涨跌额"] = 0.0, 0.0
    df["换手率"] = 0.0
    df["振幅"] = (df["最高"]-df["最低"])/df["最低"].replace(0,np.nan)*100
    return df.tail(days).reset_index(drop=True)


def get_stock_fund_flow(stock: str, market: str = "sh") -> pd.DataFrame:
    api = _get_tdx_api()
    mkt = 1 if stock.startswith(('6','9')) else 0
    q = api.get_security_quotes([(mkt, stock)])
    if not q: return pd.DataFrame()
    item = q[0]
    return pd.DataFrame([{"外盘":item.get('b_vol',0), "内盘":item.get('s_vol',0),
                         "成交量":item.get('vol',0), "最新价":item.get('price',0)}])
