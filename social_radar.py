# -*- coding: utf-8 -*-
"""
Sosyal Medya Radarı (Telegram & X) - Pump & Dump Dedektörü
==========================================================
Bu modül, hisselerin sosyal medyadaki (Telegram ve X) "hype" (popülarite) seviyesini ölçer.
Amacı: Tahtacı mal toplarken sessizlik olur, malı ky'ye (küçük yatırımcı) satarken ise
Telegram gruplarında ve X'te şelale gibi övgü/haber akışı olur.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import logging

logger = logging.getLogger(__name__)

# Örnek Borsa Telegram Kanalları (Herkese açık web önizlemesi olanlar)
# t.me/s/ ile başlayan kanallar HTML olarak kazınabilir.
TELEGRAM_CHANNELS = [
    "BorsaGundem",
    "borsa_haberr",
    "kriptoborsa",
    # Buraya popüler grupların ID'leri eklenebilir.
]

def scan_telegram_for_symbol(symbol: str) -> dict:
    """
    Belirli Telegram kanallarının web önizlemelerini (t.me/s/...) tarar
    ve hisse sembolünün kaç kez geçtiğini sayar.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    total_mentions = 0
    recent_messages = []
    
    symbol_upper = symbol.upper()
    
    for channel in TELEGRAM_CHANNELS:
        url = f"https://t.me/s/{channel}"
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message_text')
                
                for msg in messages:
                    text = msg.get_text(separator=' ').upper()
                    # Sembol geçiyorsa (örneğin ANELE veya #ANELE)
                    if re.search(r'\b' + re.escape(symbol_upper) + r'\b', text):
                        total_mentions += 1
                        recent_messages.append({
                            "channel": channel,
                            "text": text[:200] + "..." if len(text) > 200 else text
                        })
            time.sleep(0.5) # Anti-ban
        except Exception as e:
            logger.error(f"Telegram scrape hatası ({channel}): {e}")
            
    # Hype Skorunu Hesapla (Basit mantık)
    # 0 mentions = Sessizlik (İyi, tahtacı topluyor olabilir)
    # 5+ mentions = Yüksek Hype (Kötü, ky'ye mal boşaltılıyor olabilir)
    
    hype_score = min(total_mentions * 20, 100) # Maks 100
    
    status = "SESSİZ"
    if total_mentions >= 3:
        status = "ORTA HYPE"
    if total_mentions >= 7:
        status = "AŞIRI HYPE (RİSKLİ)"
        
    return {
        "total_mentions": total_mentions,
        "hype_score": hype_score,
        "status": status,
        "recent_messages": recent_messages
    }

def get_x_search_link(symbol: str) -> str:
    """X (Twitter) üzerinde hisseyi aramak için direkt link üretir."""
    # Cashtag ($) veya Hashtag (#) ile
    return f"https://twitter.com/search?q=%24{symbol.upper()}%20OR%20%23{symbol.upper()}&src=typed_query&f=live"

def get_social_summary(symbol: str) -> dict:
    """Finans Ajanı için sosyal medya özetini döndürür."""
    tg_data = scan_telegram_for_symbol(symbol)
    x_link = get_x_search_link(symbol)
    
    return {
        "telegram": tg_data,
        "x_url": x_link,
        "summary_text": f"Telegram'da Son Durum: {tg_data['status']} ({tg_data['total_mentions']} bahsedilme). Hype Skoru: {tg_data['hype_score']}/100"
    }

if __name__ == "__main__":
    test_hisse = "THYAO"
    print(f"{test_hisse} Sosyal Radar Testi:")
    res = get_social_summary(test_hisse)
    print(res["summary_text"])
    for m in res["telegram"]["recent_messages"]:
        print(f"- {m['channel']}: {m['text'][:100]}")
    print("X Arama Linki:", res["x_url"])
