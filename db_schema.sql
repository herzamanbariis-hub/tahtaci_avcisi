-- ============================================================
-- Tahtacı Avcısı v1.0 — Veritabanı Şeması (Referans)
-- ============================================================
-- Bu dosya dokümantasyon amaçlıdır.
-- Tabloları oluşturmak için database.py → init_db() kullanın.
-- ============================================================

-- AKD (Aracı Kurum Dağılımı) Verileri
-- Her hisse-tarih-kurum üçlüsü için net lot, tutar ve ortalama fiyat.
CREATE TABLE IF NOT EXISTS akd_data (
    hisse       TEXT    NOT NULL,
    tarih       TEXT    NOT NULL,   -- 'YYYY-MM-DD' formatı
    kurum_adi   TEXT    NOT NULL,
    net_lot     INTEGER NOT NULL DEFAULT 0,
    tutar       REAL    NOT NULL DEFAULT 0.0,
    avg_price   REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (hisse, tarih, kurum_adi)
);

-- Takas / Saklama Verileri (Takasbank)
-- Her hisse-tarih-kurum üçlüsü için saklama oranı ve adet.
CREATE TABLE IF NOT EXISTS takas_data (
    hisse         TEXT    NOT NULL,
    tarih         TEXT    NOT NULL,   -- 'YYYY-MM-DD' formatı
    kurum_adi     TEXT    NOT NULL,
    saklama_orani REAL    NOT NULL DEFAULT 0.0,
    saklama_adet  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (hisse, tarih, kurum_adi)
);

-- Fiyat Verileri (OHLCV)
-- Her hisse-tarih çifti için açılış, yüksek, düşük, kapanış ve hacim.
CREATE TABLE IF NOT EXISTS price_data (
    hisse   TEXT    NOT NULL,
    tarih   TEXT    NOT NULL,   -- 'YYYY-MM-DD' formatı
    open    REAL    NOT NULL DEFAULT 0.0,
    high    REAL    NOT NULL DEFAULT 0.0,
    low     REAL    NOT NULL DEFAULT 0.0,
    close   REAL    NOT NULL DEFAULT 0.0,
    volume  REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (hisse, tarih)
);

-- İndeksler: Sık kullanılan sorguları hızlandırmak için.
CREATE INDEX IF NOT EXISTS idx_akd_hisse_tarih
    ON akd_data (hisse, tarih);

CREATE INDEX IF NOT EXISTS idx_takas_hisse_tarih
    ON takas_data (hisse, tarih);

CREATE INDEX IF NOT EXISTS idx_price_hisse_tarih
    ON price_data (hisse, tarih);
