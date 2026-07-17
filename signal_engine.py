# -*- coding: utf-8 -*-
"""
Tahtaci Avcisi v1.0 — Sinyal Motoru Modulu
===========================================
Tum katmanlari (Tahtaci Skoru, Endeks Kilidi, Tuzak Savar)
birlestirerek nihai Piramit Alim ve Cikis sinyallerini uretir.

Sinyal Mantigi:
---------------
1. Endeks Kilidi "LOCKED" ise hicbir islem yapilmaz.
2. Tahtaci Skoru < 40 ise alim sinyali uretilmez.
3. Piramit Giris Sinyalleri:
   - Parca 1 (%30): Bear Trap onayli + Fiyat POC etrafinda
   - Parca 2 (%40): POC Kirilimi + Retest onayli
   - Parca 3 (%30): Parca 2 onayli + Higher High (Yeni Zirve)
4. Dagitim/Cikis Sinyali:
   - Fiyat < EMA21 ve "Diger" kolonu alici yonune gectiyse (egim > 0)

Kullanim
--------
>>> from signal_engine import generate_signals
>>> results = generate_signals(["EREGL", "THYAO"])
"""

import logging
from typing import List, Dict, Any, Tuple
import pandas as pd

from config import (
    DB_PATH,
    EMA21_PERIOD,
    DIGER_MA_WINDOW,
)
from database import query_df
from index_lock import get_market_status, MarketStatus
from analyzer import calculate_tahtaci_score, check_smc_sniper_entry
from trap_detector import analyze_trap_setup, TrapAnalysis

logger = logging.getLogger(__name__)


# =============================================
# GIRIS/CIKIS KOSULLARI
# =============================================

def check_entry_1(
    trap: TrapAnalysis,
    last_close: float,
    tahtaci_score: float,
) -> bool:
    """
    1. Parca Alim Sinyali (%30): 
    Dipte tuzak onayi ve Tahtaci maliyetine (POC) yakinlik.
    
    Sartlar:
    - Tahtaci Skoru >= 40
    - Bear Trap tespit edilmis
    - Fiyat POC seviyesine yakin (POC'un %5 alti ile %2 ustu arasi)
    """
    if tahtaci_score < 40:
        return False
    
    if not trap.bear_trap_detected:
        return False

    if trap.poc_level > 0:
        # POC'un %5 alti ile %2 ustu arasi "yakin" kabul edilir
        lower_bound = trap.poc_level * 0.95
        upper_bound = trap.poc_level * 1.02
        if lower_bound <= last_close <= upper_bound:
            return True

    return False


def check_entry_2(
    trap: TrapAnalysis,
    tahtaci_score: float,
) -> bool:
    """
    2. Parca Alim Sinyali (%40): 
    Maliyet kirilimi ve retest onayi.
    
    Sartlar:
    - Tahtaci Skoru >= 60 (Guclu sinyal sarti)
    - POC Kirilimi var
    - Retest (kapanis) onayli
    """
    if tahtaci_score < 60:
        return False
    
    if trap.poc_breakout and trap.retest_confirmed:
        return True

    return False


def check_entry_3(
    prices: pd.DataFrame,
    entry_2_active: bool,
) -> bool:
    """
    3. Parca Alim Sinyali (%30): 
    Trend onayi (Higher High / Yeni Zirve).
    
    Sartlar:
    - 2. Parca aktif olmali
    - Son kapanis, onceki N gunluk yerel tepeden yuksek olmali
    """
    if not entry_2_active or prices.empty or len(prices) < 20:
        return False

    # Son 20 gunun en yuksek kapanisini bul (son gun haric)
    recent_high = prices["close"].iloc[-21:-1].max()
    last_close = prices["close"].iloc[-1]

    if last_close > recent_high:
        return True

    return False


