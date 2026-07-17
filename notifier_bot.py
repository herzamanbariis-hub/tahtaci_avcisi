# -*- coding: utf-8 -*-
"""
Telegram Canlı Alarm Botu (Notifier)

Arka planda çalışan data_ingestion sistemi,
"SMC Sniper" veya "Yüksek Tahtacı Skoru" gibi güçlü sinyaller yakaladığında
kullanıcıya anlık Telegram mesajı gönderir.
"""

import requests
import logging
import os

logger = logging.getLogger(__name__)

# Güvenlik açısından Token ve Chat ID ortam değişkenlerinden (Environment Variables) 
# veya config dosyasından çekilmelidir. Test için boş bırakılmıştır.
TELEGRAM_BOT_TOKEN = os.getenv("TAHTACI_BOT_TOKEN", "BURAYA_TOKEN_YAZIN")
TELEGRAM_CHAT_ID = os.getenv("TAHTACI_CHAT_ID", "BURAYA_CHAT_ID_YAZIN")

def send_telegram_alert(message: str) -> bool:
    """
    Belirtilen mesajı kullanıcının Telegram adresine gönderir.
    
    Parameters:
        message (str): Gönderilecek mesaj.
        
    Returns:
        bool: Gönderim başarılı ise True.
    """
    if TELEGRAM_BOT_TOKEN == "BURAYA_TOKEN_YAZIN" or TELEGRAM_CHAT_ID == "BURAYA_CHAT_ID_YAZIN":
        logger.warning("Telegram Bot Token veya Chat ID yapılandırılmamış. Mesaj gönderilmedi: %s", message)
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("Telegram alarmı başarıyla gönderildi.")
            return True
        else:
            logger.error("Telegram alarm gönderimi başarısız: %s", response.text)
            return False
    except Exception as e:
        logger.error("Telegram API bağlantı hatası: %s", e)
        return False

def check_and_alert_signals(results: list):
    """
    Analiz sonuçlarını tarar ve güçlü sinyaller için alarm gönderir.
    
    Parameters:
        results (list): generate_signals() çıktısı.
    """
    for res in results:
        hisse = res.get("hisse")
        if hisse == "ENDEKS_KILIDI":
            if res.get("market_status") == "LOCKED":
                send_telegram_alert("🚨 <b>SİSTEM KİLİDİ:</b> Endeks kritik desteği (SMA200) kırdı. Piyasada risk yüksek, alımlar durduruldu.")
            continue
            
        score = res.get("tahtaci_score", 0)
        smc_sniper = res.get("smc_sniper", False)
        
        if smc_sniper:
            msg = f"🎯 <b>SMC SNIPER ALARMI: {hisse}</b>\n\n"
            msg += f"Tahtacı Skoru: <b>{score}/100</b>\n"
            msg += "Müthiş bir ayı tuzağı (Bear Trap) tespit edildi. Küçük yatırımcı döküldü ve mal tek elde toplandı. Acil inceleyin!"
            send_telegram_alert(msg)
            
        elif score >= 80:
            msg = f"🚀 <b>GÜÇLÜ TOPLANMA ALARMI: {hisse}</b>\n\n"
            msg += f"Tahtacı Skoru: <b>{score}/100</b>\n"
            msg += "Hissede devasa bir kurumsal para girişi ve konsantrasyon tespit edildi. Radara alındı."
            send_telegram_alert(msg)
