from datetime import date
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, func
from app.database import Base


class Sector(Base):
    __tablename__ = "sectors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, index=True, comment="板块名称")
    code = Column(String(20), comment="板块代码")
    change_pct = Column(Float, comment="涨跌幅%")
    up_count = Column(Integer, comment="上涨家数")
    down_count = Column(Integer, comment="下跌家数")
    leader_name = Column(String(50), comment="领涨股名称")
    leader_chg = Column(Float, comment="领涨股涨幅")
    total_market_cap = Column(Float, comment="总市值")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), index=True, comment="股票代码")
    name = Column(String(50), comment="股票名称")
    sector_id = Column(Integer, nullable=True, comment="所属板块ID")
    sector_name = Column(String(50), comment="所属板块名称")
    market = Column(String(10), comment="市场")

    # 实时行情
    price = Column(Float, comment="最新价")
    change_pct = Column(Float, comment="涨跌幅")
    change_amount = Column(Float, comment="涨跌额")
    volume = Column(Float, comment="成交量(手)")
    amount = Column(Float, comment="成交额")
    turnover_rate = Column(Float, comment="换手率%")
    pe = Column(Float, comment="市盈率")
    pb = Column(Float, comment="市净率")
    market_cap = Column(Float, comment="总市值")
    float_market_cap = Column(Float, comment="流通市值")

    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class StockDaily(Base):
    __tablename__ = "stock_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), index=True)
    date = Column(Date, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float, comment="成交量(股)")
    amount = Column(Float, comment="成交额")
    zhenfu = Column("振幅", Float)
    change_pct_daily = Column("涨跌幅", Float)
    change_amount_daily = Column("涨跌额", Float)
    turnover_rate_daily = Column("换手率", Float)
