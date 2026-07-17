# -*- coding: utf-8 -*-
"""
Tahtaci Avcisi v1.0 — Tuzak Savar Modulu
===========================================
Price Action ve Volume Profile tabanli tuzak tespit katmani.

Bilesenler
----------
A. **Bollinger Squeeze / Keltner Daralma**: Dusuk volatilite donemi tespiti
B. **Bear Trap / Liquidity Sweep**: Sahte destek kirilimi (ayi tuzagi) algilama
C. **Volume Profile & POC**: En yogun hacim noktasi ve kirilim kontrolu
D. **Retest Onay**: Kirilan direnç ustunde bar kapanisi dogrulama

Kullanim
--------
>>> from trap_detector import analyze_trap_setup
>>> result = analyze_trap_setup("EREGL")
>>> print(result)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from config import (
    DB_PATH,
    VOLUME_BREAKOUT_MULTIPLIER,
    VOLUME_MA_PERIOD,
    RETEST_CONFIRMATION_BARS,
)
from database import query_df

logger = logging.getLogger(__name__)


# =============================================
# SONUC VERI YAPISI
# =============================================

@dataclass
class TrapAnalysis:
    """
    Tuzak Savar analiz sonucu.

    Attributes
    ----------
    squeeze_active : bool
        Bollinger Squeeze aktif mi (dar bant donemi).
    bear_trap_detected : bool
        Ayi tuzagi (sahte alinma) tespit edildi mi.
    bear_trap_details : str
        Ayi tuzagi detay aciklamasi.
    poc_level : float
        Volume Profile Point of Control fiyati.
    poc_breakout : bool
        Fiyat POC ustune hacimli cikti mi.
    retest_confirmed : bool
        Kirilan seviye ustunde retest (bar kapanisi) onaylandi mi.
    trap_score : float
        Birlesik tuzak skor (0-100).
    details : dict
        Alt bilesen detaylari.
    """
    squeeze_active: bool = False
    bear_trap_detected: bool = False
    bear_trap_details: str = ""
    last_sweep_date: str = ""
    poc_level: float = 0.0
    poc_breakout: bool = False
    retest_confirmed: bool = False
    trap_score: float = 0.0
    details: dict = field(default_factory=dict)


# =============================================
# A. BOLLINGER SQUEEZE / KELTNER DARALMA
# =============================================

def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bantlari hesaplar.

    Parameters
    ----------
    close : pd.Series
        Kapanis fiyatlari.
    period : int
        SMA penceresi (varsayilan: 20).
    std_dev : float
        Standart sapma carpani (varsayilan: 2.0).

    Returns
    -------
    tuple of (pd.Series, pd.Series, pd.Series)
        (ust_bant, orta_bant, alt_bant)
    """
    middle = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
    atr_mult: float = 1.5,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Keltner Kanallari hesaplar (ATR tabanli).

    Parameters
    ----------
    high : pd.Series
        Yuksek fiyatlar.
    low : pd.Series
        Dusuk fiyatlar.
    close : pd.Series
        Kapanis fiyatlari.
    period : int
        EMA ve ATR penceresi (varsayilan: 20).
    atr_mult : float
        ATR carpani (varsayilan: 1.5).

    Returns
    -------
    tuple of (pd.Series, pd.Series, pd.Series)
        (ust_kanal, orta_kanal, alt_kanal)
    """
    # EMA hesapla (orta kanal)
    middle = close.ewm(span=period, adjust=False).mean()

    # True Range
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR
    atr = true_range.rolling(window=period, min_periods=period).mean()

    upper = middle + (atr * atr_mult)
    lower = middle - (atr * atr_mult)
    return upper, middle, lower


def detect_squeeze(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    bb_period: int = 20,
    bb_std: float = 2.0,
    kc_period: int = 20,
    kc_mult: float = 1.5,
) -> Tuple[bool, int]:
    """
    Bollinger Squeeze tespiti: BB bantlari KC kanallari icine girdiginde.

    Bu durum dusuk volatilite donemini isaret eder ve genellikle
    guclu bir kirilimin habercisidir.

    Parameters
    ----------
    close, high, low : pd.Series
        Fiyat serileri.
    bb_period, bb_std : int, float
        Bollinger parametreleri.
    kc_period, kc_mult : int, float
        Keltner parametreleri.

    Returns
    -------
    tuple of (bool, int)
        (squeeze_aktif_mi, ardisik_squeeze_gun_sayisi)
    """
    bb_upper, _, bb_lower = bollinger_bands(close, bb_period, bb_std)
    kc_upper, _, kc_lower = keltner_channels(high, low, close, kc_period, kc_mult)

    # BB bantlari KC icinde mi?
    squeeze = (bb_lower > kc_lower) & (bb_upper < kc_upper)
    squeeze = squeeze.dropna()

    if squeeze.empty:
        return False, 0

    is_active = bool(squeeze.iloc[-1])

    # Ardisik squeeze gun sayisi
    streak = 0
    for val in reversed(squeeze.values):
        if val:
            streak += 1
        else:
            break

    logger.debug(
        "Squeeze tespiti: aktif=%s, ardisik=%d gun", is_active, streak
    )
    return is_active, streak


# =============================================
# B. BEAR TRAP / LIQUIDITY SWEEP
# =============================================

def _find_support_levels(
    low_prices: pd.Series,
    window: int = 20,
) -> List[float]:
    """
    Yerel dip noktalarindan destek seviyeleri cikarir.

    Bir fiyat noktasi, cevresindeki ``window`` bar icinde en dusuk
    deger ise yerel destek sayilir.

    Parameters
    ----------
    low_prices : pd.Series
        Dusuk fiyat serisi.
    window : int
        Yerel minimum arama penceresi.

    Returns
    -------
    list of float
        Tespit edilen destek seviyeleri (dusukten yuksege).
    """
    supports = []
    half = window // 2

    for i in range(half, len(low_prices) - half):
        local_window = low_prices.iloc[i - half: i + half + 1]
        if low_prices.iloc[i] == local_window.min():
            supports.append(float(low_prices.iloc[i]))

    # Yakin seviyeleri birlestir (%1 tolerans)
    if not supports:
        return supports

    supports.sort()
    merged = [supports[0]]
    for s in supports[1:]:
        if abs(s - merged[-1]) / merged[-1] < 0.01:
            merged[-1] = (merged[-1] + s) / 2  # Ortalama al
        else:
            merged.append(s)

    return merged


def detect_bear_trap(
    prices: pd.DataFrame,
    lookback: int = 20,
    wick_threshold: float = 0.02,
) -> Tuple[bool, str]:
    """
    Ayi Tuzagi (Bear Trap / Liquidity Sweep) tespiti.

    Tahtacinin stop patlatmak icin yaptigi sahte asagi sarkitmalar:
    - Fiyat destek seviyesinin altina sarkiyor (low < support)
    - Ama ayni barda veya ertesi gun destege geri kapatiliyor (close > support)
    - Bu sahte kirilim, kucuk yatirimi panic satis yapmaya zorlar

    Parameters
    ----------
    prices : pd.DataFrame
        Fiyat verisi (open, high, low, close sutunlari).
    lookback : int
        Analiz penceresi (gun).
    wick_threshold : float
        Destek altina minimum sarkma orani (varsayilan: %2).

    Returns
    -------
    tuple of (bool, str, str)
        (tuzak_tespit_edildi_mi, detay_aciklamasi, son_tuzak_tarihi)
    """
    if prices.empty or len(prices) < lookback + 10:
        return False, "Yeterli veri yok", ""

    # Destek seviyelerini bul (onceki doneme bakarak)
    historical = prices.iloc[:-lookback] if len(prices) > lookback * 2 else prices.iloc[:lookback]
    supports = _find_support_levels(historical["low"], window=10)

    if not supports:
        return False, "Destek seviyesi bulunamadi", ""

    # Son lookback gunde destek alti sarkma kontrol et
    recent = prices.iloc[-lookback:]
    traps_found = []

    for support in supports:
        for idx in range(len(recent)):
            row = recent.iloc[idx]
            low = row["low"]
            close = row["close"]

            # Low destek altina sarkti mi?
            if low < support * (1 - wick_threshold):
                # Ama close destek ustunde mi? (Sahte kirilim)
                if close >= support * 0.99:  # %1 tolerans
                    trap_depth = (support - low) / support * 100
                    traps_found.append({
                        "tarih": recent.index[idx] if hasattr(recent.index[idx], 'strftime') else str(idx),
                        "destek": round(support, 2),
                        "sarkma_derinligi": round(trap_depth, 2),
                    })

    if traps_found:
        detail = (
            f"{len(traps_found)} ayi tuzagi tespit edildi. "
            f"Son tuzak: destek={traps_found[-1]['destek']}, "
            f"derinlik=%{traps_found[-1]['sarkma_derinligi']}"
        )
        logger.info("Bear Trap TESPIT: %s", detail)
        return True, detail, str(traps_found[-1]['tarih']).split()[0]

    return False, "Ayi tuzagi tespit edilemedi", ""


# =============================================
# C. VOLUME PROFILE & POC
# =============================================

def calculate_volume_profile(
    prices: pd.DataFrame,
    bins: int = 50,
) -> pd.DataFrame:
    """
    Volume Profile hesaplar: fiyat araligini kutulara bolup
    her kutudaki toplam hacmi hesaplar.

    Parameters
    ----------
    prices : pd.DataFrame
        Fiyat verisi (close, volume sutunlari).
    bins : int
        Fiyat araligi kutu sayisi.

    Returns
    -------
    pd.DataFrame
        Sutunlar: price_low, price_high, price_mid, total_volume
    """
    if prices.empty:
        return pd.DataFrame(
            columns=["price_low", "price_high", "price_mid", "total_volume"]
        )

    price_min = prices["low"].min()
    price_max = prices["high"].max()

    if price_min == price_max:
        return pd.DataFrame(
            columns=["price_low", "price_high", "price_mid", "total_volume"]
        )

    bin_edges = np.linspace(price_min, price_max, bins + 1)
    profile_data = []

    for i in range(len(bin_edges) - 1):
        low_edge = bin_edges[i]
        high_edge = bin_edges[i + 1]
        mid = (low_edge + high_edge) / 2

        # Bu fiyat bandinda islem goren hacim
        mask = (prices["close"] >= low_edge) & (prices["close"] < high_edge)
        vol = prices.loc[mask, "volume"].sum()

        profile_data.append({
            "price_low": round(low_edge, 4),
            "price_high": round(high_edge, 4),
            "price_mid": round(mid, 4),
            "total_volume": vol,
        })

    return pd.DataFrame(profile_data)


def find_poc(volume_profile: pd.DataFrame) -> float:
    """
    Point of Control (POC): En yogun hacmin dondugu fiyat noktasi.

    Bu seviye tahtacinin maliyet cizgisidir.

    Parameters
    ----------
    volume_profile : pd.DataFrame
        ``calculate_volume_profile`` ciktisi.

    Returns
    -------
    float
        POC fiyat seviyesi.
    """
    if volume_profile.empty:
        return 0.0

    max_idx = volume_profile["total_volume"].idxmax()
    poc = volume_profile.loc[max_idx, "price_mid"]

    logger.debug("POC hesaplandi: %.2f", poc)
    return float(poc)


def check_poc_breakout(
    prices: pd.DataFrame,
    poc: float,
    vol_multiplier: float = VOLUME_BREAKOUT_MULTIPLIER,
    ma_period: int = VOLUME_MA_PERIOD,
) -> Tuple[bool, dict]:
    """
    POC ustu hacimli kirilim kontrolu.

    Sartlar:
    - Fiyat POC seviyesinin ustune cikti
    - Kirilim gunu hacmi, son ``ma_period`` gunluk ortalama hacmin
      en az ``vol_multiplier`` kati

    Parameters
    ----------
    prices : pd.DataFrame
        Fiyat verisi (close, volume sutunlari).
    poc : float
        Point of Control seviyesi.
    vol_multiplier : float
        Minimum hacim carpani (varsayilan: 1.5).
    ma_period : int
        Hacim ortalama penceresi (varsayilan: 20).

    Returns
    -------
    tuple of (bool, dict)
        (kirilim_var_mi, detaylar)
    """
    if prices.empty or poc <= 0 or len(prices) < ma_period:
        return False, {"reason": "Yeterli veri yok"}

    last_close = prices["close"].iloc[-1]
    last_volume = prices["volume"].iloc[-1]
    avg_volume = prices["volume"].iloc[-ma_period:].mean()

    above_poc = last_close > poc
    volume_ok = last_volume >= avg_volume * vol_multiplier

    details = {
        "last_close": round(last_close, 2),
        "poc": round(poc, 2),
        "above_poc": above_poc,
        "last_volume": round(last_volume),
        "avg_volume": round(avg_volume),
        "volume_ratio": round(last_volume / avg_volume, 2) if avg_volume > 0 else 0,
        "volume_ok": volume_ok,
    }

    breakout = above_poc and volume_ok

    if breakout:
        logger.info(
            "POC Kirilimi ONAYLANDI: Fiyat=%.2f > POC=%.2f, "
            "Hacim=%d (%.1fx ortalama)",
            last_close, poc, last_volume,
            last_volume / avg_volume if avg_volume > 0 else 0,
        )

    return breakout, details


def check_retest_confirmation(
    prices: pd.DataFrame,
    broken_level: float,
    min_bars: int = RETEST_CONFIRMATION_BARS,
) -> Tuple[bool, int]:
    """
    Kirilan seviye ustunde retest (destek donusum) onayi.

    Fiyatin kirilan direnç/POC ustunde en az ``min_bars`` adet
    bar kapanisi yapmasi gerekir.

    Parameters
    ----------
    prices : pd.DataFrame
        Fiyat verisi (close sutunu).
    broken_level : float
        Kirilan seviye (direnç veya POC).
    min_bars : int
        Minimum bar kapanisi sayisi (varsayilan: 2).

    Returns
    -------
    tuple of (bool, int)
        (onaylandi_mi, ust_kapamayan_bar_sayisi)
    """
    if prices.empty or len(prices) < min_bars:
        return False, 0

    # Son barlarin kac tanesi seviye ustunde kapandi
    recent = prices["close"].iloc[-min_bars * 2:]  # 2x pencere ile bak
    above_count = 0

    # Son barlardan geriye dogru say
    for close_val in reversed(recent.values):
        if close_val > broken_level:
            above_count += 1
        else:
            break  # Ardisik kapanislar kopyalanir

    confirmed = above_count >= min_bars

    if confirmed:
        logger.info(
            "Retest ONAYLANDI: Seviye=%.2f, Ardisik ust kapanis=%d (min: %d)",
            broken_level, above_count, min_bars,
        )

    return confirmed, above_count


# =============================================
# D. BIRLESIK TUZAK SAVAR ANALIZI
# =============================================

def analyze_trap_setup(
    hisse: str,
    db_path: str = DB_PATH,
    lookback: int = 60,
) -> TrapAnalysis:
    """
    Tum tuzak savar alt bilesenlerini birlestirip tek bir
    TrapAnalysis sonucu dondurur.

    Birlesik skor bilesenleri:
    - Squeeze aktif: +25 puan
    - Bear trap tespit: +30 puan
    - POC kirilimi: +25 puan
    - Retest onayi: +20 puan

    Parameters
    ----------
    hisse : str
        Hisse sembolu.
    db_path : str
        SQLite veritabani dosya yolu.
    lookback : int
        Analiz penceresi (gun).

    Returns
    -------
    TrapAnalysis
        Birlesik analiz sonucu.
    """
    logger.info("Tuzak Savar analizi baslatiliyor: %s", hisse)

    result = TrapAnalysis()

    # Fiyat verisini cek
    sql = """
        SELECT tarih, open, high, low, close, volume
        FROM price_data
        WHERE hisse = ?
        ORDER BY tarih ASC
    """
    try:
        prices = query_df(sql, params=(hisse,), db_path=db_path)
    except Exception as e:
        logger.error("Fiyat verisi cekilemedi [%s]: %s", hisse, e)
        return result

    if prices.empty or len(prices) < 20:
        logger.warning("Tuzak analizi icin yeterli fiyat verisi yok: %s (%d gun)", hisse, len(prices))
        return result

    # A. Bollinger Squeeze
    try:
        squeeze_active, squeeze_days = detect_squeeze(
            prices["close"], prices["high"], prices["low"]
        )
        result.squeeze_active = squeeze_active
        result.details["squeeze_days"] = squeeze_days
    except Exception as e:
        logger.error("Squeeze tespiti hatasi [%s]: %s", hisse, e)

    # B. Bear Trap
    try:
        trap_found, trap_detail, trap_date = detect_bear_trap(prices, lookback=min(lookback, len(prices) - 10))
        result.bear_trap_detected = trap_found
        result.bear_trap_details = trap_detail
        result.last_sweep_date = trap_date
    except Exception as e:
        logger.error("Bear trap tespiti hatasi [%s]: %s", hisse, e)

    # Nearest Support for "Pusuda Bekle"
    try:
        last_close = float(prices["close"].iloc[-1])
        result.details["last_close"] = last_close
        supports = _find_support_levels(prices["low"], window=min(len(prices)//2, 20))
        below_supports = [s for s in supports if s < last_close]
        if below_supports:
            result.details["nearest_support"] = max(below_supports)
        else:
            result.details["nearest_support"] = 0.0
    except Exception as e:
        logger.error("Destek tespiti hatasi [%s]: %s", hisse, e)
        result.details["nearest_support"] = 0.0

    # C. Volume Profile & POC
    try:
        vp = calculate_volume_profile(prices)
        poc = find_poc(vp)
        result.poc_level = poc
        result.details["volume_profile_bins"] = len(vp)

        # POC kirilimi
        if poc > 0:
            breakout, breakout_details = check_poc_breakout(prices, poc)
            result.poc_breakout = breakout
            result.details["poc_breakout"] = breakout_details

            # Retest onayi (sadece kirilim varsa anlamli)
            if breakout:
                retest_ok, retest_bars = check_retest_confirmation(prices, poc)
                result.retest_confirmed = retest_ok
                result.details["retest_bars"] = retest_bars

    except Exception as e:
        logger.error("Volume Profile/POC hatasi [%s]: %s", hisse, e)

    # D. Birlesik skor
    score = 0.0
    if result.squeeze_active:
        score += 25.0
    if result.bear_trap_detected:
        score += 30.0
    if result.poc_breakout:
        score += 25.0
    if result.retest_confirmed:
        score += 20.0

    result.trap_score = score

    logger.info(
        "Tuzak Savar [%s]: Skor=%.0f | Squeeze=%s, BearTrap=%s, "
        "POC=%.2f, Kirilim=%s, Retest=%s",
        hisse, score,
        result.squeeze_active,
        result.bear_trap_detected,
        result.poc_level,
        result.poc_breakout,
        result.retest_confirmed,
    )

    return result
