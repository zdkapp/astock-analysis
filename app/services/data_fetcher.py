"""
A 股数据采集模块
- Baostock: 行业分类、历史行情
- 腾讯行情 API: 实时行情
"""
import baostock as bs
import pandas as pd
import numpy as np
import urllib.request
import re
from datetime import date, timedelta

_BS_LOGGED_IN = False


def _ensure_bs_login():
    global _BS_LOGGED_IN
    if _BS_LOGGED_IN:
        return
    lg = bs.login()
    if lg.error_code != "0":
        raise ConnectionError(f"Baostock login failed: {lg.error_msg}")
    _BS_LOGGED_IN = True


def _bs_dataframe(rs) -> pd.DataFrame:
    """把 baostock ResultData 转成 DataFrame"""
    if not rs or not rs.data:
        return pd.DataFrame(rs.data, columns=rs.fields) if hasattr(rs, 'fields') else pd.DataFrame()
    return pd.DataFrame(rs.data, columns=rs.fields)


# ── 腾讯行情 ──────────────────────────────────────────

def _tencent_quote(codes: list) -> pd.DataFrame:
    if not codes:
        return pd.DataFrame()
    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    raw = resp.read().decode("gbk")
    return _parse_tencent(raw)


def _parse_tencent(raw: str) -> pd.DataFrame:
    rows = []
    for line in raw.strip().split("\n"):
        m = re.search(r'"(.+)"', line)
        if not m:
            continue
        parts = m.group(1).split("~")
        if len(parts) < 46:
            continue
        try:
            rows.append({
                "code": parts[2].strip(),
                "name": parts[1].strip(),
                "price": float(parts[3] or 0),
                "change_pct": float(parts[32] or 0),
                "change_amount": float(parts[31] or 0),
                "high": float(parts[33] or 0),
                "low": float(parts[34] or 0),
                "volume": float(parts[36] or 0) * 100,
                "amount": float(parts[37] or 0) * 10000,
                "turnover_rate": float(parts[38] or 0),
                "pe": float(parts[39] or 0),
                "market_cap": float(parts[44] or 0) * 1e8,
            })
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows)


def _code_to_tx(code: str) -> str:
    """sh.600000 -> sh600000"""
    return code.replace(".", "")


def _code_from_bs(code: str) -> str:
    """sh.600000 -> 600000"""
    return code.split(".")[1] if "." in code else code


# ── 全市场股票 + 实时行情 ─────────────────────────

def fetch_all_stocks_spot() -> pd.DataFrame:
    """获取全市场实时行情（baostock 分类 + 腾讯行情）"""
    _ensure_bs_login()
    bs_df = _bs_dataframe(bs.query_stock_industry())
    if bs_df.empty:
        return pd.DataFrame()

    bs_df["code_short"] = bs_df["code"].apply(_code_from_bs)
    bs_df["industry"] = bs_df["industry"].fillna("")

    # 全量查询腾讯行情（分批）
    codes = bs_df["code"].tolist()
    tx_codes = [_code_to_tx(c) for c in codes]
    all_data = []
    for i in range(0, len(tx_codes), 80):
        df = _tencent_quote(tx_codes[i:i + 80])
        if not df.empty:
            all_data.append(df)
    if not all_data:
        return pd.DataFrame()
    spot = pd.concat(all_data, ignore_index=True)

    # 合并行业分类
    ind_map = dict(zip(bs_df["code_short"], bs_df["industry"]))
    name_map = dict(zip(bs_df["code_short"], bs_df["code_name"]))
    spot["sector_name"] = spot["code"].map(ind_map).fillna("")
    spot["name"] = spot["code"].map(name_map).fillna(spot["name"])
    return spot


# ── 行业板块 ───────────────────────────────────────

def fetch_sectors() -> pd.DataFrame:
    """获取行业板块（聚合实时行情）"""
    spot = fetch_all_stocks_spot()
    if spot.empty:
        return pd.DataFrame()
    g = spot[spot["sector_name"] != ""].groupby("sector_name")
    sector = g.agg(
        change_pct=("change_pct", "mean"),
        up_count=("change_pct", lambda x: (x > 0).sum()),
        down_count=("change_pct", lambda x: (x < 0).sum()),
        total_market_cap=("market_cap", "sum"),
    ).reset_index()
    sector.columns = ["name", "change_pct", "up_count", "down_count", "total_market_cap"]
    sector["stock_count"] = sector["up_count"] + sector["down_count"]

    leaders = spot.loc[spot.groupby("sector_name")["change_pct"].idxmax()]
    lmap = dict(zip(leaders["sector_name"], leaders["name"]))
    lcmap = dict(zip(leaders["sector_name"], leaders["change_pct"]))
    sector["leader_name"] = sector["name"].map(lmap)
    sector["leader_chg"] = sector["name"].map(lcmap)
    return sector.sort_values("change_pct", ascending=False).reset_index(drop=True)


