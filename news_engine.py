# -*- coding: utf-8 -*-
"""
Haber, KAP ve Dedikodu Radarı (Sentiment Analizi) - YZ DESTEKLİ
================================================================
Claude API anahtarını verimli kullanır:
- Genel taramalarda (BIST 30/100/TÜM) → Claude API çağrılmaz, 
  sadece yfinance başlıkları gösterilir.
- Belirli hisse seçildiğinde → Claude ile derin Tahtacı analizi yapılır.
- Her analiz sonucu oturum boyunca önbelleğe alınır.
- Token ve maliyet takibi yapılır.
"""

import os
import json
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
import yfinance as yf
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Çevresel değişkenleri (API key) yükle
load_dotenv()

# ═══════════════════════════════════════════════
# OTURUM İÇİ ÖNBELLEK (Session Cache)
# ═══════════════════════════════════════════════
_cache = {}           # {hisse: {result, timestamp}}
_api_call_count = 0   # Bu oturumda kaç kez Claude çağrıldı
_total_tokens_used = 0  # Toplam kullanılan token

CACHE_TTL_SECONDS = 3600  # 1 saat


def get_api_stats() -> dict:
    """Bu oturumda Claude API kullanım istatistiklerini döndürür."""
    return {
        "api_calls": _api_call_count,
        "total_tokens": _total_tokens_used,
        "cached_items": len(_cache),
        "estimated_cost_usd": round(_total_tokens_used * 0.000003, 4),  # Yaklaşık maliyet
    }


def _is_cached(hisse: str) -> bool:
    """Önbellekte geçerli sonuç var mı kontrol et."""
    if hisse not in _cache:
        return False
    entry = _cache[hisse]
    age = time.time() - entry["timestamp"]
    return age < CACHE_TTL_SECONDS


# ═══════════════════════════════════════════════
# HAFİF MOD: Sadece Haber Başlıkları (Claude YOK)
# ═══════════════════════════════════════════════

def fetch_news_headlines_only(hisse: str) -> dict:
    """
    Claude API kullanmadan sadece yfinance başlıklarını çeker.
    Genel taramalarda (BIST 30/100/TÜM) bu fonksiyon kullanılır.
    Maliyet: 0 (sıfır API çağrısı).
    """
    if hisse == "ENDEKS_KILIDI":
        return {
            "sentiment": "NEUTRAL",
            "sentiment_score": 0.0,
            "news_count": 0,
            "highlight": "Endeks analizi için haber taranmıyor.",
            "mode": "skip"
        }

    try:
        ticker = yf.Ticker(f"{hisse}.IS")
        news_items = ticker.news

        if not news_items:
            return {
                "sentiment": "NEUTRAL",
                "sentiment_score": 0.0,
                "news_count": 0,
                "highlight": "Son dönemde belirgin haber akışı yok.",
                "mode": "light"
            }

        # Sadece başlıkları listele
        headlines = []
        for item in news_items[:5]:
            content = item.get("content", item)
            title = content.get("title", "")
            if title:
                headlines.append(title)

        highlight = " | ".join(headlines[:3]) if headlines else "Haber başlıkları okunamadı."

        # Basit keyword-based sentiment (Claude olmadan)
        positive_kw = ["yüksel", "artış", "kâr", "kar", "büyüme", "rekor", "temettü", "pozitif", "güçlü", "iyi"]
        negative_kw = ["düş", "zarar", "kayıp", "azal", "risk", "negatif", "kötü", "sorun", "ceza", "borç"]

        pos_count = sum(1 for h in headlines for kw in positive_kw if kw.lower() in h.lower())
        neg_count = sum(1 for h in headlines for kw in negative_kw if kw.lower() in h.lower())

        if pos_count > neg_count + 1:
            sentiment = "POSITIVE"
            score = min(0.6, pos_count * 0.15)
        elif neg_count > pos_count + 1:
            sentiment = "NEGATIVE"
            score = max(-0.6, neg_count * -0.15)
        else:
            sentiment = "NEUTRAL"
            score = 0.0

        return {
            "sentiment": sentiment,
            "sentiment_score": score,
            "news_count": len(headlines),
            "highlight": highlight,
            "mode": "light"
        }

    except Exception as e:
        logger.debug(f"Haber başlığı çekme hatası [{hisse}]: {e}")
        return {
            "sentiment": "NEUTRAL",
            "sentiment_score": 0.0,
            "news_count": 0,
            "highlight": "Haber akışına erişilemedi.",
            "mode": "light"
        }


# ═══════════════════════════════════════════════
# DERİN MOD: Claude ile Tahtacı Analizi
# ═══════════════════════════════════════════════

