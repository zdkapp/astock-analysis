"""
数据存储服务 - 将从 AKShare 获取的数据写入 SQLite
"""
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Sector, Stock, StockDaily
from app.services import data_fetcher


def refresh_sectors(db: Session) -> int:
    """刷新板块数据，返回写入数量"""
    df = data_fetcher.fetch_sectors()
    count = 0
    for _, row in df.iterrows():
        sector = db.query(Sector).filter(Sector.name == row.get("name", "")).first()
        if not sector:
            sector = Sector(name=row.get("name", ""))
            db.add(sector)
        sector.change_pct = float(row.get("change_pct", 0))
        sector.up_count = int(row.get("up_count", 0))
        sector.down_count = int(row.get("down_count", 0))
        sector.leader_name = str(row.get("leader_name", ""))
        sector.leader_chg = float(row.get("leader_chg", 0)) if pd.notna(row.get("leader_chg")) else 0
        sector.total_market_cap = float(row.get("total_market_cap", 0))
        sector.updated_at = datetime.now()
        count += 1
    db.commit()
    return count


def refresh_sector_stocks(db: Session, sector_name: str) -> int:
    """刷新某个板块的成分股数据"""
    df = data_fetcher.fetch_sector_stocks(sector_name)
    if df.empty:
        return 0

    sector = db.query(Sector).filter(Sector.name == sector_name).first()
    sector_id = sector.id if sector else None

    count = 0
    for _, row in df.iterrows():
        code = str(row.get("code", ""))
        stock = db.query(Stock).filter(Stock.code == code).first()
        if not stock:
            stock = Stock(code=code)
            db.add(stock)
        stock.name = str(row.get("name", ""))
        stock.sector_id = sector_id
        stock.sector_name = sector_name
        stock.price = float(row.get("price", 0))
        stock.change_pct = float(row.get("change_pct", 0))
        stock.change_amount = float(row.get("change_amount", 0))
        stock.market_cap = float(row.get("market_cap", 0)) if pd.notna(row.get("market_cap")) else 0
        stock.turnover_rate = float(row.get("turnover_rate", 0)) if pd.notna(row.get("turnover_rate")) else 0
        stock.pe = float(row.get("pe", 0)) if pd.notna(row.get("pe")) else 0
        stock.pb = float(row.get("pb", 0)) if pd.notna(row.get("pb")) else 0
        stock.updated_at = datetime.now()
        count += 1
    db.commit()
    return count


def refresh_stock_history(db: Session, code: str) -> int:
    """刷新个股历史行情"""
    df = data_fetcher.fetch_stock_history(code)
    if df.empty:
        return 0

    count = 0
    for _, row in df.iterrows():
        date_val = row.get("日期")
        if pd.isna(date_val):
            continue
        if isinstance(date_val, str):
            date_val = datetime.strptime(date_val, "%Y-%m-%d").date()

        exists = db.query(StockDaily).filter(
            StockDaily.code == code,
            StockDaily.date == date_val,
        ).first()
        if exists:
            continue

        daily = StockDaily(
            code=code,
            date=date_val,
            open=float(row.get("开盘", 0)),
            high=float(row.get("最高", 0)),
            low=float(row.get("最低", 0)),
            close=float(row.get("收盘", 0)),
            volume=float(row.get("成交量", 0)),
            amount=float(row.get("成交额", 0)),
            zhenfu=float(row.get("振幅", 0)),
            change_pct_daily=float(row.get("涨跌幅", 0)),
            change_amount_daily=float(row.get("涨跌额", 0)),
            turnover_rate_daily=float(row.get("换手率", 0)),
        )
        db.add(daily)
        count += 1
    db.commit()
    return count