def check_exit_signal(
    hisse: str,
    prices: pd.DataFrame,
    tahtaci_result: Dict[str, Any],
    db_path: str = DB_PATH,
) -> bool:
    """
    Dagitim / Cikis Sinyali:
    Tahtacinin mali kucuk yatirimciya yiktigi ve trendin bittigi an.
    
    Sartlar:
    - Fiyat < EMA21 (Trend bozuldu)
    - "Diger" kolonu egimi pozitif (Kucuk yatirimci agresif alici)
    """
    if prices.empty or len(prices) < EMA21_PERIOD:
        return False

    # 1. EMA21 Kirilimi
    ema21 = prices["close"].ewm(span=EMA21_PERIOD, adjust=False).mean()
    last_close = prices["close"].iloc[-1]
    last_ema21 = ema21.iloc[-1]
    
    trend_broken = last_close < last_ema21

    # 2. Diger Kolonu Alici mi? (Egim > 0 ise Diger kolonu artiyor demektir)
    sub_scores = tahtaci_result.get("sub_scores", {})
    # Bizim analyzer.py'de Diger Egimi negatifligi uzerinden skorlaniyor.
    # Ham degere ihtiyacimiz var, veritabanindan hizlica "Diger Net" cekelim
    sql = """
        SELECT tarih, kurum_adi, net_lot
        FROM akd_data
        WHERE hisse = ? AND kurum_adi = 'Diğer'
        ORDER BY tarih ASC
    """
    try:
        diger_df = query_df(sql, params=(hisse,), db_path=db_path)
    except Exception:
        diger_df = pd.DataFrame()

    diger_buying = False
    if not diger_df.empty and len(diger_df) >= DIGER_MA_WINDOW:
        # Son gunlerin Diger net lot ortalamasi pozitif mi?
        recent_diger_net = diger_df["net_lot"].iloc[-DIGER_MA_WINDOW:].mean()
        if recent_diger_net > 0:
            diger_buying = True

    if trend_broken and diger_buying:
        logger.warning(
            "CIKIS SINYALI [%s]: Fiyat(%.2f) < EMA21(%.2f) ve 'Diger' alicida!",
            hisse, last_close, last_ema21
        )
        return True

    return False

# =============================================
# HIBRIT STRATEJI (GIZLI TOPLAMA, MALIYET SAVUNMASI, TAKAS TEYIDI)
# =============================================

def evaluate_hybrid_strategy(
    hisse: str, 
    prices: pd.DataFrame, 
    tahtaci_result: Dict[str, Any], 
    db_path: str
) -> Tuple[List[str], float]:
    """
    3. Secenek (Hibrit Strateji): Gizli Toplama, Maliyet Savunmasi ve Takas Teyidi.
    Sinyalleri ve ekstra skoru dondurur.
    """
    signals = []
    bonus_score = 0.0
    
    if prices.empty or len(prices) < 5:
        return signals, bonus_score
        
    last_close = prices["close"].iloc[-1]
    
    # 1. Gizli Toplama (Hidden Accumulation)
    recent_prices = prices["close"].iloc[-6:]
    price_change = (last_close - recent_prices.iloc[0]) / recent_prices.iloc[0] * 100
    
    if price_change < 2.0 and tahtaci_result.get("tahtaci_score", 0) > 50:
        sql = "SELECT net_lot FROM akd_data WHERE hisse = ? AND kurum_adi = 'Diğer' ORDER BY tarih DESC LIMIT 3"
        try:
            diger_df = query_df(sql, params=(hisse,), db_path=db_path)
            if not diger_df.empty and diger_df["net_lot"].mean() < 0:
                signals.append("🕵️ GİZLİ TOPLAMA (Fiyat baskılanırken balina mal alıyor)")
                bonus_score += 20.0
        except Exception:
            pass

    # 2. Maliyet Savunması (Pullback & Defend)
    buyer_cost = tahtaci_result.get("buyer_cost", 0.0)
    if buyer_cost > 0:
        cost_diff_pct = ((last_close - buyer_cost) / buyer_cost) * 100
        if abs(cost_diff_pct) <= 1.5:
            top_buyer = tahtaci_result.get("top_buyer_name", "")
            if top_buyer:
                sql = "SELECT net_lot FROM akd_data WHERE hisse = ? AND kurum_adi = ? ORDER BY tarih DESC LIMIT 1"
                try:
                    son_akd = query_df(sql, params=(hisse, top_buyer), db_path=db_path)
                    if not son_akd.empty and son_akd["net_lot"].iloc[0] > 0:
                        signals.append("🛡️ MALİYET SAVUNMASI (Tahtacı destekte alıma geçti)")
                        bonus_score += 25.0
                except Exception:
                    pass
                    
    # 3. T+2 Takas Virman Teyidi (Custody Confirmation)
    sql = "SELECT saklama_adet FROM takas_data WHERE hisse = ? AND (kurum_adi LIKE '%CITIBANK%' OR kurum_adi LIKE '%DEUTSCHE%') ORDER BY tarih DESC LIMIT 4"
    try:
        yabanci_df = query_df(sql, params=(hisse,), db_path=db_path)
        if len(yabanci_df) >= 2:
            if yabanci_df["saklama_adet"].iloc[0] > yabanci_df["saklama_adet"].iloc[-1]:
                signals.append("🏦 TAKAS TEYİDİ (Yabancı/Saklama kurumlarına virman onaylı)")
                bonus_score += 15.0
    except Exception:
        pass

    return signals, bonus_score


