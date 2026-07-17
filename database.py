# -*- coding: utf-8 -*-
"""
Tahtacı Avcısı v1.0 — Veritabanı Modülü
==========================================
SQLite veritabanını başlatır, şemayı oluşturur ve Pandas DataFrame'lerini
``INSERT OR IGNORE`` mantığıyla tablolara işler.

Kullanım
--------
>>> from database import init_db, insert_akd_data
>>> init_db()                       # Tabloları oluştur
>>> insert_akd_data(akd_dataframe)  # Veri ekle
"""

import logging
import sqlite3
from contextlib import contextmanager
from typing import Optional, List, Any

import pandas as pd

from config import DB_PATH

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# BAĞLANTI YÖNETİMİ
# ─────────────────────────────────────────────

@contextmanager
def get_connection(db_path: str = DB_PATH):
    """
    Thread-safe SQLite bağlantısı sağlayan context manager.

    WAL modu etkinleştirilerek eşzamanlı okuma performansı artırılır.
    Bağlantı, blok sonunda otomatik olarak kapatılır.

    Parameters
    ----------
    db_path : str
        SQLite veritabanı dosya yolu.

    Yields
    ------
    sqlite3.Connection
        Aktif veritabanı bağlantısı.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        logger.error("Veritabanı bağlantı hatası: %s", e)
        raise
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────
# ŞEMA OLUŞTURMA
# ─────────────────────────────────────────────

_SQL_CREATE_AKD = """
CREATE TABLE IF NOT EXISTS akd_data (
    hisse       TEXT    NOT NULL,
    tarih       TEXT    NOT NULL,
    kurum_adi   TEXT    NOT NULL,
    net_lot     INTEGER NOT NULL DEFAULT 0,
    tutar       REAL    NOT NULL DEFAULT 0.0,
    avg_price   REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (hisse, tarih, kurum_adi)
);
"""

_SQL_CREATE_TAKAS = """
CREATE TABLE IF NOT EXISTS takas_data (
    hisse         TEXT    NOT NULL,
    tarih         TEXT    NOT NULL,
    kurum_adi     TEXT    NOT NULL,
    saklama_orani REAL    NOT NULL DEFAULT 0.0,
    saklama_adet  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (hisse, tarih, kurum_adi)
);
"""

_SQL_CREATE_PRICE = """
CREATE TABLE IF NOT EXISTS price_data (
    hisse   TEXT    NOT NULL,
    tarih   TEXT    NOT NULL,
    open    REAL    NOT NULL DEFAULT 0.0,
    high    REAL    NOT NULL DEFAULT 0.0,
    low     REAL    NOT NULL DEFAULT 0.0,
    close   REAL    NOT NULL DEFAULT 0.0,
    volume  REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (hisse, tarih)
);
"""

_SQL_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_akd_hisse_tarih ON akd_data (hisse, tarih);",
    "CREATE INDEX IF NOT EXISTS idx_takas_hisse_tarih ON takas_data (hisse, tarih);",
    "CREATE INDEX IF NOT EXISTS idx_price_hisse_tarih ON price_data (hisse, tarih);",
]

_SQL_CREATE_PORTFOLIO = """
CREATE TABLE IF NOT EXISTS portfolio_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hisse TEXT NOT NULL,
    alis_tarihi TEXT NOT NULL,
    alis_fiyati REAL NOT NULL,
    lot_miktari INTEGER NOT NULL,
    hedef_fiyat REAL NOT NULL,
    aktif INTEGER NOT NULL DEFAULT 1
);
"""

def init_db(db_path: str = DB_PATH) -> None:
    """
    Veritabanını başlatır ve gerekli tabloları oluşturur.

    ``CREATE TABLE IF NOT EXISTS`` kullanıldığından mevcut tablolar
    korunur, yalnızca eksik tablolar oluşturulur.

    Parameters
    ----------
    db_path : str
        SQLite veritabanı dosya yolu.
    """
    with get_connection(db_path) as conn:
        try:
            conn.execute(_SQL_CREATE_AKD)
            conn.execute(_SQL_CREATE_TAKAS)
            conn.execute(_SQL_CREATE_PRICE)
            conn.execute(_SQL_CREATE_PORTFOLIO)
            for idx_sql in _SQL_CREATE_INDEXES:
                conn.execute(idx_sql)
            conn.commit()
            logger.info("Veritabanı tabloları kontrol edildi/oluşturuldu.")
        except sqlite3.Error as e:
            logger.error("Tablo oluşturulurken hata: %s", e)
            conn.rollback()
            raise


# ─────────────────────────────────────────────
# VERİ EKLEME FONKSİYONLARI
# ─────────────────────────────────────────────

def _validate_columns(df: pd.DataFrame, required_cols: List[str], table_name: str) -> None:
    """
    DataFrame'in gerekli sütunlara sahip olduğunu doğrular.

    Parameters
    ----------
    df : pd.DataFrame
        Kontrol edilecek DataFrame.
    required_cols : list of str
        Gerekli sütun isimleri.
    table_name : str
        Hata mesajında kullanılacak tablo adı.

    Raises
    ------
    ValueError
        Eksik sütun bulunursa.
    """
    missing = set(required_cols) - set(df.columns)
    if missing:
        raise ValueError(
            f"'{table_name}' tablosu için eksik sütunlar: {missing}. "
            f"Beklenen: {required_cols}"
        )


def insert_akd_data(df: pd.DataFrame, db_path: str = DB_PATH) -> int:
    """
    AKD (Aracı Kurum Dağılımı) verilerini veritabanına işler.

    Yinelenen kayıtlar ``INSERT OR IGNORE`` ile atlanır.

    Parameters
    ----------
    df : pd.DataFrame
        Aşağıdaki sütunları içermelidir:
        ``hisse``, ``tarih``, ``kurum_adi``, ``net_lot``, ``tutar``, ``avg_price``
    db_path : str
        SQLite veritabanı dosya yolu.

    Returns
    -------
    int
        Eklenen satır sayısı.

    Raises
    ------
    ValueError
        Eksik sütun bulunursa.
    sqlite3.Error
        Veritabanı yazma hatası.
    """
    required = ["hisse", "tarih", "kurum_adi", "net_lot", "tutar", "avg_price"]
    _validate_columns(df, required, "akd_data")

    sql = """
        INSERT OR REPLACE INTO akd_data
            (hisse, tarih, kurum_adi, net_lot, tutar, avg_price)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    rows_inserted = 0
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            for _, row in df[required].iterrows():
                cursor.execute(sql, tuple(row))
            conn.commit()
            rows_inserted = cursor.rowcount if cursor.rowcount > 0 else len(df)
            logger.info(
                "akd_data: %d satır işlendi (toplam DataFrame: %d)",
                rows_inserted, len(df)
            )
    except sqlite3.Error as e:
        logger.error("akd_data INSERT hatası: %s", e)
        raise

    return rows_inserted


