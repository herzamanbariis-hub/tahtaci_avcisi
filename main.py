# -*- coding: utf-8 -*-
"""
Tahtaci Avcisi v1.0 -- Ana Giris Noktasi
==========================================
Tum modulleri (database, telegram_scraper, analyzer) bir araya getiren
orkestrtor. Mock veri ile uctan uca calisan demo pipeline sunar.

Kullanım
--------
::

    python main.py                          # Varsayılan demo hisseler
    python main.py --hisseler EREGL THYAO   # Belirli hisseler
    python main.py --days 60                # Son 60 gün

İş Akışı
---------
1. Veritabanı başlatılır (şema oluşturulur).
2. Scraper ile veri çekilir (Mock veya gerçek).
3. Veriler veritabanına yazılır.
4. Her hisse için Tahtacı Skoru hesaplanır.
5. Sonuçlar konsola raporlanır.
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any

import pandas as pd

from config import (
    DB_PATH,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    RESIDUAL_LOOKBACK_DAYS,
    INDEX_TICKER,
)
from database import init_db, insert_akd_data, insert_takas_data, insert_price_data
from telegram_scraper import TelegramMiniAppScraper, apply_liquidity_filter
from signal_engine import generate_signals
from signal_engine import generate_signals


# ─────────────────────────────────────────────
# LOGLAMA YAPILANDIRMASI
# ─────────────────────────────────────────────

def setup_logging(level: str = LOG_LEVEL) -> None:
    """
    Uygulama genelinde loglama yapılandırmasını başlatır.

    Parameters
    ----------
    level : str
        Log seviyesi ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
    """
    # Windows cp1254 encoding sorununu coz: UTF-8 zorla
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# VERİ YÜKLEME PİPELINE
# ─────────────────────────────────────────────

def load_data(
    scraper,
    hisseler: List[str],
    days: int = RESIDUAL_LOOKBACK_DAYS,
) -> Dict[str, int]:
    """
    Belirtilen scraper nesnesi ile veri çekip veritabanına yükler.

    Parameters
    ----------
    scraper : BaseScraper
        MockScraper veya TelegramMiniAppScraper örneği.
    hisseler : list of str
        Veri üretilecek hisse sembolleri.
    days : int
        Kaç günlük veri üretileceği.

    Returns
    -------
    dict
        {tablo_adı: eklenen_satır_sayısı} istatistikleri.
    """
    stats = {"akd_data": 0, "takas_data": 0, "price_data": 0}

    today = datetime.now()
    start_date = today - timedelta(days=days + 10)  # Ekstra buffer

    for hisse in hisseler:
        logger.info("Fiyat ve derinlik verisi yükleniyor: %s (%d gün)", hisse, days)

        # ── Fiyat verisi (toplu) ──
        try:
            price_df = scraper.fetch_price(
                hisse,
                start_date.strftime("%Y-%m-%d"),
                today.strftime("%Y-%m-%d"),
            )
            if not price_df.empty:
                insert_price_data(price_df)
                stats["price_data"] += len(price_df)
        except Exception as e:
            logger.error("Fiyat verisi yukleme hatasi [%s]: %s", hisse, e)
            
        # ── AKD ve Takas verisi (gunluk) ──
        try:
            for i in range(days):
                tarih_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                
                # AKD
                try:
                    akd_df = scraper.fetch_akd(hisse, tarih_str)
                    if not akd_df.empty:
                        insert_akd_data(akd_df)
                        stats["akd_data"] += len(akd_df)
                except Exception as e:
                    logger.debug("AKD çekilemedi [%s - %s]: %s", hisse, tarih_str, e)
                    
                # Takas
                try:
                    takas_df = scraper.fetch_takas(hisse, tarih_str)
                    if not takas_df.empty:
                        insert_takas_data(takas_df)
                        stats["takas_data"] += len(takas_df)
                except Exception as e:
                    logger.debug("Takas çekilemedi [%s - %s]: %s", hisse, tarih_str, e)
        except Exception as e:
            logger.error("AKD/Takas dongusu hatasi [%s]: %s", hisse, e)

    # Endeks fiyat verisini yukle
    try:
        logger.info("Endeks (%s) veri yukleniyor...", INDEX_TICKER)
        price_df = scraper.fetch_price(
            INDEX_TICKER,
            start_date.strftime("%Y-%m-%d"),
            today.strftime("%Y-%m-%d"),
        )
        if not price_df.empty:
            insert_price_data(price_df)
            stats["price_data"] += len(price_df)
    except Exception as e:
        logger.error("Endeks fiyat verisi yukleme hatasi: %s", e)

    return stats


# ─────────────────────────────────────────────
# SONUÇ RAPORU
# ─────────────────────────────────────────────

def print_report(results: List[Dict[str, Any]]) -> None:
    """
    Analiz sonuçlarını görsel bir tablo formatında konsola yazdırır.

    Parameters
    ----------
    results : list of dict
        ``run_analysis`` çıktısı.
    """
    print("\n")
    print("=" * 80)
    print("  TAHTACI AVCISI v1.0 -- SNAKE EYE -- BIST SINYAL ANALIZ RAPORU")
    print(f"  Rapor Tarihi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    if not results:
        print("  [!] Analiz edilecek hisse bulunamadi.")
        print("=" * 80)
        return

    # Skorlara gore sirala (yuksekten dusuge)
    sorted_results = sorted(
        results,
        key=lambda x: x.get("tahtaci_score", 0),
        reverse=True,
    )

    # -- Ozet Tablosu --
    print(f"\n  {'HISSE':<10} {'SKOR':>8} {'PIYASA':<12} {'KARAR'}")
    print("  " + "-" * 100)

    for r in sorted_results:
        if r.get("hisse") == "ENDEKS_KILIDI":
            print(f"  {'ENDEKS':<10} {'-':>8} {r.get('market_status', '?'):<12} {r.get('error', '?')}")
            continue
            
        hisse = r.get("hisse", "?")
        score = r.get("tahtaci_score", 0)
        status = r.get("market_status", "?")
        summary = r.get("summary", r.get("error", "Hata"))
        print(f"  {hisse:<10} {score:>7.1f} {status:<12} {summary}")

    print()

    # -- Detayli Raporlar --
    for r in sorted_results:
        if "error" in r:
            continue

        if r.get("hisse") == "ENDEKS_KILIDI":
            continue

        hisse = r["hisse"]
        score = r["tahtaci_score"]
        status = r.get("market_status", "?")
        tahtaci_details = r.get("tahtaci_details", {})
        sub = tahtaci_details.get("sub_scores", {})
        clusters = tahtaci_details.get("clusters", {})
        corridors = tahtaci_details.get("corridors", pd.DataFrame())
        trap = r.get("trap_analysis")

        print(f"  +---- {hisse} -- DETAYLI ANALIZ ----")
        print(f"  | Tahtaci Skoru : {score:.1f} / 100")
        print(f"  | Piyasa Durumu : {status}")
        
        if trap:
            print(f"  |")
            print(f"  | Tuzak Savar   : Skor: {trap.trap_score:.1f} | Squeeze: {trap.squeeze_active} | BearTrap: {trap.bear_trap_detected}")
            print(f"  |   POC Seviye  : {trap.poc_level:.2f} | Kirilim: {trap.poc_breakout} | Retest: {trap.retest_confirmed}")
        
        entries = r.get("entry_signals", [])
        exit_sig = r.get("exit_signal", False)
        print(f"  |")
        print(f"  | Sinyaller     :")
        if exit_sig:
            print(f"  |   [CIKIS]     : Dagitim sinyali aktif!")
        elif entries:
            for e in entries:
                print(f"  |   [ALIM]      : {e}")
        else:
            print(f"  |   [-]         : Sinyal yok, izlemede.")

        print(f"  |")
        print(f"  | Alt Skorlar:")
        print(f"  |   Kalinti Yogunlugu      : {sub.get('residual_intensity', 0):6.1f}")
        print(f"  |   Korelasyon Gucu         : {sub.get('correlation_strength', 0):6.1f}")
        print(f"  |   Konsantrasyon Orani     : {sub.get('concentration_ratio', 0):6.1f}")
        print(f"  |   'Diger' Egimi           : {sub.get('diger_slope', 0):6.1f}")
        print(f"  |   Sureklilik              : {sub.get('continuity', 0):6.1f}")
        print(f"  |")

        # Kumeler
        if clusters:
            print(f"  | Tespit Edilen Kumeler ({len(clusters)}):")
            for cid, members in clusters.items():
                safe_members = [m.replace('ı','i').replace('ş','s').replace('ğ','g').replace('ü','u').replace('ö','o').replace('ç','c').replace('İ','I').replace('Ş','S').replace('Ğ','G').replace('Ü','U').replace('Ö','O').replace('Ç','C') for m in members]
                print(f"  |   Kume {cid}: {', '.join(safe_members)}")
            print(f"  |")

        # Virman koridorlari
        if not corridors.empty:
            print(f"  | Virman Koridorlari ({len(corridors)}):")
            for _, row in corridors.head(5).iterrows():
                gonderici = row['gonderici'].replace('ı','i').replace('ş','s').replace('ğ','g').replace('ü','u').replace('ö','o').replace('ç','c').replace('İ','I').replace('Ş','S').replace('Ğ','G').replace('Ü','U').replace('Ö','O').replace('Ç','C')
                alici = row['alici'].replace('ı','i').replace('ş','s').replace('ğ','g').replace('ü','u').replace('ö','o').replace('ç','c').replace('İ','I').replace('Ş','S').replace('Ğ','G').replace('Ü','U').replace('Ö','O').replace('Ç','C')
                print(
                    f"  |   {gonderici} --({row['ort_transfer']:.0f} lot)--> "
                    f"{alici}  [olasilik: %{row['olasilik']:.0f}]"
                )
            print(f"  |")

        print(f"  +{'-' * 50}")
        print()

    print("=" * 80)
    print("  [!] Bu rapor yatirim tavsiyesi degildir. Nihai karar trader onayindadir.")
    print("=" * 80)
    print()


# ─────────────────────────────────────────────
# CLI ARGÜMAN PARSER
# ─────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """
    Komut satırı argümanlarını ayrıştırır.

    Returns
    -------
    argparse.Namespace
        Ayrıştırılmış argümanlar.
    """
    parser = argparse.ArgumentParser(
        prog="tahtaci_avcisi",
        description="🐍 Tahtacı Avcısı v1.0 — BIST Sinyal ve Analiz Asistanı (SNAKE EYE)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python main.py                              # Varsayılan demo hisseler
  python main.py --hisseler EREGL THYAO       # Belirli hisseler
  python main.py --days 60 --log-level DEBUG  # 60 gün, detaylı log
        """,
    )

    parser.add_argument(
        "--hisseler",
        nargs="+",
        default=["EREGL", "THYAO", "SISE"],
        help="Analiz edilecek hisse sembolleri (varsayılan: EREGL THYAO SISE)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=RESIDUAL_LOOKBACK_DAYS,
        help=f"Geriye bakış penceresi — gün (varsayılan: {RESIDUAL_LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=DB_PATH,
        help=f"SQLite veritabanı dosya yolu (varsayılan: {DB_PATH})",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=f"Log seviyesi (varsayılan: {LOG_LEVEL})",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Veri yükleme adımını atla (mevcut DB üzerinden analiz yap)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="mock",
        choices=["mock", "live"],
        help="Veri çekme modu: mock (sahte veri) veya live (gerçek API) (varsayılan: mock)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        help="Gerçek API modu için özel endpoint URL'si (varsayılan: config.TELEGRAM_BASE_URL)",
    )

    return parser.parse_args()


