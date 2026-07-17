# -*- coding: utf-8 -*-
"""
Telegram Etkileşim Botu (User-Facing Bot)
=========================================
Kullanicilarin Telegram üzerinden bota mesaj atarak (ornegin: /analiz EREGL)
anlik Tahtaci Skoru ve rapor almasini saglar.

Kullanim:
---------
1. @BotFather'dan bir bot olusturun ve TOKEN alin.
2. .env dosyasina sunu ekleyin:
   TELEGRAM_BOT_TOKEN=...
3. python telegram_bot.py calistirin.
"""

import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from signal_engine import generate_signals

# Ayarlar
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Logger
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanici bota /start yazdiginda calisir."""
    await update.message.reply_text(
        "🐍 Merhaba! Ben SNAKE EYE (Tahtaci Avcisi) Bot.\n"
        "Bana '/analiz HISSE' formatinda mesaj atarak anlik durum sorgulayabilirsiniz.\n"
        "Ornek: /analiz THYAO"
    )

async def analiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanici /analiz HISSE yazdiginda calisir."""
    if not context.args:
        await update.message.reply_text("Lutfen bir hisse sembolu girin. Ornek: /analiz EREGL")
        return
        
    hisse = context.args[0].upper().strip()
    await update.message.reply_text(f"⏳ {hisse} icin Tahtaci Skoru ve tuzak analizleri hesaplaniyor, lutfen bekleyin...")
    
    try:
        # Analizi calistir (Sinyal motoru veritabanindan okuyacak)
        # Not: Eger veritabaninda guncel veri yoksa (Scraper tarafindan henuz eklenmemisse)
        # sinyal motoru eski verilere gore calisabilir veya hata verebilir.
        results = generate_signals([hisse])
        
        if not results:
            await update.message.reply_text("Analiz sonucu bulunamadi veya hisse veritabaninda yok.")
            return
            
        r = results[0]
        
        if "error" in r and r.get("market_status") != "LOCKED":
            await update.message.reply_text(f"❌ Hata: {r['error']}")
            return
            
        score = r.get("tahtaci_score", 0)
        status = r.get("market_status", "UNKNOWN")
        summary = r.get("summary", "")
        trap = r.get("trap_analysis")
        
        # Mesaj sablonu olustur
        if status == "LOCKED":
            msg = f"🚨 **SISTEM KILITLI** 🚨\n\nEndeks kisa vade ortalamalarinin altinda. Risk yuksek oldugu icin analiz uretilmedi.\nDetay: {summary}"
        else:
            msg = f"📊 **{hisse} ANALIZ RAPORU** 📊\n\n"
            msg += f"🔥 **Tahtaci Skoru:** {score:.1f} / 100\n"
            msg += f"📈 **Piyasa Durumu:** {status}\n\n"
            msg += f"💡 **Karar Özeti:** {summary}\n\n"
            
            if trap:
                msg += f"🪤 **Tuzak Savar:**\n"
                msg += f"- Bollinger Squeeze: {'Aktif' if trap.squeeze_active else 'Yok'}\n"
                msg += f"- Bear Trap: {'Tespit Edildi' if trap.bear_trap_detected else 'Yok'}\n\n"
                
            entries = r.get("entry_signals", [])
            exit_sig = r.get("exit_signal", False)
            
            if exit_sig:
                msg += "📉 **ÇIKIŞ SİNYALİ:** Dağıtım emareleri veya EMA21 kırılımı tespit edildi!"
            elif entries:
                msg += "🚀 **ALIM SİNYALLERİ:**\n" + "\n".join([f"- {e}" for e in entries])
            else:
                msg += "👁️ Sinyal yok, izlemede."
                
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        logger.error("Analiz sirasinda hata: %s", e)
        await update.message.reply_text(f"Sistem Hatasi: {str(e)}")

def main():
    if not BOT_TOKEN:
        logger.error("Lutfen .env dosyasina TELEGRAM_BOT_TOKEN degerini girin.")
        return
        
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Komutlari bagla
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("analiz", analiz_command))
    
    logger.info("SNAKE EYE Bot calisiyor...")
    application.run_polling()

if __name__ == "__main__":
    main()
