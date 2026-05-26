from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from app.config import TEMPLATES_DIR
from app.services.data_fetcher import (
    fetch_sectors, fetch_sector_stocks,
    fetch_concept_boards,
)

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("")
async def sector_list(request: Request):
    """行业板块列表页"""
    sectors = fetch_sectors()
    data = sectors.to_dict(orient="records") if not sectors.empty else []
    return templates.TemplateResponse(request, "sectors.html", {"sectors": data})


@router.get("/concept-boards")
async def concept_boards():
    """概念板块列表"""
    df = fetch_concept_boards()
    if df.empty:
        return []
    return df.to_dict(orient="records")


@router.get("/{board_name}/stocks")
async def sector_stocks(board_name: str):
    """行业板块成分股列表"""
    df = fetch_sector_stocks(board_name)
    if df.empty:
        return []
    cols = [c for c in ["code", "name", "change_pct", "price", "market_cap", "pe", "turnover_rate", "sector_name"] if c in df.columns]
    return df[cols].to_dict(orient="records")
