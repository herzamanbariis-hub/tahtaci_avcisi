# -*- coding: utf-8 -*-
"""
Tahtaci Avcisi v1.0 — Endeks Kilidi Modulu (Piyasa Supabi)
=============================================================
BIST100 endeksinin teknik durumuna gore tum sinyal uretiminin
onunde gecirilemez bir supap gorevi gorur.

Iki Asamali Kilit Mekanizmasi
------------------------------
1. **Ana Kilit**: BIST100 < SMA200 → Sistem tamamen KILITLI
2. **Dinamik Kilit**: Fiyat < SMA50 veya SMA20 < SMA50 → PASIF mod

Kullanim
--------
>>> from index_lock import get_market_status, MarketStatus
>>> status = get_market_status()
>>> if status == MarketStatus.LOCKED:
...     print("Sistem kilitli, sinyal uretilmez")
"""

import logging
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    DB_PATH,
    INDEX_TICKER,
    SMA200_PERIOD,
    SMA50_PERIOD,
    SMA20_PERIOD,
)
from database import query_df

logger = logging.getLogger(__name__)


# =============================================
# PIYASA DURUMU ENUM
# =============================================

class MarketStatus(Enum):
    """
    Piyasa durumu -- sinyal uretim izni belirler.

    Attributes
    ----------
    ACTIVE : Sinyal uretimi aktif, tum katmanlar calisir.
    PASSIVE : Mevcut pozisyonlar izlenir, yeni sinyal uretilmez.
    LOCKED : Sistem tamamen uyku modunda, hicbir islem yapilmaz.
    """
    ACTIVE = "ACTIVE"
    PASSIVE = "PASSIVE"
    LOCKED = "LOCKED"


# =============================================
# SMA HESAPLAMA
# =============================================

def compute_sma(prices: pd.Series, period: int) -> pd.Series:
    """
    Basit Hareketli Ortalama (Simple Moving Average) hesaplar.

    Parameters
    ----------
    prices : pd.Series
        Kapanis fiyat serisi.
    period : int
        Ortalama pencere buyuklugu.

    Returns
    -------
    pd.Series
        SMA degerleri (ilk ``period-1`` eleman NaN).
    """
    return prices.rolling(window=period, min_periods=period).mean()


# =============================================
# KiLiT KONTROLLERI
# =============================================

def check_main_lock(index_prices: pd.DataFrame) -> bool:
    """
    Ana Kilit: BIST100 endeksi gunluk SMA200'un altinda mi?

    Eger SMA200 altindaysa sistem tamamen KILITLI kalir.

    Parameters
    ----------
    index_prices : pd.DataFrame
        Endeks fiyat verisi. Sutunlar: tarih, close (en az 200 satir).

    Returns
    -------
    bool
        True ise sistem KILITLI.
    """
    if index_prices.empty or len(index_prices) < SMA200_PERIOD:
        logger.warning(
            "Ana kilit icin yeterli veri yok (%d satir, gereken: %d). "
            "Guvenli mod: KILITLI.",
            len(index_prices), SMA200_PERIOD,
        )
        return True  # Veri yetersizse guvenli tarafta kal

    sma200 = compute_sma(index_prices["close"], SMA200_PERIOD)
    last_close = index_prices["close"].iloc[-1]
    last_sma200 = sma200.iloc[-1]

    if np.isnan(last_sma200):
        logger.warning("SMA200 hesaplanamadi (NaN). Guvenli mod: KILITLI.")
        return True

    is_locked = last_close < last_sma200

    logger.info(
        "Ana Kilit: Fiyat=%.2f, SMA200=%.2f -> %s",
        last_close, last_sma200,
        "KILITLI" if is_locked else "ACIK",
    )
    return is_locked


