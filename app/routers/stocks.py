from fastapi import APIRouter, Request, Query
from fastapi.templating import Jinja2Templates
from app.config import TEMPLATES_DIR
from app.services.data_fetcher import search_stocks, fetch_stock_history
import json

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/search")
async def stock_search(request: Request, q: str = Query("")):
    """股票搜索页"""
    results = []
    if q:
        df = search_stocks(q)
        if not df.empty:
            results = df.to_dict(orient="records")
    return templates.TemplateResponse(request, "stock_search.html", {
        "results": results, "query": q,
    })


@router.get("/{code}")
async def stock_detail(request: Request, code: str):
    """个股详情"""
    return templates.TemplateResponse(request, "stock_detail.html", {
        "stock": {"code": code}, "kline": [], "dailies": [],
    })


@router.get("/{code}/history")
async def stock_history(code: str, days: int = Query(120)):
    """个股历史行情 JSON"""
    df = fetch_stock_history(code, days=days)
    if df.empty:
        return []
    df = df.fillna(0)
    cols = ["日期", "开盘", "最高", "最低", "收盘", "涨跌幅", "成交量", "成交额"]
    existing = [c for c in cols if c in df.columns]
    return json.loads(df[existing].to_json(orient="records", force_ascii=False))
