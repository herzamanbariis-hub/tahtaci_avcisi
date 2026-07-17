# -*- coding: utf-8 -*-
"""
Arka Plan Veri Çekme Robotu (Telethon & BeautifulSoup)
======================================================
Bu script, UserBot mantığı ile Telegram üzerinden @hisseyorumbot'a mesaj atarak
AKD ve Takas butonlarına tıklar. Gelen anlık (kurek hashli) WebApp linkini
alır almaz HTTP GET ile HTML'i indirir. BeautifulSoup ile HTML parse edilerek
gerçek veriler tahtaci_avcisi.db SQLite veritabanına yazılır.
"""

import asyncio
import os
import urllib.request
import logging
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telethon import TelegramClient

from database import insert_akd_data, insert_takas_data

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DataIngestion")

load_dotenv()
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

import argparse
from stock_lists import TUM_HISSELER, BIST30, BIST100, BIST_DISI

# BIST_STOCKS definition removed (moved to stock_lists.py)

def parse_akd_html(html: str, symbol: str) -> pd.DataFrame:
    """HTML'den Alanlar ve Satanlar tablosunu parse eder."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Tarihi bul
    date_spans = soup.find_all("span", class_="card-value")
    tarih = datetime.today().strftime('%Y-%m-%d')
    for idx, span in enumerate(soup.find_all("span", class_="card-label")):
        if "İlk Tarih" in span.text:
            tarih = date_spans[idx].text.strip()
            break
            
    records = []
    
    # 2 adet card-container (Alanlar ve Satanlar) olmali
    containers = soup.find_all("div", class_="card-container")
    for container in containers:
        header = container.find("div", class_="card-header")
        if not header:
            continue
            
        header_text = header.text
        if "Alanlar" in header_text:
            multiplier = 1
        elif "Satanlar" in header_text:
            multiplier = -1
        else:
            continue
            
        # Detay tablosunu bul
        detay_div = container.find("div", class_="akd-detay")
        if not detay_div:
            continue
            
        table = detay_div.find("table", class_="card-table")
        if not table:
            continue
            
        tbody = table.find("tbody")
        if not tbody:
            continue
            
        for tr in tbody.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 4:
                kurum_adi = tds[0].text.strip()
                # 342.18
                avg_price = float(tds[1].text.replace(',', '').strip())
                # 27.84 (oran kullanilmiyor ama lazim degil)
                # 977,942
                net_lot = int(tds[3].text.replace(',', '').strip()) * multiplier
                tutar = net_lot * avg_price
                
                records.append({
                    "hisse": symbol,
                    "tarih": tarih,
                    "kurum_adi": kurum_adi,
                    "net_lot": net_lot,
                    "tutar": tutar,
                    "avg_price": avg_price
                })
                
    return pd.DataFrame(records)

def parse_takas_html(html: str, symbol: str) -> pd.DataFrame:
    """HTML'den Takas tablosunu parse eder."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Tarihi bul
    date_spans = soup.find_all("span", class_="card-value")
    tarih = datetime.today().strftime('%Y-%m-%d')
    for idx, span in enumerate(soup.find_all("span", class_="card-label")):
        if "Son Tarih" in span.text:
            tarih = date_spans[idx].text.strip()
            break
            
    records = []
    
    table = soup.find("table", id="takasveri")
    if not table:
        return pd.DataFrame(records)
        
    tbody = table.find("tbody")
    if not tbody:
        return pd.DataFrame(records)
        
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 4:
            kurum_adi = tds[0].text.strip()
            # 125,784,960
            try:
                lot = int(tds[2].text.replace(',', '').strip())
                saklama_orani = float(tds[3].text.replace(',', '').strip())
            except ValueError:
                continue
            
            records.append({
                "hisse": symbol,
                "tarih": tarih,
                "kurum_adi": kurum_adi,
                "saklama_orani": saklama_orani,
                "saklama_adet": lot
            })
            
    return pd.DataFrame(records)


