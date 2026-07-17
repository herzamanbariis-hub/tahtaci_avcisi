# -*- coding: utf-8 -*-
"""
Tahtacı Avcısı v1.0 — Konfigürasyon Modülü
=============================================
Tüm modüller tarafından paylaşılan sabitler, eşik değerleri
ve yapılandırma parametreleri bu dosyada tanımlanır.
"""

import os

# ─────────────────────────────────────────────
# VERİ TABANI
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tahtaci_avcisi.db")

# ─────────────────────────────────────────────
# LİKİDİTE KİLİDİ (HARD FILTER)
# Sadece halka açıklık oranı bu bant içindeki
# orta ölçekli (Mid-Cap) hisseler taranır.
# ─────────────────────────────────────────────
HALKA_ACIKLIK_MIN = 25.0   # %25
HALKA_ACIKLIK_MAX = 45.0   # %45

# ─────────────────────────────────────────────
# MALA HAKİMİYET FİLTRESİ
# ─────────────────────────────────────────────
CONCENTRATION_THRESHOLD = 70.0   # İlk 5 kurum oranı >= %70
DIGER_MA_WINDOW = 5              # "Diğer" kolonu MA penceresi (gün)
DIGER_SLOPE_THRESHOLD = -1.5     # Haftalık minimum eğim (%)

# ─────────────────────────────────────────────
# T+2 ANALİZ PARAMETRELERİ
# ─────────────────────────────────────────────
T_PLUS_DAYS = 2                  # Takas gecikme süresi (iş günü)
RESIDUAL_LOOKBACK_DAYS = 30      # Analiz penceresi (gün)

# ─────────────────────────────────────────────
# TAHTACI SKORU BİLEŞEN AĞIRLIKLARI
# Toplam = 1.0
# ─────────────────────────────────────────────
TAHTACI_SCORE_WEIGHTS = {
    "residual_intensity":    0.30,  # Kalıntı yoğunluğu
    "correlation_strength":  0.25,  # Küme içi korelasyon gücü
    "concentration_ratio":   0.20,  # İlk 5 kurum yoğunlaşması
    "diger_slope":           0.15,  # Küçük yatırımcı dökülme hızı
    "continuity":            0.10,  # Ardışık yön sürekliliği
}

# ─────────────────────────────────────────────
# KÜMELEME PARAMETRELERİ
# ─────────────────────────────────────────────
CLUSTER_DISTANCE_THRESHOLD = 0.5  # Hiyerarşik kümeleme mesafe eşiği
MIN_CLUSTER_SIZE = 2              # Minimum küme boyutu

# ─────────────────────────────────────────────
# ENDEKS KİLİDİ PARAMETRELERİ
# ─────────────────────────────────────────────
INDEX_TICKER = "XU100"            # BIST100 endeks sembolü
SMA200_PERIOD = 200
SMA50_PERIOD = 50
SMA20_PERIOD = 20

# ─────────────────────────────────────────────
# PİRAMİT ALIM ORANLARI
# ─────────────────────────────────────────────
PYRAMID_TRANCHES = {
    "entry_1": 0.30,   # İlk giriş: POC üstü onay
    "entry_2": 0.40,   # İkinci giriş: Direnç kırılımı + retest
    "entry_3": 0.30,   # Üçüncü giriş: Higher High geçişi
}

# ─────────────────────────────────────────────
# TUZ AK SAVAR PARAMETRELERİ
# ─────────────────────────────────────────────
VOLUME_BREAKOUT_MULTIPLIER = 1.5  # POC kırılımı için hacim çarpanı
VOLUME_MA_PERIOD = 20             # Hacim ortalama penceresi (gün)
RETEST_CONFIRMATION_BARS = 2      # Kırılım üzeri minimum bar kapanışı

# ─────────────────────────────────────────────
# SINYAL MOTORU PARAMETRELERI
# ─────────────────────────────────────────────
EMA21_PERIOD = 21                 # Dagitim / Cikis sinyali icin EMA periyodu

# ─────────────────────────────────────────────
# TELEGRAM SCRAPER AYARLARI
# ─────────────────────────────────────────────
TELEGRAM_BASE_URL = os.getenv("TELEGRAM_BASE_URL", "https://hisseyorumbot.example.com/api")
TELEGRAM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json",
    "X-Requested-With": "org.telegram.messenger",
}

_auth_token = os.getenv("TELEGRAM_BOT_TOKEN")
if _auth_token:
    TELEGRAM_HEADERS["Authorization"] = f"Bearer {_auth_token}"
REQUEST_TIMEOUT = 30              # Saniye
REQUEST_RETRY_COUNT = 3           # Başarısız isteklerde tekrar sayısı
REQUEST_RETRY_BACKOFF = 1.0       # Exponential backoff başlangıcı (sn)
REQUEST_DELAY = 1.5               # İstekler arası bekleme süresi (sn)

# ─────────────────────────────────────────────
# LOGLAMA
# ─────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(name)-18s | %(levelname)-7s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
