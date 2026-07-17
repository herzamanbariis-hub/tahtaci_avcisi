import asyncio
import os
import urllib.request
import pandas as pd
import yfinance as yf
from typing import Dict, Any, List
import logging

import env
from telethon import TelegramClient
from telethon.sessions import StringSession

logger = logging.getLogger("TelegramMiniAppScraper")

class TelegramMiniAppScraper:
    def __init__(self, **kwargs):
        self.api_id = 31078357
        self.api_hash = "0fd6f44418f0aa9ed74f2957f2f33e06"
        self.bot_username = env.TARGET_GROUP_USERNAME or '@hisseyorumbot'

    async def _get_url_from_bot(self, hisse: str, action_type: str, tarih: str) -> str:
        """
        Telethon kullanarak bota komut gonderir ve donen url'yi alir.
        """
        session_file = os.path.join(os.path.dirname(__file__), 'tahtaci_session')
        client = TelegramClient(session_file, self.api_id, self.api_hash)
        
        await client.start()
        url = None
        try:
            # Komut olustur: orn: /akd THYAO 2026-07-16 2026-07-16
            cmd = f"/{action_type} {hisse} {tarih} {tarih}"
            await client.send_message(self.bot_username, cmd)
            await asyncio.sleep(2.5)
            
            messages = await client.get_messages(self.bot_username, limit=2)
            for msg in messages:
                if msg.reply_markup:
                    for row in msg.reply_markup.rows:
                        for button in row.buttons:
                            if hasattr(button, 'url') and 'webapi.hisseplus.com' in button.url:
                                url = button.url
                                break
        finally:
            await client.disconnect()
            
        return url

    def _fetch_html_table(self, url: str) -> pd.DataFrame:
        if not url:
            return pd.DataFrame()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req)
            html = res.read().decode('utf-8')
            dfs = pd.read_html(html)
            if dfs:
                return dfs[0]
        except Exception as e:
            logger.error("HTML indirelmedi veya parse edilemedi: %s", e)
        return pd.DataFrame()

    def fetch_akd(self, hisse: str, tarih: str) -> pd.DataFrame:
        logger.info(f"Telethon ile AKD cekiliyor: {hisse} - {tarih}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        url = loop.run_until_complete(self._get_url_from_bot(hisse, "akd", tarih))
        
        if not url:
            return pd.DataFrame(columns=["hisse", "tarih", "kurum_adi", "net_lot", "tutar", "avg_price"])
            
        df_raw = self._fetch_html_table(url)
        if df_raw.empty:
            return pd.DataFrame(columns=["hisse", "tarih", "kurum_adi", "net_lot", "tutar", "avg_price"])
            
        try:
            df = pd.DataFrame()
            df['hisse'] = [hisse] * len(df_raw)
            df['tarih'] = [tarih] * len(df_raw)
            df['kurum_adi'] = df_raw.iloc[:, 0]
            
            def clean_number(x):
                if isinstance(x, str):
                    x = x.replace('.', '').replace(',', '.')
                return pd.to_numeric(x, errors='coerce')
                
            df['avg_price'] = df_raw.iloc[:, 1].apply(clean_number)
            df['net_lot'] = df_raw.iloc[:, 3].apply(clean_number)
            df['tutar'] = df['net_lot'] * df['avg_price']
            
            return df[["hisse", "tarih", "kurum_adi", "net_lot", "tutar", "avg_price"]]
        except Exception as e:
            logger.error(f"AKD df donusturme hatasi: {e}")
            return pd.DataFrame(columns=["hisse", "tarih", "kurum_adi", "net_lot", "tutar", "avg_price"])


    def fetch_takas(self, hisse: str, tarih: str) -> pd.DataFrame:
        logger.info(f"Telethon ile Takas cekiliyor: {hisse} - {tarih}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        url = loop.run_until_complete(self._get_url_from_bot(hisse, "takas", tarih))
        
        if not url:
            return pd.DataFrame(columns=["hisse", "tarih", "kurum_adi", "saklama_orani", "saklama_adet"])
            
        df_raw = self._fetch_html_table(url)
        if df_raw.empty:
            return pd.DataFrame(columns=["hisse", "tarih", "kurum_adi", "saklama_orani", "saklama_adet"])
            
        try:
            df = pd.DataFrame()
            df['hisse'] = [hisse] * len(df_raw)
            df['tarih'] = [tarih] * len(df_raw)
            df['kurum_adi'] = df_raw.iloc[:, 0]
            
            def clean_number(x):
                if isinstance(x, str):
                    x = x.replace('%', '').replace('.', '').replace(',', '.')
                return pd.to_numeric(x, errors='coerce')
                
            if df_raw.shape[1] >= 3:
                df['saklama_orani'] = df_raw.iloc[:, 1].apply(clean_number)
                df['saklama_adet'] = df_raw.iloc[:, 2].apply(clean_number)
            else:
                df['saklama_orani'] = 0.0
                df['saklama_adet'] = 0.0
                
            return df[["hisse", "tarih", "kurum_adi", "saklama_orani", "saklama_adet"]]
        except Exception as e:
            logger.error(f"Takas df donusturme hatasi: {e}")
            return pd.DataFrame(columns=["hisse", "tarih", "kurum_adi", "saklama_orani", "saklama_adet"])


    def fetch_derinlik(self, hisse: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["hisse", "kademe", "alis_lot", "alis_fiyat", "satis_fiyat", "satis_lot"])


    def fetch_price(self, hisse: str, tarih_baslangic: str, tarih_bitis: str) -> pd.DataFrame:
        try:
            logger.info(f"yfinance ile fiyat cekiliyor: {hisse}")
            ticker_str = hisse if hisse == "XU100.IS" else (f"{hisse}.IS" if not hisse.endswith(".IS") else hisse)
            if hisse == "ENDEKS_KILIDI":
                ticker_str = "XU100.IS"
                
            ticker = yf.Ticker(ticker_str)
            df = ticker.history(start=tarih_baslangic, end=tarih_bitis)
            
            if df.empty:
                return pd.DataFrame(columns=["hisse", "tarih", "open", "high", "low", "close", "volume"])
                
            df = df.reset_index()
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            
            result_df = pd.DataFrame({
                "hisse": hisse,
                "tarih": df["Date"],
                "open": df["Open"],
                "high": df["High"],
                "low": df["Low"],
                "close": df["Close"],
                "volume": df["Volume"]
            })
            return result_df
            
        except Exception as e:
            logger.error("Fiyat cekme hatasi [%s/%s-%s]: %s", hisse, tarih_baslangic, tarih_bitis, e)
            return pd.DataFrame(columns=["hisse", "tarih", "open", "high", "low", "close", "volume"])

def apply_liquidity_filter(df: pd.DataFrame, min_volume: int = 10000) -> pd.DataFrame:
    return df
