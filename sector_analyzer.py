# -*- coding: utf-8 -*-
"""
Sektörel Para Akışı ve Isı Haritası Analizi
=============================================
Bu modül, BIST hisselerini sektörlerine ayırarak genel para giriş/çıkışlarını
hesaplar ve Tahtacı'nın (akıllı paranın) hangi sektörlere rotasyon yaptığını bulur.
"""

import pandas as pd
from database import query_df
from config import DB_PATH
import logging

logger = logging.getLogger(__name__)

# BIST Hisse -> Sektör Eşleştirmesi (Temel)
SECTOR_MAP = {
    # Bankacılık
    "AKBNK": "Bankacılık", "GARAN": "Bankacılık", "ISCTR": "Bankacılık", 
    "YKBNK": "Bankacılık", "VAKBN": "Bankacılık", "HALKB": "Bankacılık", 
    "ALBRK": "Bankacılık", "SKBNK": "Bankacılık",
    
    # Holding
    "KCHOL": "Holding", "SAHOL": "Holding", "SISE": "Holding", 
    "DOHOL": "Holding", "ENKAI": "Holding", "TKFEN": "Holding",
    
    # Havacılık ve Ulaşım
    "THYAO": "Havacılık", "PGSUS": "Havacılık", "TAVHL": "Havacılık",
    "CLEBI": "Havacılık",
    
    # Otomotiv
    "FROTO": "Otomotiv", "TOASO": "Otomotiv", "DOAS": "Otomotiv", 
    "OTKAR": "Otomotiv", "KARSN": "Otomotiv",
    
    # Demir Çelik & Metal
    "EREGL": "Demir/Çelik", "KRDMD": "Demir/Çelik", "ISDMR": "Demir/Çelik", 
    "CEMTS": "Demir/Çelik", "KCAER": "Demir/Çelik",
    
    # Enerji
    "TUPRS": "Enerji", "ASTOR": "Enerji", "ALFAS": "Enerji", 
    "GESAN": "Enerji", "SMRTG": "Enerji", "GWIND": "Enerji",
    "ENJSA": "Enerji", "ZOREN": "Enerji",
    
    # Perakende & Gıda
    "BIMAS": "Perakende/Gıda", "MGROS": "Perakende/Gıda", "SOKM": "Perakende/Gıda", 
    "ULKER": "Perakende/Gıda", "AEFES": "Perakende/Gıda", "CCOLA": "Perakende/Gıda",
    
    # İletişim & Bilişim
    "TCELL": "Teknoloji/İletişim", "TTKOM": "Teknoloji/İletişim", "MIATK": "Teknoloji/İletişim",
    "KONTK": "Teknoloji/İletişim", "ASELS": "Teknoloji/İletişim",
    
    # GYO & İnşaat
    "EKGYO": "GYO", "ISGYO": "GYO", "TRGYO": "GYO", 
    "HLGYO": "GYO", "OZKGY": "GYO",
    
    # Madencilik & Kimya
    "KOZAA": "Madencilik/Kimya", "KOZAL": "Madencilik/Kimya", "IPEK": "Madencilik/Kimya",
    "PETKM": "Madencilik/Kimya", "SASA": "Madencilik/Kimya", "HEKTS": "Madencilik/Kimya",
}

def get_sector(symbol: str) -> str:
    """Hissenin sektörünü döndürür."""
    return SECTOR_MAP.get(symbol.upper(), "Diğer")

def analyze_sectoral_money_flow(days: int = 5) -> pd.DataFrame:
    """
    Son X gündeki AKD verisini çekerek sektörel net para girişini/çıkışını hesaplar.
    Kurumsal net alışları (ilk 5 kurum) sektör bazında toplar.
    """
    try:
        # Son 'days' güne ait net alıcıların verisini çekelim (örnek yaklaşımla net lot > 0)
        # Gerçekte fiyata da ihtiyacımız var parayı bulmak için, ama şimdilik net lot üzerinden bir momentum puanı üretebiliriz.
        # AKD tablomuzda 'net_lot', 'hisse', 'tarih' vb. var.
        
        # Basitlik için sadece ilk 5 büyük kurumun alımlarını 'para girişi' sayalım.
        # Gerçek veritabanında net_lot değerlerini kullanacağız.
        query = """
            SELECT hisse, kurum_adi, net_lot, tarih 
            FROM akd_data 
            ORDER BY tarih DESC
        """
        df = query_df(query, db_path=DB_PATH)
        
        if df.empty:
            return pd.DataFrame()
            
        # Sektörleri ekle
        df['sektor'] = df['hisse'].apply(get_sector)
        
        # Sadece pozitif net_lot'u olanları (alıcıları) baz alıyoruz
        # Net kurumsal giriş: İlk 5 kurumun net alımı. Veya genel net lot toplamı.
        # Burada basitleştirilmiş bir model yapıyoruz: Sektördeki pozitif hacimleri topla.
        buy_df = df[df['net_lot'] > 0]
        
        sector_flow = buy_df.groupby('sektor')['net_lot'].sum().reset_index()
        sector_flow.rename(columns={'net_lot': 'toplam_net_lot_girisi'}, inplace=True)
        
        # Sektördeki hisse sayısına bölerek normalize edebiliriz (Sektör yoğunluğu)
        sector_counts = df.groupby('sektor')['hisse'].nunique().reset_index()
        sector_counts.rename(columns={'hisse': 'hisse_sayisi'}, inplace=True)
        
        res = pd.merge(sector_flow, sector_counts, on='sektor')
        res['yogunluk_skoru'] = res['toplam_net_lot_girisi'] / res['hisse_sayisi']
        
        # Puanlama 0-100 arasına çekelim
        max_score = res['yogunluk_skoru'].max()
        if max_score > 0:
            res['isi_derecesi'] = (res['yogunluk_skoru'] / max_score) * 100
        else:
            res['isi_derecesi'] = 0
            
        res = res.sort_values(by='isi_derecesi', ascending=False).reset_index(drop=True)
        return res
        
    except Exception as e:
        logger.error(f"Sektörel akış analizi hatası: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    print("Sektörel Para Akışı Testi:")
    df = analyze_sectoral_money_flow()
    if not df.empty:
        print(df)
    else:
        print("Veri bulunamadı.")