# =============================================
# ORKESTRATOR
# =============================================

def generate_signals(
    hisseler: List[str],
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Tum hisseler icin sinyal motorunu calistirir.
    Endeks kilidini kontrol eder ve her hisse icin 
    Tahtaci Skoru + Tuzak Analizi yaparak nihai karar uretir.
    """
    logger.info("============================================================")
    logger.info("SINYAL MOTORU BASLATILIYOR")
    logger.info("============================================================")

    results = []

    # 1. Endeks Kilidi Kontrolu
    market_status = get_market_status(db_path)
    
    if market_status == MarketStatus.LOCKED:
        logger.warning("Sistem KILITLI (MarketStatus.LOCKED). Sinyal uretilmeyecek.")
        return [{
            "hisse": "ENDEKS_KILIDI",
            "market_status": market_status.name,
            "error": "Sistem kilitli, sinyal analizleri durduruldu.",
        }]

    # 2. Hisse Bazli Analiz
    for hisse in hisseler:
        logger.info("Sinyal Analizi: %s", hisse)
        
        # Fiyat verisini cek
        sql = """
            SELECT tarih, open, high, low, close, volume
            FROM price_data
            WHERE hisse = ?
            ORDER BY tarih ASC
        """
        prices = query_df(sql, params=(hisse,), db_path=db_path)
        
        if prices.empty:
            logger.error("Veri yok: %s", hisse)
            results.append({"hisse": hisse, "error": "Veri yok"})
            continue
            
        last_close = prices["close"].iloc[-1]

        # A. Tahtaci Skoru
        score_res = calculate_tahtaci_score(hisse)
        tahtaci_score = score_res.get("tahtaci_score", 0.0)
        is_downtrend = score_res.get("is_downtrend", False)

        # A2. Tahtacı Maliyet Haritası (Faz 4)
        from database import get_buyer_cost
        top_buyer = score_res.get("top_buyer_name", "")
        buyer_cost = 0.0
        if top_buyer and top_buyer != "Bilinmiyor":
            buyer_cost = get_buyer_cost(hisse, top_buyer, days=10, db_path=db_path)
            score_res["buyer_cost"] = buyer_cost
            
            if buyer_cost > 0:
                cost_diff_pct = ((last_close - buyer_cost) / buyer_cost) * 100
                score_res["cost_diff_pct"] = cost_diff_pct
                
                # Kör Nokta Alım Sinyali Kontrolü (Maliyete %2 marj içindeyse)
                if abs(cost_diff_pct) <= 2.0:
                    tahtaci_score += 15.0 # Kör nokta bonusu
                    score_res["blind_spot"] = True
                elif cost_diff_pct < -2.0:
                    # Maliyetin altına sarkmış (Risk/Stop patlatma)
                    tahtaci_score -= 10.0
                    
        # A3. Karanlık Oda Analizi (Faz 2)
        # Gerçek veritabanında 18:00 ve 18:10 verileri ayrı ayrı olmalıdır.
        # Şimdilik altyapı hazırlandı, gerçek veri gelene kadar NÖTR döndürür.
        from depth_analyzer import analyze_dark_pool
        avg_vol = prices["volume"].iloc[-10:].mean() if len(prices) >= 10 else prices["volume"].iloc[-1]
        
        dark_pool_res = analyze_dark_pool(
            symbol=hisse,
            close_price_1800=last_close,
            match_price_1810=last_close, # Gerçek veri yok, aynı fiyat
            match_volume=0,              # Gerçek eşleşme hacmi yok
            avg_daily_volume=avg_vol
        )
        
        # Skor modifikasyonu
        tahtaci_score += dark_pool_res["score_modifier"]
        # Skoru 0-100 sınırlarında tut
        tahtaci_score = max(0.0, min(100.0, tahtaci_score))

        # B. Tuzak Analizi
        trap_res = analyze_trap_setup(hisse, db_path=db_path)
        
        # B2. SMC Sniper Check
        smc_sniper = False
        if trap_res.bear_trap_detected and trap_res.last_sweep_date:
            smc_sniper = check_smc_sniper_entry(hisse, trap_res.last_sweep_date, db_path)

        # C. Sinyal Uretimi
        entry_signals = []
        exit_signal = False
        
        # HIBRIT STRATEJI KONTROLU
        hybrid_signals, hybrid_bonus = evaluate_hybrid_strategy(hisse, prices, score_res, db_path)
        if hybrid_signals:
            entry_signals.extend(hybrid_signals)
            tahtaci_score += hybrid_bonus
            tahtaci_score = max(0.0, min(100.0, tahtaci_score))

        
        if dark_pool_res["signal"] != "NÖTR":
            entry_signals.append(f"Karanlık Oda: {dark_pool_res['signal']} (Skor Etkisi: {dark_pool_res['score_modifier']:+d})")
            
        if score_res.get("blind_spot"):
            entry_signals.append("🎯 KÖR NOKTA ALIMI: Fiyat Tahtacı maliyetine çok yakın!")
            
        # PASSIVE modda sadece cikis sinyalleri uretilir, yeni giris uretilmez
        if market_status == MarketStatus.ACTIVE:
            if smc_sniper:
                entry_signals.append("SMC SNIPER (GÖZÜ KAPALI GİR)")
                
            e1 = check_entry_1(trap_res, last_close, tahtaci_score)
            if e1: entry_signals.append("ENTRY_1 (%30)")
            
            e2 = check_entry_2(trap_res, tahtaci_score)
            if e2: entry_signals.append("ENTRY_2 (%40)")
            
            e3 = check_entry_3(prices, e2)
            if e3: entry_signals.append("ENTRY_3 (%30)")

        exit_signal = check_exit_signal(hisse, prices, score_res, db_path)

        # Karar Ozeti
        if exit_signal:
            summary = "[!!!] CIKIS (DAGITIM) SINYALI"
        elif entry_signals:
            summary = f"[+] ALIM SINYALI: {', '.join(entry_signals)}"
        else:
            nearest = trap_res.details.get("nearest_support", 0.0)
            poc_val = trap_res.poc_level if trap_res and hasattr(trap_res, 'poc_level') else 0.0
            
            if is_downtrend:
                summary = "[!] TEHLIKELI DUSUS TRENDI (Dusen Bicak)"
            elif last_close > 0 and nearest > 0 and nearest < last_close:
                drop_pct = ((last_close - nearest) / last_close) * 100
                summary = f"[-] PUSUDA BEKLE (Tuzak Hedefi: {nearest:.2f} TL | %{drop_pct:.1f} aşağıda)"
            elif last_close > 0 and poc_val > last_close:
                dist_pct = ((poc_val - last_close) / last_close) * 100
                summary = f"[-] PUSUDA BEKLE (Direnç Kırılım Hedefi: {poc_val:.2f} TL | %{dist_pct:.1f} yukarıda)"
            else:
                summary = "[-] IZLEMEDE"
        # Ozeti uret (UI'da gostermek icin)
        summary = f"Fiyat: {last_close:.2f} | Skor: {tahtaci_score:.1f}"
        if entry_signals:
            summary += " | Sinyal: " + " + ".join(entry_signals)
        if exit_signal:
            summary += " | DIKKAT: SAT Sinyali"
            
        summary += f"\n{dark_pool_res['message']}"

        results.append({
            "hisse": hisse,
            "tahtaci_score": tahtaci_score,
            "tahtaci_details": score_res,
            "sub_scores": score_res.get("sub_scores", {}),
            "is_downtrend": is_downtrend,
            "trap_analysis": trap_res,
            "smc_sniper": smc_sniper,
            "entry_signals": entry_signals,
            "exit_signal": exit_signal,
            "market_status": market_status.name,
            "summary": summary,
            "last_close": float(last_close),
            "dark_pool": dark_pool_res
        })

    return results