def fetch_news_sentiment(hisse: str, force_deep: bool = False) -> dict:
    """
    Claude API ile derin sentiment analizi yapar.
    
    Akıllı kullanım mantığı:
    - Önbellek varsa tekrar çağrılmaz.
    - force_deep=True ile zorlanabilir.
    
    Parameters:
        hisse (str): Hisse sembolü.
        force_deep (bool): Önbellek atlansın mı?
        
    Returns:
        dict: Sentiment analiz sonuçları.
    """
    global _api_call_count, _total_tokens_used

    # Bazı özel hisse kodları için pas geç
    if hisse == "ENDEKS_KILIDI":
        return {
            "sentiment": "NEUTRAL",
            "sentiment_score": 0.0,
            "news_count": 0,
            "highlight": "Endeks analizi için haber taranmıyor.",
            "mode": "skip"
        }

    # Önbellek kontrolü
    if not force_deep and _is_cached(hisse):
        logger.info(f"Önbellek kullanıldı: {hisse} (API tasarrufu!)")
        cached = _cache[hisse]["result"].copy()
        cached["mode"] = "cached"
        return cached

    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    # API key yoksa hafif moda düş
    if not api_key:
        logger.warning("Anthropic API key bulunamadı — hafif mod kullanılıyor.")
        return fetch_news_headlines_only(hisse)
        
    try:
        logger.info(f"🧠 Claude derin analiz başlatıldı: {hisse} (API çağrısı #{_api_call_count + 1})")
        
        # yfinance üzerinden gerçek haberleri çek
        ticker = yf.Ticker(f"{hisse}.IS")
        news_items = ticker.news
        
        if not news_items:
            result = {
                "sentiment": "NEUTRAL",
                "sentiment_score": 0.0,
                "news_count": 0,
                "highlight": "Son dönemde hisse ile ilgili belirgin bir haber akışı bulunamadı. Tahtacı sessiz ilerliyor olabilir.",
                "mode": "deep"
            }
            _cache[hisse] = {"result": result, "timestamp": time.time()}
            return result
            
        # Sadece başlıkları ve yayıncıları al
        headlines = []
        for item in news_items[:6]:
            content = item.get("content", item)
            title = content.get("title", "")
            publisher = content.get("provider", {}).get("displayName", "Bilinmeyen Kaynak")
            if not publisher or isinstance(publisher, dict):
                publisher = "Bilinmeyen Kaynak"
            if title:
                headlines.append(f"- {title} (Kaynak: {publisher})")
            
        news_text = "\n".join(headlines)
        
        if not news_text:
            result = {
                "sentiment": "NEUTRAL",
                "sentiment_score": 0.0,
                "news_count": 0,
                "highlight": "Haberler okunamadı veya içerik boş.",
                "mode": "deep"
            }
            _cache[hisse] = {"result": result, "timestamp": time.time()}
            return result

        # Claude için Prompt Hazırlığı
        prompt = f"""Sen Borsa İstanbul'da (BİST) işlem gören hisseler için haber analizi yapan ve 'Tahtacı' (Büyük fonlar/piyasa yapıcılar) davranışlarını okuyan kurnaz ve usta bir finansal yapay zeka asistanısın.
Görev: Aşağıda '{hisse}' hissesi için son çıkan haber başlıkları verilmiştir. Bu haberlerin, tahtacının mal toplama (accumulation) veya mal dağıtma/çakma (distribution) operasyonlarına nasıl bir hikaye zemini hazırladığını analiz et.

Sonucunu tam olarak şu formatta SADECE JSON olarak dönmelisin:
{{
    "sentiment": "POSITIVE" veya "NEGATIVE" veya "NEUTRAL",
    "sentiment_score": -1.0 ile 1.0 arasında bir ondalıklı sayı,
    "highlight": "Tahtacı perspektifinden yazılmış, en fazla 2-3 cümlelik doğrudan ve aksiyon odaklı özet bir yorum."
}}

Haberler:
{news_text}
"""

        # Anthropic API Çağrısı
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system="Sen profesyonel bir veri analistisin. Yanıtın her zaman geçerli ve saf bir JSON nesnesi olmalıdır. Kod bloğu markdown'u (```json ... ```) kullanma, doğrudan süslü parantez ile başla.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Token takibi
        _api_call_count += 1
        input_tokens = getattr(response.usage, 'input_tokens', 0)
        output_tokens = getattr(response.usage, 'output_tokens', 0)
        _total_tokens_used += input_tokens + output_tokens
        logger.info(f"Claude token kullanımı: input={input_tokens}, output={output_tokens}, toplam oturum={_total_tokens_used}")
        
        # Yanıtı çözümle (ThinkingBlock hatası düzeltildi)
        result_text = ""
        for block in response.content:
            if getattr(block, "type", "") == "text" and hasattr(block, "text"):
                result_text += block.text
        
        result_text = result_text.strip()
        
        # Olası markdown kalıntılarını temizle
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            result_text = "\n".join(lines).strip()
            
        result_json = json.loads(result_text)
        
        sentiment = result_json.get("sentiment", "NEUTRAL")
        if sentiment not in ["POSITIVE", "NEGATIVE", "NEUTRAL"]:
            sentiment = "NEUTRAL"
            
        logger.info(f"Claude analizi tamamlandı: {hisse} -> {sentiment}")
            
        result = {
            "sentiment": sentiment,
            "sentiment_score": float(result_json.get("sentiment_score", 0.0)),
            "news_count": len(headlines),
            "highlight": result_json.get("highlight", "Haber analizi yapıldı ancak YZ özet çıkartamadı."),
            "mode": "deep"
        }
        
        # Önbelleğe kaydet
        _cache[hisse] = {"result": result, "timestamp": time.time()}
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Claude API JSON parse hatası [{hisse}]: {e}\nRaw Response: {result_text}")
        # JSON hatasında bile raw text'ten faydalanmayı dene
        fallback_highlight = result_text[:300] if result_text else "Yapay Zeka analiz sonucunu okuyamadı."
        result = {
            "sentiment": "NEUTRAL",
            "sentiment_score": 0.0,
            "news_count": len(headlines) if 'headlines' in dir() else 0,
            "highlight": fallback_highlight,
            "mode": "deep_error"
        }
        _cache[hisse] = {"result": result, "timestamp": time.time()}
        return result
    except Exception as e:
        logger.error(f"Claude API veya haber çekme hatası [{hisse}]: {e}")
        return {
            "sentiment": "NEUTRAL",
            "sentiment_score": 0.0,
            "news_count": 0,
            "highlight": f"Yapay Zeka servisine bağlanırken bir hata oluştu: {str(e)}",
            "mode": "deep_error"
        }