async def fetch_stock_data(client: TelegramClient, symbol: str):
    """Bir hisse icin AKD ve Takas verilerini Telegram botundan ceker."""
    logger.info(f"{symbol} icin AKD sorgusu baslatiliyor...")
    
    # 1. AKD Icin Sorgu
    try:
        await client.send_message('@hisseyorumbot', symbol)
        await asyncio.sleep(2.5) 
        
        messages = await client.get_messages('@hisseyorumbot', limit=3)
        akd_url = None
        for msg in messages:
            if not msg.reply_markup: continue
            
            logger.info(f"{symbol} AKD butonuna tiklandi, taze link bekleniyor...")
            await msg.click(data=f"{symbol}:akd".encode('utf-8'))
            await asyncio.sleep(2.5)
            
            messages_after = await client.get_messages('@hisseyorumbot', limit=2)
            for msg2 in messages_after:
                if msg2.reply_markup:
                    for row in msg2.reply_markup.rows:
                        for button in row.buttons:
                            if hasattr(button, 'url') and 'webapi.hisseplus.com/ui/akd' in button.url:
                                akd_url = button.url
                                break
                        if akd_url: break
                if akd_url: break
            if akd_url: break
            
        if akd_url:
            logger.info(f"{symbol} AKD Linki yakalandi: {akd_url[:60]}...")
            req = urllib.request.Request(akd_url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req)
            html = res.read().decode('utf-8')
            
            df = parse_akd_html(html, symbol)
            if not df.empty:
                insert_akd_data(df)
                logger.info(f"{symbol} AKD veritabanina yazildi. Kayit sayisi: {len(df)}")
            else:
                logger.warning(f"{symbol} AKD HTML parse edilemedi veya veri bos.")
        else:
            logger.error(f"{symbol} icin AKD URL bulunamadi!")
    except Exception as e:
        logger.error(f"{symbol} AKD islenirken hata: {e}")

    await asyncio.sleep(2) # Bekle biraz
    
    # 2. TAKAS Icin Sorgu
    logger.info(f"{symbol} icin TAKAS sorgusu baslatiliyor...")
    try:
        await client.send_message('@hisseyorumbot', symbol)
        await asyncio.sleep(2.5) 
        
        messages = await client.get_messages('@hisseyorumbot', limit=3)
        takas_url = None
        for msg in messages:
            if not msg.reply_markup: continue
            
            logger.info(f"{symbol} TAKAS butonuna tiklaniyor...")
            await msg.click(data=f"{symbol}:takas".encode('utf-8'))
            await asyncio.sleep(2.5)
            
            messages_after_takas = await client.get_messages('@hisseyorumbot', limit=2)
            for msg3 in messages_after_takas:
                if msg3.reply_markup:
                    for row in msg3.reply_markup.rows:
                        for button in row.buttons:
                            if hasattr(button, 'url') and 'webapi.hisseplus.com/ui/takas' in button.url:
                                takas_url = button.url
                                break
                        if takas_url: break
                if takas_url: break
            if takas_url: break
            
        if takas_url:
            logger.info(f"{symbol} TAKAS Linki yakalandi: {takas_url[:60]}...")
            req = urllib.request.Request(takas_url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req)
            takas_html = res.read().decode('utf-8')
            
            takas_df = parse_takas_html(takas_html, symbol)
            if not takas_df.empty:
                insert_takas_data(takas_df)
                logger.info(f"{symbol} TAKAS veritabanina yazildi. Kayit sayisi: {len(takas_df)}")
            else:
                logger.warning(f"{symbol} TAKAS HTML parse edilemedi veya veri bos.")
        else:
            logger.error(f"{symbol} icin TAKAS URL bulunamadi!")
            
    except Exception as e:
        logger.error(f"{symbol} TAKAS islenirken hata: {e}")


async def main(target_list, group_name):
    client = TelegramClient('tahtaci_session', API_ID, API_HASH)
    await client.start()
    
    logger.info(f"Arka Plan Veri Toplama Robotu Basladi! Grup: {group_name} ({len(target_list)} Hisse)")
    
    import json
    from datetime import datetime
    
    def update_progress(status, current_sym, current_idx, total, err=""):
        try:
            with open("progress.json", "w", encoding="utf-8") as f:
                json.dump({
                    "status": status,
                    "group": group_name,
                    "current_symbol": current_sym,
                    "current_index": current_idx,
                    "total": total,
                    "error": err,
                    "last_update": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }, f)
        except Exception:
            pass

    import os, json
    start_idx = 0
    if os.path.exists('progress.json'):
        try:
            with open('progress.json', 'r', encoding='utf-8') as f:
                prog = json.load(f)
            if prog.get('status') == 'RUNNING' and prog.get('group') == group_name:
                last_sym = prog.get('current_symbol')
                if last_sym in target_list:
                    start_idx = target_list.index(last_sym)
                    logger.info(f"Kaldigi yerden devam ediyor: {last_sym} (Index: {start_idx})")
        except:
            pass

    total_len = len(target_list)
    update_progress("RUNNING", target_list[start_idx] if total_len > 0 else "", start_idx, total_len)
    
    for idx in range(start_idx, total_len):
        symbol = target_list[idx]
        update_progress("RUNNING", symbol, idx + 1, total_len)
        try:
            if not client.is_connected():
                logger.warning("Baglanti kopmus, yeniden baglaniliyor...")
                await client.connect()
                
            await fetch_stock_data(client, symbol)
            await asyncio.sleep(5) # Hisseler arasi bekleme suresi artirildi (Spam ban yememek icin)
        except Exception as e:
            logger.error(f"Dongu hatasi ({symbol}): {e}")
            update_progress("RUNNING", symbol, idx + 1, total_len, err=str(e))
            await asyncio.sleep(10)
        
    update_progress("COMPLETED", "", total_len, total_len)
    logger.info(f"Tarama tamamlandi. Grup: {group_name}")
    
    # Yeni cekilen veriler uzerinden SMC Sniper / Toplanma sinyali arayip alarmlari calistir
    logger.info("Telegram Canli Alarm sistemi tetikleniyor...")
    try:
        from signal_engine import generate_signals
        from notifier_bot import check_and_alert_signals
        
        # Sadece taradigimiz grup icin sinyal uret
        results = generate_signals(target_list, "tahtaci_avcisi.db")
        check_and_alert_signals(results)
        
    except Exception as e:
        logger.error(f"Telegram Alarm sistemi calisirken hata olustu: {e}")

    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--group', type=str, default='ALL', choices=['BIST30', 'BIST100', 'BIST_DISI', 'ALL'])
    parser.add_argument('--symbols', type=str, default=None, help='Comma separated list of symbols (e.g. THYAO,EREGL)')
    args = parser.parse_args()
    
    if args.symbols:
        target = [s.strip().upper() for s in args.symbols.split(',')]
        group_name = f"CUSTOM ({args.symbols})"
    elif args.group == 'BIST30':
        target = BIST30
        group_name = args.group
    elif args.group == 'BIST100':
        target = BIST100
        group_name = args.group
    elif args.group == 'BIST_DISI':
        target = BIST_DISI
        group_name = args.group
    else:
        target = TUM_HISSELER
        group_name = args.group
        
    asyncio.run(main(target, group_name))

