# -*- coding: utf-8 -*-
"""
Derinlik ve Sahte Emir (Spoofing) Analiz Modülü

Tahtadaki alış-satış lot yığılmalarını analiz eder.
Özellikle üst kademelerde anlamsız büyüklükteki "Korkutma (Spoofing)" satışlarını
veya alt kademelerdeki "Sahte Alış" desteklerini tespit eder.
"""

import pandas as pd

def analyze_depth_spoofing(df: pd.DataFrame) -> dict:
    """
    Derinlik tablosunu analiz eder ve spoofing ihtimalini değerlendirir.
    
    Parameters:
        df (pd.DataFrame): fetch_derinlik() metodundan dönen canlı derinlik verisi.
                           Sütunlar: hisse, kademe, alis_lot, alis_fiyat, satis_fiyat, satis_lot
                           
    Returns:
        dict: Analiz sonuçları.
              {
                  "total_bid": int,
                  "total_ask": int,
                  "bid_ask_ratio": float,
                  "spoofing_detected": bool,
                  "spoof_direction": str, # "ASK" veya "BID"
                  "warning_message": str
              }
    """
    if df.empty:
        return {
            "total_bid": 0, "total_ask": 0, "bid_ask_ratio": 1.0, 
            "spoofing_detected": False, "spoof_direction": "", 
            "warning_message": "Derinlik verisi yok."
        }
        
    total_bid = df["alis_lot"].sum()
    total_ask = df["satis_lot"].sum()
    
    bid_ask_ratio = total_bid / total_ask if total_ask > 0 else 999.0
    
    spoofing_detected = False
    spoof_direction = ""
    warning_message = ""
    
    # Kademelerdeki lot oranlarına bak (Ortalamanın x katı bir lot varsa)
    avg_bid = df["alis_lot"].mean()
    avg_ask = df["satis_lot"].mean()
    
    max_bid = df["alis_lot"].max()
    max_ask = df["satis_lot"].max()
    
    # Eger bir kademedeki satis, ortalama satisin 5 katindan fazlaysa ve
    # toplam ask_lot bid_lot'un uzerindeyse -> Satis Spoofing (Baski kurma)
    if avg_ask > 0 and max_ask > avg_ask * 5:
        spoofing_detected = True
        spoof_direction = "ASK"
        warning_message = "DİKKAT: Üst kademelerde devasa yığılma (Satış Baskısı/Spoofing) var. Tahtacı fiyatı baskılıyor olabilir."
        
    elif avg_bid > 0 and max_bid > avg_bid * 5:
        spoofing_detected = True
        spoof_direction = "BID"
        warning_message = "DİKKAT: Alt kademelerde devasa yığılma (Alış Spoofing) var. Fiyatın aşağı düşmesi engelleniyor gibi gösterilebilir."
        
    return {
        "total_bid": int(total_bid),
        "total_ask": int(total_ask),
        "bid_ask_ratio": round(bid_ask_ratio, 2),
        "spoofing_detected": spoofing_detected,
        "spoof_direction": spoof_direction,
        "warning_message": warning_message
    }

def analyze_dark_pool(symbol: str, close_price_1800: float, match_price_1810: float, match_volume: float, avg_daily_volume: float) -> dict:
    """
    Karanlık Oda (18:05 - 18:10 Eşleşme Seansı) Analizi
    Tahtacıların gün sonu eşleşmesinde büyük hacimlerle fiyatı manipüle etmesini tespit eder.
    
    Parameters:
        symbol (str): Hisse sembolü
        close_price_1800 (float): 18:00'daki normal seans kapanış fiyatı
        match_price_1810 (float): 18:10'daki eşleşme fiyatı
        match_volume (float): Eşleşme seansında gerçekleşen lot hacmi
        avg_daily_volume (float): Son 10 günlük ortalama hacim
        
    Returns:
        dict: Karanlık oda analiz sonuçları ve Tahtacı Skoru çarpanı
    """
    if close_price_1800 == 0 or avg_daily_volume == 0:
        return {"signal": "NÖTR", "score_modifier": 0, "message": "Yetersiz veri."}
        
    price_diff_pct = ((match_price_1810 - close_price_1800) / close_price_1800) * 100
    volume_ratio = (match_volume / avg_daily_volume) * 100
    
    # Eşleşme hacmi günlük ortalamanın %5'inden fazlaysa bu çok ciddi bir harekettir
    is_high_volume = volume_ratio > 5.0
    
    signal = "NÖTR"
    score_modifier = 0
    message = "Karanlık odada olağandışı bir hareket yok."
    
    if is_high_volume:
        if price_diff_pct > 0.5:
            # Fiyatı yukarı sürdüler
            signal = "GÜÇLÜ ALIM"
            score_modifier = +15
            message = f"🦇 KARANLIK ODA: Yüksek hacimle ({volume_ratio:.1f}%) fiyat {price_diff_pct:.1f}% yukarı çekildi! Tahtacı agresif mal topladı."
        elif price_diff_pct < -0.5:
            # Fiyatı aşağı bastılar
            signal = "GÜÇLÜ SATIŞ"
            score_modifier = -15
            message = f"🦇 KARANLIK ODA: Yüksek hacimle ({volume_ratio:.1f}%) fiyat {price_diff_pct:.1f}% aşağı basıldı! Panik satışı veya mal çıkışı."
        elif price_diff_pct >= 0:
             signal = "GİZLİ ALIM"
             score_modifier = +5
             message = f"🦇 KARANLIK ODA: Fiyat değişmeden devasa hacim eşleşti ({volume_ratio:.1f}%). Gizli el değiştirme (Cep to Cep / Fon virmanı) ihtimali."
    
    return {
        "signal": signal,
        "score_modifier": score_modifier,
        "price_diff_pct": round(price_diff_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "message": message
    }