def insert_takas_data(df: pd.DataFrame, db_path: str = DB_PATH) -> int:
    """
    Takas/saklama verilerini veritabanına işler.

    Yinelenen kayıtlar ``INSERT OR IGNORE`` ile atlanır.

    Parameters
    ----------
    df : pd.DataFrame
        Aşağıdaki sütunları içermelidir:
        ``hisse``, ``tarih``, ``kurum_adi``, ``saklama_orani``, ``saklama_adet``
    db_path : str
        SQLite veritabanı dosya yolu.

    Returns
    -------
    int
        Eklenen satır sayısı.

    Raises
    ------
    ValueError
        Eksik sütun bulunursa.
    sqlite3.Error
        Veritabanı yazma hatası.
    """
    required = ["hisse", "tarih", "kurum_adi", "saklama_orani", "saklama_adet"]
    _validate_columns(df, required, "takas_data")

    sql = """
        INSERT OR REPLACE INTO takas_data
            (hisse, tarih, kurum_adi, saklama_orani, saklama_adet)
        VALUES (?, ?, ?, ?, ?)
    """
    rows_inserted = 0
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            for _, row in df[required].iterrows():
                cursor.execute(sql, tuple(row))
            conn.commit()
            rows_inserted = cursor.rowcount if cursor.rowcount > 0 else len(df)
            logger.info(
                "takas_data: %d satır işlendi (toplam DataFrame: %d)",
                rows_inserted, len(df)
            )
    except sqlite3.Error as e:
        logger.error("takas_data INSERT hatası: %s", e)
        raise

    return rows_inserted


