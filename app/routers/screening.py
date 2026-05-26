from fastapi import APIRouter, Request, Query
from fastapi.templating import Jinja2Templates
from app.config import TEMPLATES_DIR
from app.services.data_fetcher import fetch_all_stocks_spot

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("")
async def screening_page(request: Request):
    return templates.TemplateResponse(request, "screening.html", {"results": None})


@router.get("/query")
async def screening_query(
    request: Request,
    min_pe: float = Query(0, alias="min_pe"),
    max_pe: float = Query(9999, alias="max_pe"),
    min_mc: float = Query(0, alias="min_mc"),
    max_mc: float = Query(99999999999999, alias="max_mc"),
):
    """多条件筛选个股"""
    spot = fetch_all_stocks_spot()
    if spot.empty:
        return {"results": [], "total": 0}
    mask = (
        (spot["pe"].between(min_pe, max_pe) if "pe" in spot else True)
        & (spot["market_cap"].between(min_mc, max_mc) if "market_cap" in spot else True)
    )
    result = spot[mask].sort_values("change_pct", ascending=False).head(200)
    cols = [c for c in ["code", "name", "price", "change_pct", "pe", "market_cap", "turnover_rate", "sector_name"] if c in result.columns]
    return {"results": result[cols].to_dict(orient="records"), "total": len(result)}
