# -*- coding: utf-8 -*-
"""
Tahtacı Avcısı — Finans Ajanı (Claude Destekli Tam Kapsamlı Analiz)
=====================================================================
Tüm mevcut verileri (AKD, Takas, Kümeler, Koridorlar, Tuzak Savar,
Fiyat/Hacim, Haber) tek bir Claude çağrısında birleştirerek
stratejik seviyede bir "Tahtacı Raporu" üretir.

Maliyet: Hisse başına ~$0.01-0.02 (tek API çağrısı)
"""

import os
import json
import time
import logging
from dotenv import load_dotenv
from anthropic import Anthropic

logger = logging.getLogger(__name__)
load_dotenv()

# Önbellek
_ajan_cache = {}
_ajan_call_count = 0
_ajan_tokens = 0
CACHE_TTL = 3600  # 1 saat


def get_ajan_stats() -> dict:
    return {
        "calls": _ajan_call_count,
        "tokens": _ajan_tokens,
        "cached": len(_ajan_cache),
        "cost": round(_ajan_tokens * 0.000003, 4),
    }


def generate_ajan_report(
    hisse: str,
    tahtaci_score: float,
    sub_scores: dict,
    clusters: dict,
    corridors_text: str,
    trap_summary: str,
    entry_signals: list,
    exit_signal: bool,
    last_close: float,
    top_buyer: str,
    top_buyer_type: str,
    news_headlines: str = "",
    akd_summary: str = "",
    takas_summary: str = "",
    social_summary: str = "",
) -> dict:
    """
    Tüm verileri Claude'a verip tek seferde kapsamlı rapor üretir.
    
    Returns:
        dict: {
            "rapor": str,           # Ana yorum metni
            "aksiyon": str,         # AL / SAT / BEKLE / UZAK DUR
            "guven": float,         # 0-100 arası güven skoru
            "risk_notu": str,       # Risk uyarısı
            "hedef_fiyat": str,     # Tahmini hedef
            "stop_loss": str,       # Önerilen zarar kes
            "mode": str             # "ajan" / "cached" / "error"
        }
    """
    global _ajan_call_count, _ajan_tokens

    # Önbellek
    if hisse in _ajan_cache:
        age = time.time() - _ajan_cache[hisse]["ts"]
        if age < CACHE_TTL:
            logger.info(f"Finans Ajanı önbellek: {hisse}")
            cached = _ajan_cache[hisse]["result"].copy()
            cached["mode"] = "cached"
            return cached

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "rapor": "⚠️ Claude API anahtarı bulunamadı. Finans Ajanı çalışamıyor.",
            "aksiyon": "BİLİNMİYOR",
            "guven": 0,
            "risk_notu": "API eksik",
            "hedef_fiyat": "-",
            "stop_loss": "-",
            "mode": "error"
        }

    # Veri paketini hazırla
    sinyal_text = "YOK"
    if exit_signal:
        sinyal_text = "ÇIKIŞ (DAĞITIM) SİNYALİ AKTİF"
    elif entry_signals:
        sinyal_text = ", ".join(entry_signals)

    cluster_text = "Küme verisi yok"
    if clusters:
        parts = []
        for cid, members in clusters.items():
            parts.append(f"Küme {cid}: {', '.join(members)}")
        cluster_text = " | ".join(parts)

    data_package = f"""
=== {hisse} — TAM VERİ PAKETİ ===

📊 TAHTACI SKORU: {tahtaci_score:.1f}/100
Son Kapanış Fiyatı: {last_close:.2f} TL

🏦 LİDER ALICI: {top_buyer} ({top_buyer_type})

📈 ALT SKORLAR:
- Kalıntı Yoğunluğu: {sub_scores.get('residual_intensity', 0):.1f}/100
- Korelasyon Gücü: {sub_scores.get('correlation_strength', 0):.1f}/100
- Konsantrasyon Oranı: {sub_scores.get('concentration_ratio', 0):.1f}/100
- Diğer Eğimi: {sub_scores.get('diger_slope', 0):.1f}/100
- Süreklilik: {sub_scores.get('continuity', 0):.1f}/100

🎯 SİNYALLER: {sinyal_text}

🪤 TUZAK ANALİZİ:
{trap_summary}

👥 KÜMELER (Birlikte Hareket Eden Kurumlar):
{cluster_text}

🔄 VİRMAN KORİDORLARI (Mal Transferleri):
{corridors_text if corridors_text else "Veri yok"}

📊 AKD ÖZETİ (Son Günler — Kim Alıyor / Kim Satıyor):
{akd_summary if akd_summary else "Veri yok"}

📦 TAKAS ÖZETİ (Kurumların Kasasındaki Mal):
{takas_summary if takas_summary else "Veri yok"}

📰 SON HABERLER:
{news_headlines if news_headlines else "Haber verisi yok"}

📱 SOSYAL MEDYA (TELEGRAM & X) RADARI:
{social_summary if social_summary else "Sosyal medya verisi yok"}
"""

    prompt = f"""Sen Borsa İstanbul'da (BİST) kurumsal para akışını okuyan ve "Tahtacı" (büyük fonlar, piyasa yapıcılar, kurumsal manipülatörler) operasyonlarını deşifre eden efsanevi bir piyasa ajanısın. Adın "SNAKE EYE Finans Ajanı".

Aşağıda '{hisse}' hissesi için toplanan TÜM veri paketi verilmiştir. Bu verileri bir bütün olarak oku ve aşağıdaki görevleri yerine getir:

1. DURUM TESPİTİ: Tahtacı şu an ne yapıyor? (Sessiz toplama, agresif toplama, dağıtım, tuzak kurma, bekleme?)
2. KÜME ANALİZİ: Birlikte hareket eden kurumlar ne anlatıyor? Virman koridorları bir koordineli hareket mi gösteriyor?
3. RİSK DEĞERLENDİRMESİ: Bu hisseye girmek ne kadar güvenli? Bear trap riski var mı? Düşen bıçak mı?
4. AKSİYON ÖNERİSİ: Net ve cesur bir karar ver. Yuvarlak laflar yapma. "AL", "SAT", "BEKLE" veya "UZAK DUR" de.
5. HİKAYE: Tüm bu verileri birleştirerek 3-5 cümlelik bir "Tahtacı Hikayesi" yaz. Sanki bir dedektif raporu gibi.

SADECE şu JSON formatında yanıt ver:
{{
    "rapor": "3-5 cümlelik detaylı Tahtacı hikayesi/analizi",
    "aksiyon": "AL" veya "SAT" veya "BEKLE" veya "UZAK DUR",
    "guven": 0 ile 100 arası güven skoru (integer),
    "risk_notu": "Kısa risk uyarısı (1 cümle)",
    "hedef_fiyat": "XX.XX TL (tahmini hedef) veya 'Belirsiz'",
    "stop_loss": "XX.XX TL (önerilen zarar kes) veya 'Belirsiz'"
}}

VERİ PAKETİ:
{data_package}
"""

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system="Sen SNAKE EYE Finans Ajanısın. Her zaman geçerli JSON döndür. Kod bloğu markdown kullanma. Doğrudan süslü parantez ile başla. Türkçe yaz.",
            messages=[{"role": "user", "content": prompt}]
        )

        _ajan_call_count += 1
        input_t = getattr(response.usage, 'input_tokens', 0)
        output_t = getattr(response.usage, 'output_tokens', 0)
        _ajan_tokens += input_t + output_t
        logger.info(f"Finans Ajanı token: in={input_t} out={output_t} toplam={_ajan_tokens}")

        # Yanıt parse
        result_text = ""
        for block in response.content:
            if getattr(block, "type", "") == "text" and hasattr(block, "text"):
                result_text += block.text
        result_text = result_text.strip()

        # Markdown temizle
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            result_text = "\n".join(lines).strip()

        result_json = json.loads(result_text)

        result = {
            "rapor": result_json.get("rapor", "Analiz tamamlandı."),
            "aksiyon": result_json.get("aksiyon", "BEKLE"),
            "guven": int(result_json.get("guven", 50)),
            "risk_notu": result_json.get("risk_notu", ""),
            "hedef_fiyat": str(result_json.get("hedef_fiyat", "Belirsiz")),
            "stop_loss": str(result_json.get("stop_loss", "Belirsiz")),
            "mode": "ajan"
        }

        _ajan_cache[hisse] = {"result": result, "ts": time.time()}
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Finans Ajanı JSON hatası [{hisse}]: {e}")
        # Ham metni rapor olarak kullan
        return {
            "rapor": result_text[:500] if result_text else "JSON parse hatası.",
            "aksiyon": "BEKLE",
            "guven": 0,
            "risk_notu": "Analiz JSON formatında dönemedi.",
            "hedef_fiyat": "Belirsiz",
            "stop_loss": "Belirsiz",
            "mode": "ajan_error"
        }
    except Exception as e:
        logger.error(f"Finans Ajanı hatası [{hisse}]: {e}")
        return {
            "rapor": f"Finans Ajanına bağlanırken hata: {str(e)}",
            "aksiyon": "BİLİNMİYOR",
            "guven": 0,
            "risk_notu": str(e),
            "hedef_fiyat": "Belirsiz",
            "stop_loss": "Belirsiz",
            "mode": "error"
        }