def insert_price_data(df: pd.DataFrame, db_path: str = DB_PATH) -> int:
    """
    Fiyat (OHLCV) verilerini veritabanına işler.

    Yinelenen kayıtlar ``INSERT OR IGNORE`` ile atlanır.

    Parameters
    ----------
    df : pd.DataFrame
        Aşağıdaki sütunları içermelidir:
        ``hisse``, ``tarih``, ``open``, ``high``, ``low``, ``close``, ``volume``
    db_path : str
        SQLite veritabanı dosya yolu.

    Returns
    -------
    int
        Eklenen satır sayısı.

    Raises
    ------
    ValueError
        Eksik sütun bulunursa.
    sqlite3.Error
        Veritabanı yazma hatası.
    """
    required = ["hisse", "tarih", "open", "high", "low", "close", "volume"]
    _validate_columns(df, required, "price_data")

    sql = """
        INSERT OR REPLACE INTO price_data
            (hisse, tarih, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    rows_inserted = 0
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            for _, row in df[required].iterrows():
                cursor.execute(sql, tuple(row))
            conn.commit()
            rows_inserted = cursor.rowcount if cursor.rowcount > 0 else len(df)
            logger.info(
                "price_data: %d satır işlendi (toplam DataFrame: %d)",
                rows_inserted, len(df)
            )
    except sqlite3.Error as e:
        logger.error("price_data INSERT hatası: %s", e)
        raise

    return rows_inserted


# ─────────────────────────────────────────────
# GENEL SORGULAYICI
# ─────────────────────────────────────────────

def query_df(
    sql: str,
    params: Optional[tuple] = None,
    db_path: str = DB_PATH
) -> pd.DataFrame:
    """
    Verilen SQL sorgusunu çalıştırıp sonucu Pandas DataFrame olarak döndürür.

    Parameters
    ----------
    sql : str
        Çalıştırılacak SQL sorgusu.
    params : tuple, optional
        Sorgu parametreleri (placeholder'lar için).
    db_path : str
        SQLite veritabanı dosya yolu.

    Returns
    -------
    pd.DataFrame
        Sorgu sonucu.

    Raises
    ------
    sqlite3.Error
        Sorgu çalıştırma hatası.
    """
    try:
        with get_connection(db_path) as conn:
            if params:
                result = pd.read_sql_query(sql, conn, params=params)
            else:
                result = pd.read_sql_query(sql, conn)
            logger.debug("Sorgu başarılı: %d satır döndü", len(result))
            return result
    except (sqlite3.Error, pd.errors.DatabaseError) as e:
        logger.error("Sorgu hatası: %s | SQL: %s", e, sql[:200])
        raise


def get_distinct_hisseler(db_path: str = DB_PATH) -> List[str]:
    """
    Veritabanında AKD kaydı bulunan benzersiz hisse sembollerini döndürür.

    Parameters
    ----------
    db_path : str
        SQLite veritabanı dosya yolu.

    Returns
    -------
    list of str
        Hisse sembollerinin listesi.
    """
    df = query_df("SELECT DISTINCT hisse FROM akd_data ORDER BY hisse", db_path=db_path)
    return df["hisse"].tolist()


def get_date_range(table: str, hisse: str, db_path: str = DB_PATH) -> tuple:
    """
    Belirtilen tablo ve hisse için veri tarih aralığını döndürür.

    Parameters
    ----------
    table : str
        Tablo adı ('akd_data', 'takas_data', 'price_data').
    hisse : str
        Hisse sembolü.
    db_path : str
        SQLite veritabanı dosya yolu.

    Returns
    -------
    tuple of (str, str)
        (min_tarih, max_tarih) — 'YYYY-MM-DD' formatında.
    """
    allowed_tables = {"akd_data", "takas_data", "price_data"}
    if table not in allowed_tables:
        raise ValueError(f"Geçersiz tablo adı: {table}. İzin verilenler: {allowed_tables}")

    df = query_df(
        f"SELECT MIN(tarih) as min_t, MAX(tarih) as max_t FROM {table} WHERE hisse = ?",
        params=(hisse,),
        db_path=db_path
    )
    if df.empty or df.iloc[0]["min_t"] is None:
        return (None, None)
    return (df.iloc[0]["min_t"], df.iloc[0]["max_t"])


# ─────────────────────────────────────────────
# BIST ÖZEL ÖZELLİKLER (FAZ 4)
# ─────────────────────────────────────────────

def get_foreign_accumulation(days: int = 7, db_path: str = DB_PATH) -> pd.DataFrame:
    """
    Citi ve Deutsche takasındaki lot artışını hesaplar.
    Son 'days' gün içerisindeki en düşük ve en yüksek saklama adedini kıyaslar.
    """
    query = f"""
    WITH ForeignTakas AS (
        SELECT hisse, tarih, kurum_adi, saklama_adet
        FROM takas_data
        WHERE (kurum_adi LIKE '%CITI%' OR kurum_adi LIKE '%DEUTSCHE%' OR kurum_adi LIKE '%BOFA%')
        AND tarih >= date((SELECT MAX(tarih) FROM takas_data), '-{days} days')
    ),
    MinMax AS (
        SELECT hisse, kurum_adi, 
               FIRST_VALUE(saklama_adet) OVER (PARTITION BY hisse, kurum_adi ORDER BY tarih ASC) as start_lot,
               FIRST_VALUE(saklama_adet) OVER (PARTITION BY hisse, kurum_adi ORDER BY tarih DESC) as end_lot
        FROM ForeignTakas
    )
    SELECT hisse, kurum_adi, 
           MAX(start_lot) as baslangic_lot, 
           MAX(end_lot) as bitis_lot, 
           (MAX(end_lot) - MAX(start_lot)) as lot_degisim
    FROM MinMax
    GROUP BY hisse, kurum_adi
    HAVING lot_degisim > 0
    ORDER BY lot_degisim DESC;
    """
    return query_df(query, db_path=db_path)

def get_sectoral_money_flow(db_path: str = DB_PATH) -> pd.DataFrame:
    """
    Sektörel bazda son günün toplam AKD net para girişini/çıkışını (net_lot * avg_price) hesaplar.
    Not: Şu an veritabanımızda 'sektor' kolonu bulunmuyor. Bu nedenle hisselerin ilk harfinden 
    veya harici bir eşleşmeden sözde-sektör gruplaması yapacağız (Demonstrasyon amaçlı).
    İleride 'companies' tablosu eklenirse JOIN yapılabilir.
    """
    # AKD tablosundaki tutar kolonu doğrudan kullanılabilir.
    query = """
    SELECT SUBSTR(hisse, 1, 1) as pseudo_sektor, SUM(tutar) as net_para_girisi
    FROM akd_data
    WHERE tarih = (SELECT MAX(tarih) FROM akd_data)
    GROUP BY pseudo_sektor
    ORDER BY net_para_girisi DESC;
    """
    return query_df(query, db_path=db_path)

def get_buyer_cost(hisse: str, kurum_adi: str, days: int = 10, db_path: str = DB_PATH) -> float:
    """
    Belirli bir hissede, belirli bir kurumun son 'days' gündeki ağırlıklı ortalama maliyetini hesaplar.
    """
    query = f"""
    SELECT SUM(net_lot * avg_price) / SUM(net_lot) as maliyet
    FROM akd_data
    WHERE hisse = ? AND kurum_adi = ? AND net_lot > 0
    AND tarih >= date((SELECT MAX(tarih) FROM akd_data WHERE hisse = ?), '-{days} days')
    """
    df = query_df(query, params=(hisse, kurum_adi, hisse), db_path=db_path)
    if not df.empty and pd.notna(df.iloc[0]['maliyet']):
        return float(df.iloc[0]['maliyet'])
    return 0.0
