import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import TEMPLATES_DIR, STATIC_DIR
from app.routers import sectors, stocks, screening
from app.services.data_fetcher import fetch_sectors

app = FastAPI(title="A股分析系统")

os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

app.include_router(sectors.router, prefix="/sectors", tags=["板块"])
app.include_router(stocks.router, prefix="/stocks", tags=["个股"])
app.include_router(screening.router, prefix="/screening", tags=["筛选"])


@app.get("/")
async def index(request: Request):
    sectors = fetch_sectors()
    data = {
        "sector_count": len(sectors) if not sectors.empty else 0,
        "up_count": int((sectors["change_pct"] > 0).sum()) if not sectors.empty else 0,
        "down_count": int((sectors["change_pct"] < 0).sum()) if not sectors.empty else 0,
    }
    return templates.TemplateResponse(request, "index.html", data)


@app.get("/health")
async def health():
    return {"status": "ok"}
