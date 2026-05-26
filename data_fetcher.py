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

import pandas as pd, numpy as np
from datetime import datetime
import streamlit as st
from pytdx.hq import TdxHq_API
from collections import OrderedDict


@st.cache_resource
def _get_tdx_api():
    api = TdxHq_API()
    for host, port in [('115.238.90.165', 7709), ('218.75.126.170', 7709)]:
        try: api.connect(host, port); return api
        except Exception: continue
    raise ConnectionError("无法连接通达信服务器")


# ── 板块核心数据 ──

@st.cache_data(ttl=3600)
def _get_board_data() -> list[dict]:
    """获取板块列表，每个板块包含 {id, name, stocks}"""
    api = _get_tdx_api()
    raw = api.get_and_parse_block_info('block_gn.dat')
    boards = OrderedDict()
    for item in raw:
        bt = str(item['block_type'])
        name = item['blockname'].replace('\x00', '').strip()
        has_cn = any(ord(c) > 127 for c in name)
        if bt not in boards:
            uid = name if has_cn else f"GN{bt}"
            boards[bt] = {'id': uid, 'raw_name': name, 'stocks': []}
        boards[bt]['stocks'].append(item['code'])
    # 去重股票，过滤少于5只的
    result = []
    for bt, info in boards.items():
        unique = list(set(info['stocks']))
        if len(unique) >= 5:
            result.append({'id': info['id'], 'raw_name': info['raw_name'], 'stocks': unique})
    return result


def get_concept_boards() -> pd.DataFrame:
    boards = _get_board_data()
    return pd.DataFrame([{"板块名称": b['id']} for b in boards])


# ── 全市场报价 ──

@st.cache_data(ttl=300, show_spinner=False)
def _get_all_quotes() -> dict:
    api = _get_tdx_api()
    # 重连确保连接有效
    try: api.do_heartbeat()
    except: api.connect(api.client.host, api.client.port)
    all_codes = list(set(c for b in _get_board_data() for c in b['stocks']))
    quotes = {}
    for i in range(0, len(all_codes), 80):
        batch = all_codes[i:i+80]
        qlist = [(1 if c.startswith(('6','9')) else 0, c) for c in batch]
        try:
            for q in api.get_security_quotes(qlist) or []:
                c = q.get('code',''); lc = q.get('last_close',0); p = q.get('price',0)
                chg = (p-lc)/lc*100 if lc>0 else 0
                quotes[c] = {'price':p, 'change_pct':round(chg,2),
                             'b_vol':q.get('b_vol',0), 's_vol':q.get('s_vol',0)}
        except: continue
    return quotes


# ── 板块排行榜 ──

@st.cache_data(ttl=300)
def get_board_rankings() -> pd.DataFrame:
    boards = _get_board_data()
    quotes = _get_all_quotes()
    name_map = _build_stock_name_map()
    rows = []
    for b in boards:
        sq = [quotes.get(c) for c in b['stocks'] if c in quotes and quotes[c]['price']>0]
        if not sq: continue
        df = pd.DataFrame(sq)
        up = int((df['change_pct']>0).sum())
        down = int((df['change_pct']<0).sum())
        avg_chg = df['change_pct'].mean()
        tb, ts = df['b_vol'].sum(), df['s_vol'].sum()
        ratio = tb/max(ts,1)
        score = avg_chg*0.4 + (ratio-1)*30 + ((up-down)/max(up+down,1))*20
        ti = df['change_pct'].idxmax()
        tc = b['stocks'][ti] if ti<len(b['stocks']) else ''
        rows.append({"板块名称":b['id'], "涨跌幅":round(avg_chg,2),
            "上涨家数":up, "下跌家数":down, "外盘":int(tb), "内盘":int(ts),
            "内外盘比":round(ratio,2), "净买入":int(tb-ts),
            "博弈评分":round(max(0,min(100,score)),1),
            "领涨股":name_map.get(tc,''), "领涨股涨跌幅":round(df.loc[ti,'change_pct'],2)})
    result = pd.DataFrame(rows)
    if result.empty: return result
    result = result.sort_values(result.columns[9], ascending=False).reset_index(drop=True)
    result.index += 1; result.insert(0,"序号",result.index)
    return result


# ── 板块成分股 ──

def _build_stock_name_map() -> dict:
    api = _get_tdx_api()
    name_map = {}
    for market in [0, 1]:
        count = api.get_security_count(market)
        for start in range(0, count, 500):
            for item in api.get_security_list(market, start) or []:
                code = str(item.get('code',''))
                name = item.get('name','').strip()
                if code and name: name_map[code] = name
    return name_map


@st.cache_data(ttl=1800)
def get_concept_board_stocks(board_id: str) -> pd.DataFrame:
    name_map = _build_stock_name_map()
    for b in _get_board_data():
        if b['id'] == board_id:
            result = []
            for code in b['stocks']:
                name = name_map.get(code, '')
                if code and name: result.append({"股票代码":code, "股票名称":name})
            return pd.DataFrame(result)
    return pd.DataFrame(columns=["股票代码","股票名称"])


# ── 板块历史（成分股均值） ──

@st.cache_data(ttl=3600)
def get_concept_board_history(symbol: str, days: int = 60) -> pd.DataFrame:
    stocks_df = get_concept_board_stocks(symbol)
    if len(stocks_df) == 0: return pd.DataFrame()
    api, codes, all_dates = _get_tdx_api(), stocks_df["股票代码"].tolist()[:30], {}
    for code in codes:
        market = 1 if code.startswith(('6','9')) else 0
        try:
            df = api.to_df(api.get_security_bars(9, market, code, 0, days+10) or [])
            if df.empty: continue
            df.columns = ["日期","开盘","收盘","最高","最低","成交量","成交额"]
            df["日期"] = pd.to_datetime(df["日期"])
            for _, r in df.iterrows():
                d = r["日期"]
                if d not in all_dates: all_dates[d] = {"总":0,"c":0}
                all_dates[d]["总"] += r["收盘"]; all_dates[d]["c"] += 1
        except: continue
    records = [{"日期":d, "收盘价":v["总"]/v["c"]} for d,v in sorted(all_dates.items()) if v["c"]>0]
    df = pd.DataFrame(records)
    if df.empty: return df
    df = df.sort_values("日期").tail(days).reset_index(drop=True)
    if len(df) >= 2: df["涨跌幅(%)"] = df["收盘价"].pct_change() * 100
    return df


# ── 个股 ──

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
