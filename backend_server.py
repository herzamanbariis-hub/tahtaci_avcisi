# -*- coding: utf-8 -*-
"""
FastAPI Backend Server
======================
Sistemin veritabanina yazilan (data_ingestion.py tarafindan) AKD, Takas
ve Fiyat verilerini REST API (JSON) olarak sunar.
Ayni zamanda Streamlit arayuzu (live mode) veya baska sistemler 
bu API'den beslenir.

Kullanim:
---------
uvicorn backend_server:app --host 127.0.0.1 --port 8000 --reload
"""

import logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import pandas as pd

from database import query_df, DB_PATH
from telegram_scraper import apply_liquidity_filter

# Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("BackendAPI")

app = FastAPI(title="Tahtaci Avcisi Backend API", version="1.0")

class AKDResponse(BaseModel):
    success: bool
    hisse: str
    tarih: str
    data: List[dict]

class TakasResponse(BaseModel):
    success: bool
    hisse: str
    tarih: str
    data: List[dict]

class PriceResponse(BaseModel):
    success: bool
    hisse: str
    data: List[dict]

@app.get("/api/akd", response_model=AKDResponse)
def get_akd(hisse: str, tarih: str):
    """
    Belirtilen hisse ve tarih icin AKD (Araci Kurum Dagilimi) verilerini dondurur.
    """
    sql = "SELECT kurum_adi as kurum, net_lot as net, tutar as amount, avg_price as price FROM akd_data WHERE hisse = ? AND tarih = ?"
    try:
        df = query_df(sql, params=(hisse, tarih))
        data = df.to_dict(orient="records")
        return {"success": True, "hisse": hisse, "tarih": tarih, "data": data}
    except Exception as e:
        logger.error("AKD sorgu hatasi: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/takas", response_model=TakasResponse)
def get_takas(hisse: str, tarih: str):
    """
    Belirtilen hisse ve tarih icin Takas verilerini dondurur.
    """
    sql = "SELECT kurum_adi as kurum, saklama_orani as oran, saklama_adet as adet FROM takas_data WHERE hisse = ? AND tarih = ?"
    try:
        df = query_df(sql, params=(hisse, tarih))
        data = df.to_dict(orient="records")
        return {"success": True, "hisse": hisse, "tarih": tarih, "data": data}
    except Exception as e:
        logger.error("Takas sorgu hatasi: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/price", response_model=PriceResponse)
def get_price(hisse: str, start: str, end: str):
    """
    Belirtilen hisse icin fiyat gecmisini (OHLCV) dondurur.
    """
    sql = "SELECT tarih as date, open as o, high as h, low as l, close as c, volume as v FROM price_data WHERE hisse = ? AND tarih >= ? AND tarih <= ? ORDER BY tarih ASC"
    try:
        df = query_df(sql, params=(hisse, start, end))
        data = df.to_dict(orient="records")
        return {"success": True, "hisse": hisse, "data": data}
    except Exception as e:
        logger.error("Fiyat sorgu hatasi: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend_server:app", host="127.0.0.1", port=8000, reload=True)
