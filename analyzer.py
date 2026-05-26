"""Analysis logic - 资金博弈, 量价, 筹码分析."""

import pandas as pd
import numpy as np


def rank_boards_by_flow(df: pd.DataFrame) -> pd.DataFrame:
    """按资金博弈对板块进行排序评分

    Args:
        df: 概念板块资金流数据

    Returns:
        排序后的板块DataFrame，包含综合评分
    """
    if df is None or len(df) == 0:
        return pd.DataFrame()

    result = df.copy()

    # 确保数值类型
    numeric_cols = ["板块指数", "涨跌幅", "主力净流入", "超大单净流入",
                     "大单净流入", "中单净流入", "小单净流入", "领涨股涨跌幅"]
    for col in numeric_cols:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0)

    # 综合评分 (0-100)
    scores = pd.Series(np.zeros(len(result)), index=result.index)

    if "涨跌幅" in result.columns:
        pct_min, pct_max = result["涨跌幅"].min(), result["涨跌幅"].max()
        if pct_max > pct_min:
            scores += (result["涨跌幅"] - pct_min) / (pct_max - pct_min) * 40

    if "主力净流入" in result.columns:
        # 主力强度: 主力净流入 / (主力绝对值 + 散户绝对值)
        denom = result["主力净流入"].abs() + result["中单净流入"].abs()
        if "小单净流入" in result.columns:
            denom += result["小单净流入"].abs()
        denom += 0.01
        result["主力强度"] = result["主力净流入"] / denom
        scores += result["主力强度"].rank(pct=True) * 30

    if "超大单净流入" in result.columns:
        cols_pool = ["超大单净流入", "大单净流入", "中单净流入"]
        if "小单净流入" in result.columns:
            cols_pool.append("小单净流入")
        denom = result[cols_pool].abs().sum(axis=1) + 0.01
        result["超大单强度"] = result["超大单净流入"] / denom
        scores += result["超大单强度"].rank(pct=True) * 30

    result["综合评分"] = scores.clip(0, 100)

    return result.sort_values("综合评分", ascending=False).reset_index(drop=True)


def analyze_stock_money_flow(df: pd.DataFrame) -> dict:
    """分析个股资金流向数据

    Returns:
        分析结果字典
    """
    if df is None or len(df) == 0:
        return {}

    # 计算累计主力净流入
    result = {}
    for col in df.columns:
        if "净流入" in col:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "主力净流入" in df.columns:
        result["累计主力净流入"] = df["主力净流入"].sum()
        result["日均主力净流入"] = df["主力净流入"].mean()

    if "小单净流入" in df.columns:
        result["累计小单净流入"] = df["小单净流入"].sum()

    return result


def estimate_chip_distribution(df: pd.DataFrame) -> dict:
    """估算筹码分布

    使用换手率和价格区间近似估算筹码成本分布。

    Args:
        df: 个股历史行情DataFrame

    Returns:
        筹码分析结果
    """
    if df is None or len(df) < 5:
        return {}

    current_price = df["收盘"].iloc[-1]
    high_20 = df["最高"].tail(20).max()
    low_20 = df["最低"].tail(20).min()

    # 当前价格在20日区间的位置 (0~1)
    if high_20 > low_20:
        price_position = (current_price - low_20) / (high_20 - low_20)
    else:
        price_position = 0.5

    # 估算获利比例：用N日内收盘价分布近似
    closes = df["收盘"].values
    profit_pct = (closes[-1] > closes).mean() * 100

    # 平均成交价（换手率加权）
    total_volume = df["成交量"].tail(20).sum()
    if total_volume > 0:
        avg_cost = (df["成交量"].tail(20) * df["收盘"].tail(20)).sum() / total_volume
    else:
        avg_cost = current_price

    # 相对于平均成本的位置
    if avg_cost > 0:
        cost_distance = (current_price - avg_cost) / avg_cost * 100
    else:
        cost_distance = 0

    return {
        "现价": current_price,
        "20日最高": high_20,
        "20日最低": low_20,
        "价格区间位置": price_position,  # 0=最低, 1=最高
        "获利比例(%)": profit_pct,
        "平均成本(换手加权)": avg_cost,
        "距成本距离(%)": cost_distance,
        "筹码状态": "获利" if current_price >= avg_cost else "亏损",
    }


def filter_stocks_in_board(board_name: str, stocks_df: pd.DataFrame,
                           flow_data: pd.DataFrame | None = None) -> pd.DataFrame:
    """筛选并排序板块内个股

    Args:
        board_name: 板块名
        stocks_df: 板块成分股 DataFrame
        flow_data: 个股资金流数据（可选）

    Returns:
        排序后的个股DataFrame
    """
    return stocks_df


def get_board_market_sentiment(index_df: pd.DataFrame) -> dict:
    """分析板块市场情绪

    Returns:
        情绪指标字典
    """
    if index_df is None or len(index_df) < 2:
        return {}

    closes = index_df["收盘价"].values
    volumes = index_df["成交量"].values if "成交量" in index_df.columns else None

    sentiment = {
        "最新收盘": closes[-1],
        "涨跌幅(%)": (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else 0,
    }

    # 量价关系判断
    if volumes is not None and len(volumes) >= 2:
        vol_change = volumes[-1] / volumes[-2] - 1
        price_change = sentiment["涨跌幅(%)"]

        if price_change > 0 and vol_change > 0.1:
            sentiment["量价状态"] = "放量上涨 (强势)"
        elif price_change > 0 and vol_change < -0.1:
            sentiment["量价状态"] = "缩量上涨 (谨慎)"
        elif price_change < 0 and vol_change > 0.1:
            sentiment["量价状态"] = "放量下跌 (危险)"
        elif price_change < 0 and vol_change < -0.1:
            sentiment["量价状态"] = "缩量下跌 (企稳)"
        else:
            sentiment["量价状态"] = "量价平稳"

    # 短期趋势
    if len(closes) >= 5:
        sentiment["5日涨跌幅(%)"] = (closes[-1] / closes[-5] - 1) * 100
    if len(closes) >= 20:
        sentiment["20日涨跌幅(%)"] = (closes[-1] / closes[-20] - 1) * 100

    return sentiment