def check_dynamic_lock(index_prices: pd.DataFrame) -> bool:
    """
    Dinamik Kilit: Kisa vadeli trend bozulmus mu?

    Iki kosuldan biri gerceklesirse PASIF moda gecer:
    1. Fiyat < SMA50
    2. SMA20 < SMA50 (Asagi kesisim / Death Cross kisa vade)

    Parameters
    ----------
    index_prices : pd.DataFrame
        Endeks fiyat verisi. Sutunlar: tarih, close (en az 50 satir).

    Returns
    -------
    bool
        True ise sistem PASIF modda.
    """
    if index_prices.empty or len(index_prices) < SMA50_PERIOD:
        logger.warning(
            "Dinamik kilit icin yeterli veri yok (%d satir, gereken: %d). "
            "Guvenli mod: PASIF.",
            len(index_prices), SMA50_PERIOD,
        )
        return True

    sma50 = compute_sma(index_prices["close"], SMA50_PERIOD)
    sma20 = compute_sma(index_prices["close"], SMA20_PERIOD)
    last_close = index_prices["close"].iloc[-1]
    last_sma50 = sma50.iloc[-1]
    last_sma20 = sma20.iloc[-1]

    if np.isnan(last_sma50) or np.isnan(last_sma20):
        logger.warning("SMA50/SMA20 hesaplanamadi (NaN). Guvenli mod: PASIF.")
        return True

    price_below_sma50 = last_close < last_sma50
    death_cross = last_sma20 < last_sma50

    is_passive = price_below_sma50 or death_cross

    logger.info(
        "Dinamik Kilit: Fiyat=%.2f, SMA50=%.2f, SMA20=%.2f | "
        "Fiyat<SMA50=%s, SMA20<SMA50=%s -> %s",
        last_close, last_sma50, last_sma20,
        price_below_sma50, death_cross,
        "PASIF" if is_passive else "ACIK",
    )
    return is_passive


# =============================================
# ANA DURUM FONKSIYONU
# =============================================

def get_market_status(db_path: str = DB_PATH) -> MarketStatus:
    """
    Veritabanindan endeks fiyatlarini cekip iki kilidi birlikte degerlendirir.

    Oncelik sirasi:
    1. Ana Kilit kontrol -> LOCKED ise direkt don
    2. Dinamik Kilit kontrol -> PASSIVE ise don
    3. Her iki kilit de acik -> ACTIVE don

    Parameters
    ----------
    db_path : str
        SQLite veritabani dosya yolu.

    Returns
    -------
    MarketStatus
        Piyasa durumu (ACTIVE / PASSIVE / LOCKED).
    """
    logger.info("=" * 50)
    logger.info("ENDEKS KILIDI KONTROL EDILIYOR: %s", INDEX_TICKER)
    logger.info("=" * 50)

    # Endeks fiyatlarini veritabanindan cek
    sql = """
        SELECT tarih, close
        FROM price_data
        WHERE hisse = ?
        ORDER BY tarih ASC
    """
    try:
        index_prices = query_df(sql, params=(INDEX_TICKER,), db_path=db_path)
    except Exception as e:
        logger.error("Endeks verisi cekilemedi: %s", e)
        logger.warning("Guvenli mod: KILITLI (veri yok)")
        return MarketStatus.LOCKED

    if index_prices.empty:
        logger.warning(
            "Endeks verisi bulunamadi (%s). "
            "Guvenli mod: KILITLI. Endeks verisini yukleyin.",
            INDEX_TICKER,
        )
        return MarketStatus.LOCKED

    # 1. Ana Kilit
    if check_main_lock(index_prices):
        logger.info("SONUC: %s -> KILITLI (Fiyat < SMA200)", INDEX_TICKER)
        return MarketStatus.LOCKED

    # 2. Dinamik Kilit
    if check_dynamic_lock(index_prices):
        logger.info("SONUC: %s -> PASIF (Kisa vade trend bozuk)", INDEX_TICKER)
        return MarketStatus.PASSIVE

    # 3. Her iki kilit de acik
    logger.info("SONUC: %s -> AKTIF (Tum kilitler acik)", INDEX_TICKER)
    return MarketStatus.ACTIVE


def get_market_status_with_data(index_prices: pd.DataFrame) -> MarketStatus:
    """
    Veritabani yerine dogrudan DataFrame ile calisir (test/mock icin).

    Parameters
    ----------
    index_prices : pd.DataFrame
        Endeks fiyat verisi. Sutunlar: tarih, close.

    Returns
    -------
    MarketStatus
        Piyasa durumu.
    """
    if index_prices.empty:
        return MarketStatus.LOCKED

    if check_main_lock(index_prices):
        return MarketStatus.LOCKED

    if check_dynamic_lock(index_prices):
        return MarketStatus.PASSIVE

    return MarketStatus.ACTIVE
