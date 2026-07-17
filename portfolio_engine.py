import sqlite3
import pandas as pd
from datetime import datetime
from database import get_connection, DB_PATH
import logging

logger = logging.getLogger(__name__)

def add_position(hisse: str, alis_fiyati: float, lot_miktari: int, hedef_fiyat: float, alis_tarihi: str = None) -> bool:
    if alis_tarihi is None:
        alis_tarihi = datetime.now().strftime("%Y-%m-%d")
        
    sql = """
        INSERT INTO portfolio_data (hisse, alis_tarihi, alis_fiyati, lot_miktari, hedef_fiyat, aktif)
        VALUES (?, ?, ?, ?, ?, 1)
    """
    try:
        with get_connection() as conn:
            conn.execute(sql, (hisse, alis_tarihi, alis_fiyati, lot_miktari, hedef_fiyat))
            conn.commit()
            logger.info("Pozisyon eklendi: %s, Maliyet: %.2f", hisse, alis_fiyati)
            return True
    except Exception as e:
        logger.error("Pozisyon eklenirken hata: %s", e)
        return False

def get_active_positions() -> pd.DataFrame:
    sql = "SELECT id, hisse, alis_tarihi, alis_fiyati, lot_miktari, hedef_fiyat FROM portfolio_data WHERE aktif = 1"
    try:
        with get_connection() as conn:
            df = pd.read_sql(sql, conn)
            return df
    except Exception as e:
        logger.error("Aktif pozisyonlar alinirken hata: %s", e)
        return pd.DataFrame()

def close_position(pos_id: int) -> bool:
    sql = "UPDATE portfolio_data SET aktif = 0 WHERE id = ?"
    try:
        with get_connection() as conn:
            conn.execute(sql, (pos_id,))
            conn.commit()
            return True
    except Exception as e:
        logger.error("Pozisyon kapatilirken hata: %s", e)
        return False

def calculate_inflation_adjusted_target(alis_fiyati: float, current_price: float, aylar: int, aylik_enflasyon: float = 3.0) -> dict:
    """
    Kullanicinin belirttigi strateji:
    - Hisse 2x veya x miktar gittiginde, "Ana Para + Enflasyon" kadarini satip iceride "Bedava Lot" birakmak.
    """
    # Ana paranin enflasyona ugramis su anki hakki
    toplam_enflasyon_carpani = (1 + (aylik_enflasyon / 100)) ** aylar
    istenen_ana_para = alis_fiyati * toplam_enflasyon_carpani
    
    # 2X Hedefi
    hedef_2x = alis_fiyati * 2.0
    
    # Eger hisse su anki fiyattaysa, ana paramizi cikarmak icin kac lot satmamiz lazim?
    satilmasi_gereken_oran = istenen_ana_para / current_price if current_price > 0 else 1.0
    
    return {
        "istenen_ana_para_hedefi": istenen_ana_para,
        "hedef_2x": hedef_2x,
        "satilmasi_gereken_oran": min(satilmasi_gereken_oran, 1.0)
    }
