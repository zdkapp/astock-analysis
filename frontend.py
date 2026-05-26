"""A股数据分析 - 板块轮动与个股筛选"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_fetcher import (
    get_concept_boards,
    get_concept_board_history,
    get_concept_fund_flow,
    get_concept_board_stocks,
    get_stock_history,
    get_stock_fund_flow,
)
from database import init_db
from analyzer import rank_boards_by_flow, estimate_chip_distribution, get_board_market_sentiment

st.set_page_config(page_title="A股资金博弈分析", layout="wide", initial_sidebar_state="collapsed")

# ── 暗色主题样式 ──
st.markdown("""
<style>
    .main-header { font-size: 1.8rem; font-weight: 700; margin-bottom: 0.5rem; }
    .positive { color: #ff4b4b; }
    .negative { color: #00d4aa; }
    .stDataFrame { font-size: 0.85rem; }
    div[data-testid="stMetricValue"] { font-size: 1.3rem; }
</style>
""", unsafe_allow_html=True)


def init_session():
    if "page" not in st.session_state:
        st.session_state.page = "boards"
    if "current_board" not in st.session_state:
        st.session_state.current_board = None
    if "current_stock" not in st.session_state:
        st.session_state.current_stock = None


# ── 缓存 ──
@st.cache_data(ttl=3600)
def _cached_boards():
    return get_concept_boards()

@st.cache_data(ttl=1800)
def _cached_flow(period):
    return get_concept_fund_flow(period)

@st.cache_data(ttl=3600)
def _cached_board_hist(name, days=60):
    return get_concept_board_history(name, days)

@st.cache_data(ttl=1800)
def _cached_board_stocks(name):
    return get_concept_board_stocks(name)

@st.cache_data(ttl=600)
def _cached_stock_hist(code, days=60):
    return get_stock_history(code, days)


# ── 工具函数 ──
def fmt_num(x):
    try:
        x = float(x)
    except (ValueError, TypeError):
        return "-"
    if abs(x) >= 1e8:
        return f"{x/1e8:.2f}亿"
    if abs(x) >= 1e4:
        return f"{x/1e4:.2f}万"
    return f"{x:.2f}"


def fmt_pct(x):
    try:
        v = float(x)
        return ("<span class='positive'>%+.2f%%</span>" if v > 0
                else "<span class='negative'>%+.2f%%</span>" if v < 0
                else f"{v:+.2f}%")
    except (ValueError, TypeError):
        return "-"


def nav_back(target, label="← 返回"):
    if st.button(label):
        st.session_state.page = target
        st.rerun()


# ══════════════════════════════════════════════════
#  页面1：板块全景扫描
# ══════════════════════════════════════════════════
def page_boards():
    st.markdown('<div class="main-header">板块资金博弈全景扫描</div>', unsafe_allow_html=True)

    period_map = {"今日": "即时", "近3日": "3日排行", "近5日": "5日排行",
                  "近10日": "10日排行", "近20日": "20日排行"}
    period = st.segmented_control("周期", list(period_map.keys()),
                                   default="今日", label_visibility="collapsed",
                                   key="per")
    flow = _cached_flow(period_map[period])

    if flow is None or len(flow) == 0:
        st.warning("暂无数据")
        return

    ranked = rank_boards_by_flow(flow)

    # 构造显示用DataFrame（保持原数值用于排序）
    display = ranked[["序号", "板块名称", "涨跌幅", "主力净流入",
                       "超大单净流入", "综合评分", "领涨股", "领涨股涨跌幅"]].copy()
    display["涨跌幅"] = display["涨跌幅"].apply(lambda x: f"{x:+.2f}%")
    display["主力净流入"] = display["主力净流入"].apply(fmt_num)
    display["超大单净流入"] = display["超大单净流入"].apply(fmt_num)
    display["领涨股涨跌幅"] = display["领涨股涨跌幅"].apply(lambda x: f"{x:+.2f}%")
    display["综合评分"] = display["综合评分"].apply(lambda x: f"{x:.1f}")

    sel = st.dataframe(
        display,
        column_config={
            "序号": st.column_config.Column("序号", width=50),
            "板块名称": st.column_config.Column("板块名称", width=180),
            "涨跌幅": st.column_config.Column("涨跌幅", width=90),
            "主力净流入": st.column_config.Column("主力净流入", width=110),
            "超大单净流入": st.column_config.Column("超大单净流入", width=110),
            "综合评分": st.column_config.Column("博弈评分", width=90),
            "领涨股": st.column_config.Column("领涨股", width=120),
            "领涨股涨跌幅": st.column_config.Column("领涨股涨幅", width=100),
        },
        use_container_width=True, hide_index=True, height=700,
        on_select="rerun", selection_mode="single-row",
    )

    if sel and sel.selection and sel.selection.rows:
        idx = sel.selection.rows[0]
        board = ranked.iloc[idx]["板块名称"]
        if board:
            st.session_state.current_board = board
            st.session_state.page = "board_detail"
            st.rerun()

    # 底部统计
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("概念板块", len(ranked))
    with c2:
        pos = int((ranked["涨跌幅"] > 0).sum())
        st.metric("上涨板块", pos)
    with c3:
        st.metric("下跌板块", len(ranked) - pos)
    with c4:
        st.metric("最强板块", ranked.iloc[0]["板块名称"])


# ══════════════════════════════════════════════════
#  页面2：板块详情 → 个股
# ══════════════════════════════════════════════════
def page_board_detail():
    board = st.session_state.get("current_board", "")
    if not board:
        st.session_state.page = "boards"
        st.rerun()
        return

    nav_back("boards", "← 返回板块全景")
    st.markdown(f'<div class="main-header">{board}</div>', unsafe_allow_html=True)

    hist = _cached_board_hist(board, 60)
    info = _cached_board_stocks(board)

    # ── 情绪指标 ──
    sent = get_board_market_sentiment(hist) if hist is not None and len(hist) > 0 else {}
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        v = sent.get("涨跌幅(%)", "-")
        st.metric("当日涨跌幅", f"{v:+.2f}%" if isinstance(v, (int, float)) else "-")
    with c2:
        v = sent.get("5日涨跌幅(%)", 0)
        st.metric("5日涨跌幅", f"{v:+.2f}%" if isinstance(v, (int, float)) else "-")
    with c3:
        v = sent.get("20日涨跌幅(%)", 0)
        st.metric("20日涨跌幅", f"{v:+.2f}%" if isinstance(v, (int, float)) else "-")
    with c4:
        st.metric("量价状态", sent.get("量价状态", "-"))
    with c5:
        v = sent.get("最新收盘", "-")
        st.metric("板块指数", f"{v:.2f}" if isinstance(v, (int, float)) else "-")

    # ── K线 ──
    if hist is not None and len(hist) >= 5:
        st.subheader("板块走势")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            vertical_spacing=0.05, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(
            x=hist["日期"], open=hist["开盘价"], high=hist["最高价"],
            low=hist["最低价"], close=hist["收盘价"],
            increasing_line_color="#ff4b4b", decreasing_line_color="#00d4aa"), row=1, col=1)
        clr = ["#ff4b4b" if hist["收盘价"].iloc[i] >= hist["开盘价"].iloc[i]
               else "#00d4aa" for i in range(len(hist))]
        fig.add_trace(go.Bar(x=hist["日期"], y=hist["成交量"],
                             marker_color=clr, opacity=0.6), row=2, col=1)
        fig.update_layout(xaxis_rangeslider_visible=False, height=420,
                          margin=dict(l=0, r=0, t=10, b=0),
                          template="plotly_dark", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # ── 板块摘要信息（替代成分股，等另一个窗口提供个股数据） ──
    st.subheader("板块概况")
    if info is not None and len(info) >= 2:
        # info 返回的是 项目/值 格式的摘要
        show = info.copy()
        if "项目" in show.columns and "值" in show.columns:
            show.columns = ["指标", "数值"]
        st.dataframe(show, use_container_width=True, hide_index=True)
    else:
        st.info("暂无板块详细数据")


# ══════════════════════════════════════════════════
#  页面3：个股详情
# ══════════════════════════════════════════════════
def page_stock_detail():
    info = st.session_state.get("current_stock", {})
    if not info:
        st.session_state.page = "board_detail"
        st.rerun()
        return

    code = info["code"]
    name = info.get("name", "")

    nav_back("board_detail", "← 返回板块")
    st.markdown(f'<div class="main-header">{name}（{code}）</div>', unsafe_allow_html=True)

    hist = _cached_stock_hist(code, 60)
    if hist is None or len(hist) == 0:
        st.error("无法获取个股数据")
        return

    chip = estimate_chip_distribution(hist)
    price = hist["收盘"].iloc[-1]
    chg = hist["涨跌幅"].iloc[-1]
    turn = hist["换手率"].iloc[-1]

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: st.metric("当前价", f"{price:.2f}")
    with c2: st.metric("当日涨跌幅", f"{chg:+.2f}%",
                        delta_color="normal" if chg >= 0 else "inverse")
    with c3: st.metric("换手率", f"{turn:.2f}%")
    with c4: st.metric("获利比例", f"{chip.get('获利比例(%)', 0):.1f}%")
    with c5: st.metric("平均成本", f"{chip.get('平均成本(换手加权)', 0):.2f}")
    with c6: st.metric("筹码状态", chip.get("筹码状态", "-"))

    # ── K线图 ──
    st.subheader("K线走势")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05, row_heights=[0.7, 0.3])
    clr = ["#ff4b4b" if hist["收盘"].iloc[i] >= hist["开盘"].iloc[i]
           else "#00d4aa" for i in range(len(hist))]
    fig.add_trace(go.Candlestick(
        x=hist["日期"], open=hist["开盘"], high=hist["最高"],
        low=hist["最低"], close=hist["收盘"],
        increasing_line_color="#ff4b4b", decreasing_line_color="#00d4aa"), row=1, col=1)
    fig.add_trace(go.Bar(x=hist["日期"], y=hist["换手率"],
                         marker_color=clr, opacity=0.5), row=2, col=1)
    fig.update_layout(xaxis_rangeslider_visible=False, height=420,
                      margin=dict(l=0, r=0, t=10, b=0),
                      template="plotly_dark", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # ── 资金流向 ──
    st.subheader("资金博弈分析")
    market = "sh" if code.startswith("6") else ("sz" if code.startswith(("0", "3")) else "sh")
    try:
        fund = get_stock_fund_flow(code, market)
    except Exception:
        fund = None

    if fund is not None and len(fund) > 0:
        fund = fund.tail(20).reset_index(drop=True)

        # 主力柱状图
        if "主力净流入" in fund.columns:
            fund["主力净流入"] = pd.to_numeric(fund["主力净流入"], errors="coerce").fillna(0)
            clr2 = ["#ff4b4b" if v >= 0 else "#00d4aa" for v in fund["主力净流入"]]
            f1 = go.Figure(go.Bar(x=fund.index, y=fund["主力净流入"], marker_color=clr2))
            f1.update_layout(title="主力资金流向", height=260,
                             template="plotly_dark", yaxis_title="万元",
                             margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(f1, use_container_width=True)

        # 内外盘
        if "外盘" in fund.columns and "内盘" in fund.columns:
            fund["外盘"] = pd.to_numeric(fund["外盘"], errors="coerce").fillna(0)
            fund["内盘"] = pd.to_numeric(fund["内盘"], errors="coerce").fillna(0)
            r5 = fund.tail(5)
            o_sum, i_sum = r5["外盘"].sum(), r5["内盘"].sum()
            ratio = o_sum / i_sum if i_sum > 0 else 0

            sc1, sc2, sc3 = st.columns(3)
            with sc1: st.metric("近5日外盘", fmt_num(o_sum))
            with sc2: st.metric("近5日内盘", fmt_num(i_sum))
            with sc3: st.metric("内外盘比", f"{ratio:.2f}")

            pie = make_subplots(rows=1, cols=2, subplot_titles=("近5日", "当日"))
            pie.add_trace(go.Pie(labels=["外盘", "内盘"],
                                 values=[o_sum, i_sum],
                                 marker_colors=["#ff4b4b", "#00d4aa"]), row=1, col=1)
            lf = fund.tail(1)
            if len(lf) > 0:
                pie.add_trace(go.Pie(labels=["外盘", "内盘"],
                                     values=[float(lf["外盘"].iloc[0]), float(lf["内盘"].iloc[0])],
                                     marker_colors=["#ff4b4b", "#00d4aa"]), row=1, col=2)
            pie.update_layout(height=280, margin=dict(l=0, r=0, t=30, b=0),
                              template="plotly_dark", showlegend=False)
            st.plotly_chart(pie, use_container_width=True)
    else:
        st.info("暂无资金流向数据")

    # ── 筹码 ──
    st.subheader("筹码成本估算")
    ca, cb = st.columns(2)
    with ca:
        if len(hist) >= 20:
            close20 = hist["收盘"].tail(20)
            hf = go.Figure()
            hf.add_trace(go.Histogram(x=close20, nbinsx=15,
                                       marker_color="#3366cc", opacity=0.7))
            hf.add_vline(x=price, line_dash="dash", line_color="#ff4b4b",
                          annotation_text=f"现价 {price:.2f}")
            hf.update_layout(title="近20日价格分布", height=280,
                             template="plotly_dark",
                             margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(hf, use_container_width=True)
    with cb:
        tbl = [
            ("当前价格", f"{chip.get('现价', 0):.2f}"),
            ("20日最高", f"{chip.get('20日最高', 0):.2f}"),
            ("20日最低", f"{chip.get('20日最低', 0):.2f}"),
            ("价格在20日区间位置", f"{chip.get('价格区间位置', 0)*100:.1f}%"),
            ("平均持仓成本", f"{chip.get('平均成本(换手加权)', 0):.2f}"),
            ("距成本距离", f"{chip.get('距成本距离(%)', 0):+.2f}%"),
            ("获利比例", f"{chip.get('获利比例(%)', 0):.1f}%"),
        ]
        st.dataframe(pd.DataFrame(tbl, columns=["指标", "数值"]),
                     use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════
def main():
    init_session()
    init_db()

    {
        "boards": page_boards,
        "board_detail": page_board_detail,
        "stock_detail": page_stock_detail,
    }.get(st.session_state.page, page_boards)()


if __name__ == "__main__":
    main()
