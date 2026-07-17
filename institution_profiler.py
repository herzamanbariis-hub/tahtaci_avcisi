# -*- coding: utf-8 -*-
"""
Kurum Profilleme (Institution Profiling) Modülü

Bu modül, Borsa İstanbul'daki aracı kurumları alım-satım karakterlerine göre sınıflandırır.
Tahtacı skorunu hesaplarken kurumun "kimliğine" göre çarpan (ağırlık) uygulanmasını sağlar.
"""

from typing import Dict, Tuple

# Kurum Tipleri
TYPE_DAILY = "DAILY_TRADER"       # Algoritmik, günlükçü, hızlı girip çıkan (Örn: BofA)
TYPE_SPECULATIVE = "SPECULATIVE"  # Operasyon kurumları, sığ tahtalarda manipülatif hareket edebilen (Örn: Info, Marbaş)
TYPE_LONG_TERM = "LONG_TERM"      # Fonlar, yatırım ve emeklilik kurumları (Örn: Emeklilik Fonları, İş Yatırım)
TYPE_FOREIGN = "FOREIGN"          # Yabancı saklama (Örn: Citibank, Deutsche)
TYPE_RETAIL = "RETAIL"            # Küçük yatırımcının yoğun olduğu kurumlar (Örn: Ziraat, Garanti, Yapı Kredi)
TYPE_NEUTRAL = "NEUTRAL"          # Belirgin bir karakteri olmayan genel kurumlar

# Kurum İsimlerinden Kurum Tipine Eşleştirme (Büyük-Küçük Harf Duyarsız Aramak İçin)
# Anahtar kelimelerle eşleşme yapılacak.
INSTITUTION_PROFILES: Dict[str, Tuple[str, float]] = {
    "BANK OF AMERICA": (TYPE_DAILY, 0.5),      # BofA alımları skoru yarıya düşürür (Yarın satma ihtimali yüksek)
    "BOFA": (TYPE_DAILY, 0.5),
    "YATIRIM FINANSMAN": (TYPE_DAILY, 0.7),
    
    "INFO": (TYPE_SPECULATIVE, 1.3),           # Operasyon kurumu, alıyorsa bir bildiği vardır, skoru %30 artır
    "MARBAS": (TYPE_SPECULATIVE, 1.3),
    "A1 CAPITAL": (TYPE_SPECULATIVE, 1.2),
    "MEKSA": (TYPE_SPECULATIVE, 1.2),
    
    "IS YATIRIM": (TYPE_LONG_TERM, 1.2),       # Kurumsal alımlar skoru artırır
    "YAPI KREDI": (TYPE_RETAIL, 0.9),          # KY yoğun, skor hafif düşer
    "ZIRAAT": (TYPE_RETAIL, 0.8),
    "GARANTI": (TYPE_RETAIL, 0.9),
    "VAKIF": (TYPE_RETAIL, 0.9),
    "HALK": (TYPE_RETAIL, 0.9),
    "OYAK": (TYPE_LONG_TERM, 1.1),
    "GEDIK": (TYPE_NEUTRAL, 1.0),
    "TEB": (TYPE_LONG_TERM, 1.1),
    "CITIBANK": (TYPE_FOREIGN, 1.5),           # Yabancı alımı çok değerlidir
    "DEUTSCHE": (TYPE_FOREIGN, 1.5),
    "EMEK": (TYPE_LONG_TERM, 1.4),             # Emeklilik fonları vb. (İsim içinde geçerse)
    "YATIRIM FON": (TYPE_LONG_TERM, 1.4),      # Yatırım fonları
}

def get_institution_profile(kurum_adi: str) -> Tuple[str, float]:
    """
    Verilen kurum adının profilini ve skor çarpanını döndürür.
    
    Parameters:
        kurum_adi (str): AKD veya Takas tablosundan gelen kurum adı.
        
    Returns:
        tuple: (kurum_tipi, skor_carpani)
    """
    if not kurum_adi:
        return (TYPE_NEUTRAL, 1.0)
        
    kurum_upper = str(kurum_adi).upper()
    
    for key, (k_type, multiplier) in INSTITUTION_PROFILES.items():
        if key in kurum_upper:
            return (k_type, multiplier)
            
    # Eşleşme bulunamazsa nötr kabul et
    return (TYPE_NEUTRAL, 1.0)

def calculate_profile_adjusted_score(net_lot: float, kurum_adi: str) -> float:
    """
    Net lot miktarını kurumun karakter çarpanı ile çarparak
    Düzeltilmiş (Ağırlıklandırılmış) Lot etkisini hesaplar.
    
    BofA'nın 1 Milyon lotu = 500 Bin lot etkisi yaratır.
    Citibank'ın 1 Milyon lotu = 1.5 Milyon lot etkisi yaratır.
    """
    _, multiplier = get_institution_profile(kurum_adi)
    return net_lot * multiplier

def get_institution_category_name(kurum_adi: str) -> str:
    """Arayüzde göstermek için Türkçe kurum profili ismi döndürür."""
    k_type, _ = get_institution_profile(kurum_adi)
    mapping = {
        TYPE_DAILY: "Günlükçü/Algo",
        TYPE_SPECULATIVE: "Spekülatif/Tahtacı",
        TYPE_LONG_TERM: "Kurumsal/Uzun Vade",
        TYPE_FOREIGN: "Yabancı Takası",
        TYPE_RETAIL: "Bireysel (KY) Yoğun",
        TYPE_NEUTRAL: "Nötr"
    }
    return mapping.get(k_type, "Nötr")