# ─────────────────────────────────────────────
# ANA ÇALIŞMA
# ─────────────────────────────────────────────

def main() -> None:
    """
    Ana çalıştırma fonksiyonu.

    İş akışı:
    1. Argümanları ayrıştır
    2. Loglamayı yapılandır
    3. Veritabanını başlat
    4. Veri yükle (mock veya skip)
    5. Analiz çalıştır
    6. Rapor yazdır
    """
    args = parse_args()

    # Loglama başlat
    setup_logging(args.log_level)

    logger.info("Tahtaci Avcisi v1.0 baslatiliyor...")
    logger.info("Hisseler: %s", args.hisseler)
    logger.info("Geriye bakis: %d gun", args.days)
    logger.info("DB yolu: %s", args.db_path)

    # 1. Veritabanini baslat
    logger.info("Veritabani baslatiliyor...")
    init_db(args.db_path)

    # 2. Veri yukleme
    if not args.skip_load:
        logger.info("Veri yukleniyor (Mod: %s)...", args.mode)
        
        scraper_kwargs = {}
        if args.api_url:
            scraper_kwargs["base_url"] = args.api_url
        scraper = TelegramMiniAppScraper(**scraper_kwargs)
            
        stats = load_data(scraper, args.hisseler, args.days)
        logger.info(
            "Veri yukleme tamamlandi - AKD: %d, Takas: %d, Fiyat: %d satir",
            stats["akd_data"], stats["takas_data"], stats["price_data"],
        )
    else:
        logger.info("Veri yukleme atlandi (--skip-load)")

    # 3. Analiz calistir (Sinyal Motoru)
    logger.info("Analiz baslatiliyor...")
    results = generate_signals(args.hisseler, args.db_path)

    # 4. Rapor yazdir
    print_report(results)

    logger.info("Tahtaci Avcisi tamamlandi.")


if __name__ == "__main__":
    main()