def fetch_sector_stocks(sector_name: str) -> pd.DataFrame:
    """获取行业成分股"""
    spot = fetch_all_stocks_spot()
    if spot.empty:
        return pd.DataFrame()
    r = spot[spot["sector_name"] == sector_name].copy()
    return r.sort_values("change_pct", ascending=False)


# ── 概念板块 ───────────────────────────────────────

def fetch_concept_boards() -> pd.DataFrame:
    """获取概念板块列表（THS）"""
    import akshare as ak
    try:
        df = ak.stock_board_concept_name_ths()
        df.columns = ["name", "code"]
        return df
    except Exception:
        return pd.DataFrame()


def fetch_concept_board_stocks(concept_name: str) -> pd.DataFrame:
    """获取概念板块成分股（EM API，走 HTTP 绕过 HTTPS 阻断）"""
    import requests
    import warnings
    warnings.filterwarnings("ignore")

    # 1. 从 EM 获取概念板块代码
    try:
        r = requests.get(
            "http://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": "1", "pz": "500", "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": "m:90+t:3", "fields": "f12,f14",
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        data = r.json()
        boards = data.get("data", {}).get("diff", [])
        board_code = None
        for b in boards:
            if b.get("f14") == concept_name:
                board_code = b.get("f12")
                break
        if not board_code:
            return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

    # 2. 获取成分股
    try:
        r2 = requests.get(
            "http://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": "1", "pz": "200", "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": f"b:{board_code}+f:!50",
                "fields": "f12,f14,f2,f3,f4,f5,f6,f7,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22",
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r2_data = r2.json()
        diffs = r2_data.get("data", {}).get("diff", [])
        records = []
        for d in diffs:
            records.append({
                "code": str(d.get("f12", "")),
                "name": str(d.get("f14", "")),
                "price": float(d.get("f2", 0) or 0),
                "change_pct": float(d.get("f3", 0) or 0),
                "change_amount": float(d.get("f4", 0) or 0),
                "volume": float(d.get("f5", 0) or 0),
                "amount": float(d.get("f6", 0) or 0),
                "market_cap": float(d.get("f20", 0) or 0) * 1e8 if d.get("f20") else 0,
                "turnover_rate": float(d.get("f23", 0) or 0),
                "pe": float(d.get("f9", 0) or 0),
            })
        return pd.DataFrame(records)
    except Exception:
        return pd.DataFrame()


# ── 个股 ───────────────────────────────────────────

def _bs_code(code: str) -> str:
    c = code.strip()
    if "." in c:
        return c
    if c.startswith(("6", "9")):
        return f"sh.{c}"
    return f"sz.{c}"


def fetch_stock_history(code: str, days: int = 365) -> pd.DataFrame:
    _ensure_bs_login()
    end = date.today()
    start = end - timedelta(days=days)
    rs = bs.query_history_k_data_plus(
        _bs_code(code),
        fields="date,open,high,low,close,volume,amount,adjustflag",
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        frequency="d", adjustflag="2",
    )
    df = _bs_dataframe(rs)
    if df.empty:
        return df
    df = df.rename(columns={
        "date": "日期", "open": "开盘", "high": "最高",
        "low": "最低", "close": "收盘", "volume": "成交量", "amount": "成交额",
    })
    for col in ["开盘", "最高", "最低", "收盘", "成交量", "成交额"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if len(df) > 1:
        df["涨跌幅"] = df["收盘"].pct_change() * 100
        df["涨跌额"] = df["收盘"].diff()
    else:
        df["涨跌幅"] = 0.0
        df["涨跌额"] = 0.0
    df["振幅"] = (df["最高"] - df["最低"]) / df["最低"].replace(0, np.nan) * 100
    df["换手率"] = 0.0
    return df.dropna(subset=["收盘"])


def fetch_stock_financial(code: str) -> pd.DataFrame:
    _ensure_bs_login()
    today = date.today()
    q = (today.month - 1) // 3 + 1
    rs = bs.query_operation_data(_bs_code(code), year=today.year, quarter=q)
    df = _bs_dataframe(rs)
    if df.empty and q > 1:
        df = _bs_dataframe(bs.query_operation_data(_bs_code(code), year=today.year, quarter=q - 1))
    return df


def search_stocks(keyword: str) -> pd.DataFrame:
    spot = fetch_all_stocks_spot()
    if spot.empty:
        return spot
    m = spot["code"].astype(str).str.contains(keyword) | spot["name"].str.contains(keyword, na=False)
    return spot[m].head(20)
