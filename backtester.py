# -*- coding: utf-8 -*-
"""
Backtest Motoru (Geriye Dönük Performans Testi)
================================================
Geçmiş tarihlerde "Tahtacı Skoru" yüksek çıkan hisselerin (ör. Skor > 70),
alım yapıldıktan T+N gün sonraki getirilerini hesaplayarak sistemin başarı oranını (Win Rate) ölçer.
"""

import pandas as pd
from database import query_df
from config import DB_PATH
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def run_backtest(min_score: float = 70.0, holding_period_days: int = 15) -> dict:
    """
    Sistemin geçmiş verilerdeki başarı oranını hesaplar.
    Gerçek bir uygulamada tarihi 'Tahtacı Skorları'nın veritabanına kaydedilmiş olması
    veya geçmiş verilere göre yeniden hesaplanması gerekir.
    
    Burada basit bir simülasyon yapıyoruz: (Eğer geçmiş fiyat ve sinyal verimiz varsa)
    """
    try:
        # Örnek olarak, eğer veritabanımızda 'signals' adında bir tablomuz olsaydı 
        # oradan çekerdik. Biz şimdilik fiyat datası olan hisseler üzerinden sembolik
        # bir yapı kuralım veya gerçek veriye bağlayalım.
        
        # 1. Fiyat verisini çekelim
        price_query = "SELECT hisse, tarih, close FROM price_data ORDER BY tarih ASC"
        price_df = query_df(price_query, db_path=DB_PATH)
        
        if price_df.empty:
            return {"error": "Fiyat verisi bulunamadı."}
            
        # 2. Şimdilik "geçmiş Tahtacı Skorları" kaydımız olmadığı için,
        # sistemin test mantığını kurup rastgele seçilmiş geçmiş tarihlerde 
        # "sanki alım yapılmış gibi" bir simülasyon (dummy data) yapalım ki UI çalışsın.
        # İleride her günün Tahtacı Skoru DB'ye kaydedildiğinde burası o tabloyu okur.
        
        # Gerçek veritabanından simülasyon: Son 30 günün rastgele bir noktasında %10 artış bulan hisseler
        result = {
            "toplam_islem": 0,
            "basarili_islem": 0,
            "win_rate": 0.0,
            "ortalama_getiri": 0.0,
            "max_kazanc": 0.0,
            "max_kayip": 0.0,
            "detaylar": []
        }
        
        # Örnek: THYAO, ISCTR, TUPRS
        test_hisseler = price_df['hisse'].unique()
        if len(test_hisseler) == 0:
            return result
            
        islem_sayisi = 0
        basarili = 0
        toplam_getiri = 0
        max_k = 0
        max_z = 0
        
        for h in list(test_hisseler)[:5]: # Sadece 5 hisse ile test
            hdf = price_df[price_df['hisse'] == h].copy()
            if len(hdf) > holding_period_days:
                # Farz edelim ilk gün Tahtacı Skoru 85 çıktı ve AL verdik
                alis_fiyati = hdf.iloc[0]['close']
                alis_tarihi = hdf.iloc[0]['tarih']
                
                satis_fiyati = hdf.iloc[holding_period_days]['close']
                satis_tarihi = hdf.iloc[holding_period_days]['tarih']
                
                getiri_yuzde = ((satis_fiyati - alis_fiyati) / alis_fiyati) * 100
                
                islem_sayisi += 1
                toplam_getiri += getiri_yuzde
                
                if getiri_yuzde > 0:
                    basarili += 1
                
                if getiri_yuzde > max_k:
                    max_k = getiri_yuzde
                if getiri_yuzde < max_z:
                    max_z = getiri_yuzde
                    
                result["detaylar"].append({
                    "hisse": h,
                    "alis_tarihi": alis_tarihi,
                    "alis_fiyati": alis_fiyati,
                    "satis_tarihi": satis_tarihi,
                    "satis_fiyati": satis_fiyati,
                    "getiri": getiri_yuzde
                })
                
        if islem_sayisi > 0:
            result["toplam_islem"] = islem_sayisi
            result["basarili_islem"] = basarili
            result["win_rate"] = (basarili / islem_sayisi) * 100
            result["ortalama_getiri"] = toplam_getiri / islem_sayisi
            result["max_kazanc"] = max_k
            result["max_kayip"] = max_z
            
        return result
        
    except Exception as e:
        logger.error(f"Backtest motoru hatası: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    print(run_backtest())
