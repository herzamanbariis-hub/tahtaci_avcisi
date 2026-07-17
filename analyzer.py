# -*- coding: utf-8 -*-
"""
Tahtacı Avcısı v1.0 — Analiz Motoru
======================================
Veritabanındaki son 30 günlük veriyi okuyarak T+2 kalıntı analizini,
kurum kümeleme (hiyerarşik agglomerative clustering) işlemini ve
0–100 arası **Tahtacı Skoru** hesaplamasını gerçekleştirir.

Matematiksel Temel
------------------
::

    Residual(j, t) = ΔTakas(j, t+2) − AKD(j, t)

Burada:
- ``j`` : Aracı kurum
- ``t`` : İşlem günü
- ``ΔTakas(j, t+2)`` : j kurumunun t+2 günündeki saklama adet değişimi
- ``AKD(j, t)`` : j kurumunun t günündeki net lot alımı

Yüksek pozitif kalıntı → Başka kurumdan gelen gizli virman (toplama)
Yüksek negatif kalıntı → Başka kuruma giden gizli virman (dağıtım ağı)

Kullanım
--------
>>> from analyzer import calculate_tahtaci_score
>>> result = calculate_tahtaci_score("EREGL")
>>> print(result["tahtaci_score"])
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

from config import (
    DB_PATH,
    T_PLUS_DAYS,
    RESIDUAL_LOOKBACK_DAYS,
    TAHTACI_SCORE_WEIGHTS,
    CLUSTER_DISTANCE_THRESHOLD,
    MIN_CLUSTER_SIZE,
    CONCENTRATION_THRESHOLD,
    DIGER_MA_WINDOW,
    DIGER_SLOPE_THRESHOLD,
)
from database import query_df

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# A. T+2 KALINTI ANALİZİ (RESIDUAL ANALYSIS)
# ═══════════════════════════════════════════════

def _get_akd_net(hisse: str, lookback_days: int = RESIDUAL_LOOKBACK_DAYS) -> pd.DataFrame:
    """
    Son N gün için AKD net lot verilerini çeker.

    Parameters
    ----------
    hisse : str
        Hisse sembolü.
    lookback_days : int
        Geriye bakış penceresi (gün).

    Returns
    -------
    pd.DataFrame
        Sütunlar: tarih, kurum_adi, net_lot
    """
    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    sql = """
        SELECT tarih, kurum_adi, net_lot
        FROM akd_data
        WHERE hisse = ? AND tarih >= ?
        ORDER BY tarih, kurum_adi
    """
    try:
        df = query_df(sql, params=(hisse, cutoff))
        logger.debug("AKD verisi çekildi: %s — %d satır", hisse, len(df))
        return df
    except Exception as e:
        logger.error("AKD çekme hatası [%s]: %s", hisse, e)
        return pd.DataFrame(columns=["tarih", "kurum_adi", "net_lot"])


def _get_takas_delta(hisse: str, lookback_days: int = RESIDUAL_LOOKBACK_DAYS) -> pd.DataFrame:
    """
    Son N gün için saklama adet değişimlerini (günlük delta) hesaplar.

    Her kurum-gün çifti için:
    ``ΔTakas(j, t) = saklama_adet(j, t) − saklama_adet(j, t−1)``

    Parameters
    ----------
    hisse : str
        Hisse sembolü.
    lookback_days : int
        Geriye bakış penceresi (gün).

    Returns
    -------
    pd.DataFrame
        Sütunlar: tarih, kurum_adi, delta_saklama
    """
    # Ek buffer: T+2 eşleşmesi için +5 gün daha geriye gidiyoruz
    cutoff = (datetime.now() - timedelta(days=lookback_days + 5)).strftime("%Y-%m-%d")

    sql = """
        SELECT tarih, kurum_adi, saklama_adet
        FROM takas_data
        WHERE hisse = ? AND tarih >= ?
        ORDER BY kurum_adi, tarih
    """
    try:
        df = query_df(sql, params=(hisse, cutoff))
        if df.empty:
            logger.warning("Takas verisi bulunamadı: %s", hisse)
            return pd.DataFrame(columns=["tarih", "kurum_adi", "delta_saklama"])

        # Kurum bazında günlük delta hesapla
        df = df.sort_values(["kurum_adi", "tarih"])
        df["delta_saklama"] = df.groupby("kurum_adi")["saklama_adet"].diff()
        df = df.dropna(subset=["delta_saklama"])
        df["delta_saklama"] = df["delta_saklama"].astype(int)

        logger.debug("Takas delta hesaplandı: %s — %d satır", hisse, len(df))
        return df[["tarih", "kurum_adi", "delta_saklama"]]

    except Exception as e:
        logger.error("Takas delta hatası [%s]: %s", hisse, e)
        return pd.DataFrame(columns=["tarih", "kurum_adi", "delta_saklama"])


def _build_business_day_map(dates: List[str]) -> Dict[str, str]:
    """
    Her iş günü için T+2 sonraki iş gününü eşleyen bir harita oluşturur.

    Parameters
    ----------
    dates : list of str
        Sıralı tarih listesi ('YYYY-MM-DD' formatında).

    Returns
    -------
    dict
        {t_tarihi: t+2_tarihi} eşlemesi.
    """
    sorted_dates = sorted(set(dates))
    day_map = {}
    for i, d in enumerate(sorted_dates):
        # Basit yaklaşım: listedeki i+T_PLUS_DAYS elemanına eşle
        target_idx = i + T_PLUS_DAYS
        if target_idx < len(sorted_dates):
            day_map[d] = sorted_dates[target_idx]
    return day_map


def compute_residuals(
    hisse: str,
    lookback_days: int = RESIDUAL_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """
    T+2 kalıntı (residual) hesaplaması yapar.

    Her kurum-gün çifti için:
    ``Residual(j, t) = ΔTakas(j, t+2) − AKD(j, t)``

    Parameters
    ----------
    hisse : str
        Hisse sembolü.
    lookback_days : int
        Geriye bakış penceresi (gün).

    Returns
    -------
    pd.DataFrame
        Sütunlar: tarih, kurum_adi, akd_net_lot, takas_delta, residual

    Notes
    -----
    Pozitif kalıntı: Kuruma AKD'de görünmeyen gizli lot girişi var (virman alıcısı).
    Negatif kalıntı: Kurumdan AKD'de görünmeyen gizli lot çıkışı var (virman göndericisi).
    """
    akd_df = _get_akd_net(hisse, lookback_days)
    takas_df = _get_takas_delta(hisse, lookback_days)

    if akd_df.empty or takas_df.empty:
        logger.warning(
            "Kalıntı hesaplaması için yeterli veri yok: %s (AKD: %d, Takas: %d)",
            hisse, len(akd_df), len(takas_df),
        )
        return pd.DataFrame(
            columns=["tarih", "kurum_adi", "akd_net_lot", "takas_delta", "residual"]
        )

    # T+2 tarih eşleme haritası oluştur
    all_dates = sorted(set(akd_df["tarih"].tolist() + takas_df["tarih"].tolist()))
    day_map = _build_business_day_map(all_dates)

    # AKD tarihlerini T+2'ye eşle
    akd_df = akd_df.copy()
    akd_df["tarih_t2"] = akd_df["tarih"].map(day_map)
    akd_df = akd_df.dropna(subset=["tarih_t2"])

    # AKD (t günü) ile Takas Delta (t+2 günü) birleştir
    merged = pd.merge(
        akd_df,
        takas_df,
        left_on=["tarih_t2", "kurum_adi"],
        right_on=["tarih", "kurum_adi"],
        how="inner",
        suffixes=("_akd", "_takas"),
    )

    if merged.empty:
        logger.warning("T+2 eşleşme bulunamadı: %s", hisse)
        return pd.DataFrame(
            columns=["tarih", "kurum_adi", "akd_net_lot", "takas_delta", "residual"]
        )

    # Kalıntı hesapla
    result = pd.DataFrame({
        "tarih": merged["tarih_akd"],
        "kurum_adi": merged["kurum_adi"],
        "akd_net_lot": merged["net_lot"],
        "takas_delta": merged["delta_saklama"],
        "residual": merged["delta_saklama"] - merged["net_lot"],
    })

    logger.info("Kalinti hesaplandi: %s -- %d eslesme, ort. kalinti: %.1f lot",
        hisse, len(result), result["residual"].mean(),
    )
    return result


# ═══════════════════════════════════════════════
# B. KURUM KÜMELEME & VİRMAN KORİDORU TESPİTİ
# ═══════════════════════════════════════════════

def build_residual_matrix(hisse: str) -> pd.DataFrame:
    """
    Kurum × Gün bazında kalıntı matrisi oluşturur.

    Satırlar: Kurumlar, Sütunlar: Günler, Değerler: Kalıntı (lot)

    Parameters
    ----------
    hisse : str
        Hisse sembolü.

    Returns
    -------
    pd.DataFrame
        Pivot tablo (kurum × tarih) — kalıntı değerleri.
    """
    residuals = compute_residuals(hisse)

    if residuals.empty:
        logger.info("Kalinti matrisi olusturulamadi: %s -- veri yok", hisse)
        return pd.DataFrame()

    # Pivot: Satır=kurum, Sütun=tarih, Değer=kalıntı
    matrix = residuals.pivot_table(
        index="kurum_adi",
        columns="tarih",
        values="residual",
        aggfunc="sum",
        fill_value=0,
    )

    logger.debug(
        "Kalinti matrisi olusturuldu: %s -- %d kurum x %d gun",
        hisse, matrix.shape[0], matrix.shape[1],
    )
    return matrix


def cluster_institutions(residual_matrix: pd.DataFrame) -> Dict[int, List[str]]:
    """
    Kalıntı korelasyonuna dayalı hiyerarşik kümeleme uygular.

    Kurumlar arası zaman serisi korelasyonu hesaplanır ve
    Agglomerative Clustering ile gruplandırılır.

    Parameters
    ----------
    residual_matrix : pd.DataFrame
        ``build_residual_matrix`` çıktısı (kurum × tarih).

    Returns
    -------
    dict
        {küme_id: [kurum_adı_listesi]} — Virman kümeleri.
    """
    if residual_matrix.empty or residual_matrix.shape[0] < 2:
        logger.warning("Kümeleme için yeterli kurum yok (%d)", residual_matrix.shape[0])
        return {}

    # Korelasyon matrisi hesapla
    corr_matrix = residual_matrix.T.corr()

    # Negatif korelasyon da virman göstergesi olabilir (A gönderir → B alır)
    # Bu yüzden |korelasyon|'u kullanıyoruz
    abs_corr = corr_matrix.abs()

    # Mesafe matrisi: 1 − |korelasyon| (düşük mesafe = yüksek ilişki)
    distance_matrix = 1.0 - abs_corr

    # Negatif/NaN mesafeleri düzelt
    distance_matrix = distance_matrix.clip(lower=0).fillna(1.0)

    # Explicit copy to avoid read-only array issues
    dist_values = distance_matrix.values.copy()
    np.fill_diagonal(dist_values, 0)

    try:
        # Condensed distance matrix (squareform)
        condensed_dist = squareform(dist_values, checks=False)

        # Hiyerarşik kümeleme (Ward yöntemi)
        linkage_matrix = linkage(condensed_dist, method="average")

        # Küme ataması
        labels = fcluster(linkage_matrix, t=CLUSTER_DISTANCE_THRESHOLD, criterion="distance")

        # Sonuçları dict'e dönüştür
        clusters: Dict[int, List[str]] = {}
        institutions = residual_matrix.index.tolist()
        for inst, label in zip(institutions, labels):
            cluster_id = int(label)
            if cluster_id not in clusters:
                clusters[cluster_id] = []
            clusters[cluster_id].append(inst)

        # Küçük kümeleri filtrele
        significant_clusters = {
            k: v for k, v in clusters.items() if len(v) >= MIN_CLUSTER_SIZE
        }

        logger.info(
            "Kumeleme tamamlandi: %d kume bulundu (%d anlamli, min_boyut=%d)",
            len(clusters), len(significant_clusters), MIN_CLUSTER_SIZE,
        )
        return significant_clusters

    except Exception as e:
        logger.error("Kümeleme hatası: %s", e)
        return {}


def detect_virman_corridors(
    clusters: Dict[int, List[str]],
    residual_matrix: pd.DataFrame,
    hisse: str = None
) -> pd.DataFrame:
    """
    Küme içi negatif-pozitif kalıntı eşleşmelerini tespit eder.

    Bir küme içinde bir kurum sürekli negatif kalıntı (lot çıkışı)
    üretirken diğeri pozitif kalıntı (lot girişi) üretiyorsa,
    aralarında bir virman koridoru olma olasılığı yüksektir.

    Parameters
    ----------
    clusters : dict
        ``cluster_institutions`` çıktısı.
    residual_matrix : pd.DataFrame
        Kurum × Gün kalıntı matrisi.

    Returns
    -------
    pd.DataFrame
        Sütunlar: kume_id, gonderici, alici, ort_transfer, korelasyon, olasilik
    """
    corridors = []

    latest_saklama = {}
    if hisse:
        try:
            from database import query_df
            sql = "SELECT kurum_adi, saklama_adet FROM takas_data WHERE hisse = ? AND tarih = (SELECT MAX(tarih) FROM takas_data WHERE hisse = ?)"
            df_sak = query_df(sql, params=(hisse, hisse))
            latest_saklama = dict(zip(df_sak['kurum_adi'], df_sak['saklama_adet']))
        except Exception as e:
            logger.warning(f"Vault data could not be fetched for {hisse}: {e}")
    for cluster_id, members in clusters.items():
        if len(members) < 2:
            continue

        # Küme içi her kurum çifti için analiz
        for i, sender in enumerate(members):
            for receiver in members[i + 1:]:
                if sender not in residual_matrix.index or receiver not in residual_matrix.index:
                    continue

                sender_series = residual_matrix.loc[sender]
                receiver_series = residual_matrix.loc[receiver]

                # Negatif korelasyon = biri gönderirken diğeri alıyor
                corr = sender_series.corr(receiver_series)

                sender_mean = sender_series.mean()
                receiver_mean = receiver_series.mean()

                # Virman koridoru: Biri net negatif, diğeri net pozitif
                if sender_mean * receiver_mean < 0:  # Zıt yönler
                    actual_sender = sender if sender_mean < 0 else receiver
                    actual_receiver = receiver if sender_mean < 0 else sender
                    avg_transfer = abs(min(sender_mean, receiver_mean))

                    # Olasılık: |korelasyon| × transfer büyüklüğü normalize
                    probability = min(100, abs(corr) * 100) if not np.isnan(corr) else 0

                    sender_total = latest_saklama.get(actual_sender, 0)
                    receiver_total = latest_saklama.get(actual_receiver, 0)

                    corridors.append({
                        "kume_id": cluster_id,
                        "gonderici": actual_sender,
                        "alici": actual_receiver,
                        "ort_transfer": round(avg_transfer, 1),
                        "korelasyon": round(corr, 3) if not np.isnan(corr) else 0.0,
                        "olasilik": round(probability, 1),
                        "gonderici_kasa": sender_total,
                        "alici_kasa": receiver_total
                    })

    result = pd.DataFrame(corridors)
    if not result.empty:
        result = result.sort_values("olasilik", ascending=False).reset_index(drop=True)
        logger.info("Virman koridorları tespit edildi: %d aday", len(result))
    else:
        logger.info("Virman koridoru tespit edilemedi")

    return result


# ═══════════════════════════════════════════════
# C. TAHTACI SKORU (0–100) BİLEŞENLERİ
# ═══════════════════════════════════════════════

def _residual_intensity_score(residuals: pd.DataFrame) -> float:
    """
    Kalıntı yoğunluğu alt skoru (0–100).

    Küme bazında açıklanamayan lot transferi büyüklüğünü ölçer.
    Yüksek mutlak kalıntı = Yüksek skor.

    Parameters
    ----------
    residuals : pd.DataFrame
        ``compute_residuals`` çıktısı.

    Returns
    -------
    float
        Alt skor (0–100).
    """
    if residuals.empty:
        return 0.0

    # Mutlak kalıntıların medyanı (aykırı değerlere dayanıklı)
    abs_median = residuals["residual"].abs().median()

    # Normalize: 0 lot → 0 puan, 5000+ lot → 100 puan (sigmoid)
    score = 100 * (1 - np.exp(-abs_median / 2000))
    return round(min(100, max(0, score)), 1)


def _correlation_strength_score(residual_matrix: pd.DataFrame) -> float:
    """
    Küme içi korelasyon gücü alt skoru (0–100).

    Kurumlar arası kalıntı zaman serisi korelasyonlarının gücünü ölçer.
    Yüksek |korelasyon| = Koordineli hareket = Yüksek skor.

    Parameters
    ----------
    residual_matrix : pd.DataFrame
        Kurum × Gün kalıntı matrisi.

    Returns
    -------
    float
        Alt skor (0–100).
    """
    if residual_matrix.empty or residual_matrix.shape[0] < 2:
        return 0.0

    corr = residual_matrix.T.corr()
    # Diagonal dışı |korelasyon| ortalaması
    mask = ~np.eye(corr.shape[0], dtype=bool)
    off_diag = corr.values[mask]
    avg_abs_corr = np.nanmean(np.abs(off_diag))

    # Normalize: 0 korelasyon → 0, 1.0 korelasyon → 100
    score = avg_abs_corr * 100
    return round(min(100, max(0, score)), 1)


def _concentration_ratio_score(hisse: str) -> float:
    """
    İlk 5 kurum yoğunlaşma alt skoru (0–100).

    Son günün AKD verilerinde ilk 5 kurumun toplam net lot
    içindeki payını ölçer. %70+ = Yüksek hakimiyet.

    Parameters
    ----------
    hisse : str
        Hisse sembolü.

    Returns
    -------
    float
        Alt skor (0–100).
    """
    sql = """
        SELECT kurum_adi, SUM(ABS(net_lot)) as total_lot
        FROM akd_data
        WHERE hisse = ? AND tarih = (
            SELECT MAX(tarih) FROM akd_data WHERE hisse = ?
        )
        GROUP BY kurum_adi
        ORDER BY total_lot DESC
    """
    try:
        df = query_df(sql, params=(hisse, hisse))
        if df.empty:
            return 0.0

        total = df["total_lot"].sum()
        if total == 0:
            return 0.0

        top5 = df.head(5)["total_lot"].sum()
        ratio = (top5 / total) * 100

        # Eşik üzeri bonus
        if ratio >= CONCENTRATION_THRESHOLD:
            score = 70 + (ratio - CONCENTRATION_THRESHOLD) * (30 / (100 - CONCENTRATION_THRESHOLD))
        else:
            score = (ratio / CONCENTRATION_THRESHOLD) * 70

        return round(min(100, max(0, score)), 1)

    except Exception as e:
        logger.error("Konsantrasyon hesaplama hatası [%s]: %s", hisse, e)
        return 0.0


def _diger_slope_score(hisse: str) -> float:
    """
    'Diğer' kolonu eğim alt skoru (0–100).

    Küçük yatırımcının 5 günlük hareketli ortalamasının (MA5) eğimini ölçer.
    Aşağı eğim (dökülme) = Yüksek skor.

    Parameters
    ----------
    hisse : str
        Hisse sembolü.

    Returns
    -------
    float
        Alt skor (0–100).
    """
    sql = """
        SELECT tarih, net_lot
        FROM akd_data
        WHERE hisse = ? AND kurum_adi = 'Diğer'
        ORDER BY tarih
    """
    try:
        df = query_df(sql, params=(hisse,))
        if df.empty or len(df) < DIGER_MA_WINDOW:
            return 0.0

        # MA(5) hesapla
        df["ma"] = df["net_lot"].rolling(window=DIGER_MA_WINDOW, min_periods=DIGER_MA_WINDOW).mean()
        df = df.dropna(subset=["ma"])

        if len(df) < 2:
            return 0.0

        # Haftalık eğim (lineer regresyon)
        x = np.arange(len(df)).astype(float)
        y = df["ma"].values.astype(float)

        # Basit lineer regresyon: slope = Σ(xi-x̄)(yi-ȳ) / Σ(xi-x̄)²
        x_mean = x.mean()
        y_mean = y.mean()
        numerator = ((x - x_mean) * (y - y_mean)).sum()
        denominator = ((x - x_mean) ** 2).sum()

        if denominator == 0:
            return 0.0

        slope = numerator / denominator

        # Haftalık eğim oranına dönüştür (5 işgünü = 1 hafta)
        if y_mean != 0:
            weekly_slope_pct = (slope * 5 / abs(y_mean)) * 100
        else:
            weekly_slope_pct = 0.0

        # Negatif eğim → yüksek skor (dökülme)
        if weekly_slope_pct >= 0:
            return 0.0  # Yükselen "Diğer" → tahtacı senaryosuna uymaz

        # Eşik kontrolü: -%1.5 ve altı isteniyor
        if weekly_slope_pct <= DIGER_SLOPE_THRESHOLD:
            # Tam puan: -%1.5'tan aşağıda
            intensity = min(abs(weekly_slope_pct) / abs(DIGER_SLOPE_THRESHOLD * 3), 1.0)
            score = 60 + intensity * 40
        else:
            # Kısmi puan: 0 ile -%1.5 arasında
            score = (abs(weekly_slope_pct) / abs(DIGER_SLOPE_THRESHOLD)) * 60

        return round(min(100, max(0, score)), 1)

    except Exception as e:
        logger.error("Diğer eğim hesaplama hatası [%s]: %s", hisse, e)
        return 0.0


def _continuity_score(residuals: pd.DataFrame) -> float:
    """
    Ardışık yön sürekliliği alt skoru (0–100).

    Kalıntının kaç ardışık gün aynı yönde olduğunu ölçer.
    Uzun süreklilik = Sistematik transferler = Yüksek skor.

    Parameters
    ----------
    residuals : pd.DataFrame
        ``compute_residuals`` çıktısı.

    Returns
    -------
    float
        Alt skor (0–100).
    """
    if residuals.empty:
        return 0.0

    # Gün bazında toplam kalıntı
    daily = residuals.groupby("tarih")["residual"].sum().sort_index()

    if len(daily) < 2:
        return 0.0

    # İşaret değişimlerini say
    signs = np.sign(daily.values)
    sign_changes = np.sum(np.abs(np.diff(signs)) > 0)

    # Maksimum ardışık aynı yön
    max_streak = 1
    current_streak = 1
    for i in range(1, len(signs)):
        if signs[i] == signs[i - 1] and signs[i] != 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 1

    # Normalize: 1 gün → 0, 15+ gün → 100
    score = min(100, (max_streak / 15) * 100)
    return round(max(0, score), 1)


# ═══════════════════════════════════════════════
# ANA SKOR HESAPLAYICI
# ═══════════════════════════════════════════════

def calculate_tahtaci_score(hisse: str) -> Dict[str, Any]:
    """
    Tüm bileşenleri birleştirerek 0–100 arası Tahtacı Skoru üretir.

    Bileşenler ve ağırlıklar:
    - Kalıntı Yoğunluğu:   %30
    - Korelasyon Gücü:      %25
    - Konsantrasyon Oranı:  %20
    - "Diğer" Eğimi:        %15
    - Süreklilik:           %10

    Parameters
    ----------
    hisse : str
        Hisse sembolü.

    Returns
    -------
    dict
        Aşağıdaki anahtarları içerir:
        - ``hisse`` : str — Hisse sembolü
        - ``tahtaci_score`` : float — Nihai skor (0–100)
        - ``sub_scores`` : dict — Alt skor detayları
        - ``clusters`` : dict — Kurum kümeleri
        - ``corridors`` : pd.DataFrame — Virman koridorları
        - ``residuals`` : pd.DataFrame — Ham kalıntı verileri
        - ``verdict`` : str — Yorumlayıcı metin

    Raises
    ------
    Exception
        Kritik hesaplama hatası.
    """
    logger.info("=" * 60)
    logger.info("TAHTACI SKORU HESAPLANIYOR: %s", hisse)
    logger.info("=" * 60)

    try:
        # 1. Kalıntı hesapla
        residuals = compute_residuals(hisse)

        # 2. Kalıntı matrisi oluştur
        residual_matrix = build_residual_matrix(hisse)

        # 3. Kurum kümeleri
        clusters = cluster_institutions(residual_matrix)

        # 4. Virman koridorları
        corridors = detect_virman_corridors(clusters, residual_matrix, hisse)

        # 5. Alt skorları hesapla
        sub_scores = {
            "residual_intensity": _residual_intensity_score(residuals),
            "correlation_strength": _correlation_strength_score(residual_matrix),
            "concentration_ratio": _concentration_ratio_score(hisse),
            "diger_slope": _diger_slope_score(hisse),
            "continuity": _continuity_score(residuals),
        }

        # 6. Ağırlıklı toplam skor
        # Eger kalinti (Takas) verisi yetersizse, sadece AKD uzerinden (Konsantrasyon ve Diger Egimi) skor uret
        if residuals.empty:
            weights = {
                "residual_intensity": 0.0,
                "correlation_strength": 0.0,
                "concentration_ratio": 0.70,  # Sadece gunluk alan satan yogunlugu
                "diger_slope": 0.30,          # Sadece kucuk yatirimci cikisi
                "continuity": 0.0,
            }
        else:
            weights = TAHTACI_SCORE_WEIGHTS
            
        tahtaci_score = sum(
            sub_scores[key] * weights[key] for key in weights
        )
        
        # 6.2 Kurum Profilleme Carpanini Uygula
        top_buyer_multiplier = 1.0
        top_buyer_name = "Bilinmiyor"
        top_buyer_type = "Nötr"
        
        try:
            sql_buyer = """
                SELECT kurum_adi, net_lot 
                FROM akd_data 
                WHERE hisse = ? 
                ORDER BY tarih DESC, net_lot DESC LIMIT 1
            """
            top_b_df = query_df(sql_buyer, params=(hisse,))
            if not top_b_df.empty:
                top_buyer_name = top_b_df.iloc[0]["kurum_adi"]
                from institution_profiler import get_institution_profile, get_institution_category_name
                _, top_buyer_multiplier = get_institution_profile(top_buyer_name)
                top_buyer_type = get_institution_category_name(top_buyer_name)
        except Exception as e:
            logger.warning("Kurum profili alinirken hata [%s]: %s", hisse, e)

        tahtaci_score = tahtaci_score * top_buyer_multiplier
        tahtaci_score = round(min(100, max(0, tahtaci_score)), 1)
        
        # 6.5. Trend Filtresi (Düşen Bıçak Koruması)
        is_downtrend = False
        is_overextended = False
        runup_pct = 0.0
        try:
            ticker = f"{hisse}.IS"
            stock = yf.Ticker(ticker)
            df_hist = stock.history(period="6mo")
            if not df_hist.empty:
                max_high = df_hist['High'].max()
                min_low = df_hist['Low'].min()
                last_close = df_hist['Close'].iloc[-1]
                
                # Dusen bicak kontrolu
                if max_high > 0 and ((max_high - last_close) / max_high) > 0.30:
                    is_downtrend = True
                    
                # Ralli / Sismis hisse kontrolu (Dipten %70'ten fazla primliyse)
                if min_low > 0:
                    runup_pct = ((last_close - min_low) / min_low) * 100
                    if runup_pct > 70.0 and not is_downtrend:
                        is_overextended = True
                        
        except Exception as e:
            logger.warning("Trend filtresi icin yfinance hatasi [%s]: %s", hisse, e)

        # 7. Yorumlayıcı metin
        if residuals.empty and tahtaci_score >= 40:
            verdict = "[!] AKD ODAKLI -- Sadece gunluk alan/satan uzerinden anomali tespit edildi (Takas verisi bekleniyor)."
        elif tahtaci_score >= 80:
            verdict = "[!!!] YUKSEK -- Guclu tahtaci aktivitesi tespit edildi!"
        elif tahtaci_score >= 60:
            verdict = "[!!] ORTA-YUKSEK -- Anlamli kurumsal toplama sinyalleri mevcut."
        elif tahtaci_score >= 40:
            verdict = "[!] ORTA -- Bazi sinyaller var ancak teyit gerekiyor."
        elif tahtaci_score >= 20:
            verdict = "[~] DUSUK -- Zayif sinyaller, izlemeye devam."
        else:
            verdict = "[-] COK DUSUK -- Anlamli tahtaci aktivitesi tespit edilemedi."

        # 8. Sonuç raporla
        logger.info("-" * 50)
        logger.info("TAHTACI SKORU: %s -> %.1f / 100", hisse, tahtaci_score)
        logger.info("  %-25s : %s (Carpan: %.1f)", "TOP BUYER (" + top_buyer_name + ")", top_buyer_type, top_buyer_multiplier)
        logger.info("  %-25s : %s", "KARAR", verdict)
        logger.info("  Kumeler: %d | Koridorlar: %d", len(clusters), len(corridors))
        logger.info("-" * 50)

        return {
            "hisse": hisse,
            "tahtaci_score": tahtaci_score,
            "sub_scores": sub_scores,
            "clusters": clusters,
            "corridors": corridors,
            "residuals": residuals,
            "verdict": verdict,
            "is_downtrend": is_downtrend,
            "is_overextended": is_overextended,
            "runup_pct": runup_pct,
            "top_buyer_name": top_buyer_name,
            "top_buyer_type": top_buyer_type,
            "top_buyer_multiplier": top_buyer_multiplier
        }

    except Exception as e:
        logger.error("Tahtacı skoru hesaplama hatası [%s]: %s", hisse, e)
        raise

def check_smc_sniper_entry(hisse: str, sweep_date: str, db_path: str = DB_PATH) -> bool:
    """
    SMC Sniper (Keskin Nisanci) Modeli.
    Fiyat destek altina sarkip temizlik yaptigi (Likidite Avlama) gunde:
    1. Ilk 5 Alici toplam net alimin %70'inden fazlasini mi yapti?
    2. Satislar daginik veya 'Diger' net satici mi oldu?
    
    Bu sartlar saglaniyorsa, gercek bir SMC Sniper Setup'i tescillenir.
    """
    if not sweep_date:
        return False
        
    try:
        sql = """
            SELECT kurum_adi, net_lot
            FROM akd_data
            WHERE hisse = ? AND tarih = ?
        """
        akd = query_df(sql, params=(hisse, sweep_date), db_path=db_path)
        
        if akd.empty:
            return False
            
        buyers = akd[akd["net_lot"] > 0].copy()
        if buyers.empty:
            return False
            
        buyers = buyers.sort_values(by="net_lot", ascending=False)
        total_buy_volume = buyers["net_lot"].sum()
        top5_buyers_volume = buyers.head(5)["net_lot"].sum()
        top5_ratio = top5_buyers_volume / total_buy_volume if total_buy_volume > 0 else 0
        
        sellers = akd[akd["net_lot"] < 0].copy()
        sellers["net_lot"] = sellers["net_lot"].abs()
        total_sell_volume = sellers["net_lot"].sum()
        
        if top5_ratio >= 0.70:
            diger_row = akd[akd["kurum_adi"].str.contains("Diğer|DİĞER|Diger", case=False, na=False)]
            if not diger_row.empty:
                diger_net = diger_row["net_lot"].sum()
                if diger_net < 0:
                    logger.info(f"SMC SNIPER TESPIT: {hisse} - Diger satti, Tahtaci %{top5_ratio*100:.0f} topladi.")
                    return True
            else:
                sellers = sellers.sort_values(by="net_lot", ascending=False)
                top5_sellers_volume = sellers.head(5)["net_lot"].sum()
                top5_sell_ratio = top5_sellers_volume / total_sell_volume if total_sell_volume > 0 else 0
                
                if top5_sell_ratio < 0.60:
                    logger.info(f"SMC SNIPER TESPIT: {hisse} - Satislar daginik, Tahtaci %{top5_ratio*100:.0f} topladi.")
                    return True

        return False
        
    except Exception as e:
        logger.error("SMC Sniper hatasi [%s]: %s", hisse, e)
        return False
