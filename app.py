# -*- coding: utf-8 -*-
"""
Tahtacı Avcısı v1.0 — Streamlit Dashboard (SNAKE EYE)
======================================================
"""

import streamlit as st
import pandas as pd
import os
import sys
import plotly.graph_objects as go
import plotly.express as px

# Windows cp1254 encoding sorunu için utf-8 ayarı
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from database import init_db, query_df
from main import load_data
from telegram_scraper import TelegramMiniAppScraper
from signal_engine import generate_signals
from config import DB_PATH, RESIDUAL_LOOKBACK_DAYS

st.set_page_config(
    page_title="SNAKE EYE | Tahtacı Avcısı",
    page_icon="🐍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Tema olarak Dark seçildiğinden CSS ile ekstra makyajlamalar
st.markdown("""
<style>
.stMetric {
    background-color: #1e1e1e;
    padding: 15px;
    border-radius: 8px;
    border: 1px solid #333;
}
</style>
""", unsafe_allow_html=True)

st.title("🐍 SNAKE EYE — BİST Sinyal ve Analiz Asistanı")
st.markdown("Tahtacı toplama bölgeleri, aracı kurum kümeleri ve tuzak dedektörleri...")

tab_analiz, tab_portfoy, tab_sektor, tab_backtest, tab_yabanci, tab_para_akisi = st.tabs([
    "📊 Sinyal ve Analiz", 
    "💼 Portföy Yönetimi", 
    "🗺️ Sektör Haritası", 
    "🔄 Backtest Motoru",
    "🌍 Yabancı Takas Avcısı",
    "💸 Sektörel Para Akışı"
])
# DB Başlat (Tabloları kur)
init_db(DB_PATH)


# ── SİDEBAR (MENÜ) ──
from stock_lists import TUM_HISSELER, BIST30, BIST100, BIST_DISI
import subprocess

st.sidebar.header("⚙️ Analiz Ayarları")

analiz_grubu = st.sidebar.selectbox(
    "Analiz Edilecek Liste",
    ["Belirli Hisseler", "BIST 30 (Hızlı)", "BIST 100", "BIST DIŞI", "TÜM LİSTE (Radar Modu)"]
)

if analiz_grubu == "Belirli Hisseler":
    hisse_input = st.sidebar.text_input(
        "Hisse Sembolleri (Virgülle Ayırın)",
        value=""
    )
else:
    radar_esik = st.sidebar.slider(
        "Radar Tahtacı Skoru Eşiği",
        min_value=0, max_value=100, value=60, step=5,
        help="Sadece bu skorun üzerindeki hisseler gösterilir."
    )

days_input = st.sidebar.number_input(
    "Geriye Bakış (Gün)",
    min_value=10, max_value=500, value=RESIDUAL_LOOKBACK_DAYS, step=10
)

skip_load = st.sidebar.checkbox("Veri Yüklemeyi Atla (Sadece Analiz Yap)", value=False)

st.sidebar.markdown("---")

with st.sidebar.expander("🛠️ Veritabanını Güncelle (Tehlikeli)"):
    st.warning("Dikkat: Bu buton arka planda Telegram botunu çalıştırır. Sık basmak ban sebebidir.")
    
    if analiz_grubu == "Belirli Hisseler":
        st.info(f"Seçilen Hisseler: {hisse_input}")
        if st.button("🚀 Sadece Seçili Hisseleri Güncelle", use_container_width=True):
            if hisse_input.strip():
                # Bosluklari sil ve birlestir
                clean_symbols = ",".join([s.strip().upper() for s in hisse_input.split(",") if s.strip()])
                subprocess.Popen(["python", "data_ingestion.py", "--symbols", clean_symbols])
                st.success(f"{clean_symbols} için Telegram robotu arka planda başlatıldı! (Yaklaşık {len(clean_symbols.split(','))*15} saniye sürecek)")
            else:
                st.error("Lütfen önce hisse sembolü girin!")
    else:
        secilen_grup = st.selectbox("Taranacak Hisse Grubu", ["BIST30", "BIST100", "BIST_DISI", "ALL"])
        if st.button("🔄 Tüm Grubu Telegram'dan Çek", use_container_width=True):
            subprocess.Popen(["python", "data_ingestion.py", "--group", secilen_grup])
            st.success(f"{secilen_grup} için robot başlatıldı.")

import os, json
if os.path.exists("progress.json"):
    try:
        with open("progress.json", "r", encoding="utf-8") as f:
            prog = json.load(f)
        if prog.get("status") == "RUNNING":
            st.sidebar.markdown("### 🔄 Veri Çekimi Devam Ediyor")
            c = prog.get('current_index', 0)
            t = prog.get('total', 1)
            pct = min(1.0, c / t) if t > 0 else 0
            st.sidebar.progress(pct)
            st.sidebar.write(f"**İşlenen:** {c} / {t}")
            st.sidebar.write(f"**Şu Anki Hisse:** {prog.get('current_symbol', '')}")
            if st.sidebar.button("⏳ Durumu Yenile"):
                st.rerun()
        elif prog.get("status") == "COMPLETED":
            st.sidebar.success(f"✅ Son Tarama Tamamlandı ({prog.get('group', '')})")
            if st.sidebar.button("Kapat"):
                os.remove("progress.json")
                st.rerun()
    except Exception:
        pass

st.sidebar.markdown("---")
if st.sidebar.button("🚀 Analizi Başlat", type="primary"):
    
    with st.spinner("Piyasa verileri analiz ediliyor, lütfen bekleyin..."):
        
        target_symbols = []
        if analiz_grubu == "Belirli Hisseler":
            target_symbols = [s.strip().upper() for s in hisse_input.split(",") if s.strip()]
            if not target_symbols:
                st.warning("Lütfen en az bir hisse sembolü girin!")
                st.stop()
        elif analiz_grubu == "BIST 30 (Hızlı)":
            target_symbols = BIST30
        elif analiz_grubu == "BIST 100":
            target_symbols = BIST100
        elif analiz_grubu == "BIST DIŞI":
            target_symbols = BIST_DISI
        elif analiz_grubu == "TÜM LİSTE (Radar Modu)":
            target_symbols = TUM_HISSELER

        # Radar esigini global olarak saklamak icin
        if analiz_grubu != "Belirli Hisseler":
            st.session_state['radar_esik'] = radar_esik
            st.session_state['analiz_modu_spesifik'] = False  # Grup taraması: Claude kapalı
        else:
            st.session_state['radar_esik'] = 0
            st.session_state['analiz_modu_spesifik'] = True   # Tek hisse: Claude açık
        
    try:
        # Fiyat Verisini Yükle (AKD/Takas arka plan botundan gelecek)
        if not skip_load:
            with st.spinner("Gerçek piyasa verileri çekiliyor..."):
                scraper = TelegramMiniAppScraper()
                # Sadece price verisini ceker (cunku load_data icinde AKD fail olursa price yine de cekilir)
                stats = load_data(scraper, target_symbols, days_input)
                st.success(f"Fiyatlar Yüklendi! (AKD ve Takas arka plan botu tarafından besleniyor)")
                
        # 3. Analiz
        with st.spinner("Yapay zeka ve kümeleme algoritmaları çalışıyor..."):
            results = generate_signals(target_symbols, DB_PATH)
            
        st.success("Analiz tamamlandı!")
        
        st.session_state['results'] = results
    except Exception as e:
        st.error(f"Analiz sırasında bir hata oluştu: {str(e)}")


# ── SONUÇLARI GÖRSELLEŞTİRME ──
if 'results' in st.session_state:
    with tab_analiz:
        st.divider()
        st.subheader("📊 Analiz Sonuçları")
        
        sorted_results = sorted(
            st.session_state['results'],
            key=lambda x: x.get("tahtaci_score", 0),
            reverse=True,
        )
    
        if st.session_state.get('radar_esik', 0) > 0:
            esik = st.session_state['radar_esik']
            # Sadece skoru eşikten büyük olanları filtrele (Endeks kilit kontrolü hariç)
            sorted_results = [r for r in sorted_results if r.get("hisse") == "ENDEKS_KILIDI" or r.get("tahtaci_score", 0) >= esik]
            st.info(f"🔍 **Radar Modu Aktif:** Tüm liste tarandı. {len([r for r in sorted_results if r.get('hisse') != 'ENDEKS_KILIDI'])} hissede anormal toplama (Skor ≥ {esik}) tespit edildi!")
        
        st.markdown("##### 🚦 Sinyal Renk Filtresi")
        renk_filtresi = st.multiselect(
            "Görmek istediğiniz sinyalleri seçin (Boş bırakırsanız tümü listelenir):",
            ["🟢 Yeşil (Güçlü Alış / SMC Sniper)", "🟡 Sarı (Pusu / Bekle)", "🔴 Kırmızı (Zayıf / Pas Geç)"],
            default=[]
        )
    
        # Renk filtresi uygulama
        if renk_filtresi:
            filtered_results = []
            for r in sorted_results:
                if r.get("hisse") == "ENDEKS_KILIDI":
                    filtered_results.append(r)
                    continue
                score = r.get("tahtaci_score", 0)
                smc = r.get("smc_sniper", False)
                if score >= 70 or smc:
                    color = "🟢 Yeşil (Güçlü Alış / SMC Sniper)"
                elif score >= 50:
                    color = "🟡 Sarı (Pusu / Bekle)"
                else:
                    color = "🔴 Kırmızı (Zayıf / Pas Geç)"
                if color in renk_filtresi:
                    filtered_results.append(r)
            sorted_results = filtered_results
    
        # Endeks kontrolü
        endeks_res = next((r for r in sorted_results if r.get("hisse") == "ENDEKS_KILIDI"), None)
        if endeks_res:
            status = endeks_res.get("market_status", "UNKNOWN")
            if status == "LOCKED":
                st.error(f"🚨 **SİSTEM KİLİTLİ:** XU100 Endeksi SMA200 altında veya yeterli veri yok! Sinyal üretimi durduruldu. \n\n*Hata Detayı: {endeks_res.get('error', '')}*")
            else:
                st.info(f"📈 **SİSTEM AÇIK:** XU100 Endeksi SMA200 üzerinde (Güvenli Bölge).")
    
        # Hisseleri Listele
        for r in sorted_results:
            if r.get("hisse") == "ENDEKS_KILIDI":
                continue
                
            h = r.get("hisse", "?")
            score = r.get("tahtaci_score", 0)
            status = r.get("market_status", "?")
            summary = r.get("summary", r.get("error", "Hata Oluştu"))
            smc_sniper = r.get("smc_sniper", False)
            
            with st.expander(f"**{h}** — Skor: {score:.1f}/100 — Durum: {status}", expanded=(score > 50 or smc_sniper)):
                if "error" in r and "market_status" not in r: # Gerçek hata
                    st.error(r["error"])
                    continue
                
                if smc_sniper:
                    st.error("🎯 **KESKİN NİŞANCI (SMC SNIPER) SİNYALİ TESPİT EDİLDİ!**\n\nTahtacı, destek kırılımıyla küçük yatırımcının stoplarını patlattı ve dökülen malın büyük bir kısmını (%70+) tek elde topladı! Bu, kusursuz bir tuzak ve çok güçlü bir alış fırsatıdır.")
                
                esik = st.session_state.get('radar_esik', 0)
                
                # Radar modu aktifse sadece esigin ustundekileri goster
                if esik > 0 and score < esik:
                    st.warning("Bu hisse radar eşiğinin altında.")
                    continue

            
            # Özet metin
            if status == "LOCKED":
                st.warning(f"Sistem kilitli olduğu için sinyal analizleri pas geçildi.")
            else:
                st.write(f"**Karar Özeti:** {summary}")
                
                # Karanlık Oda Gösterimi
                dark_pool = r.get("dark_pool")
                if dark_pool and dark_pool.get("signal") != "NÖTR":
                    st.info(f"🦇 **KARANLIK ODA (Eşleşme):** {dark_pool.get('message', '')} *(Hacim: {dark_pool.get('volume_ratio', 0)}%, Fiyat Değişimi: {dark_pool.get('price_diff_pct', 0)}%)*")
            
            # Metrikler
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Tahtacı Skoru", f"{score:.1f}", help="0-100 arası toplama potansiyeli")
            
            trap = r.get("trap_analysis")
            if trap:
                col2.metric("Tuzak Skoru", f"{trap.trap_score:.1f}", help="Bollinger Squeeze + Bear Trap risk ölçümü")
                col3.metric("Bollinger Squeeze", "Aktif" if trap.squeeze_active else "Yok")
                col4.metric("Bear Trap", "Tespit Edildi" if trap.bear_trap_detected else "Yok")
            
            # Alt Skorlar
            tahtaci_details = r.get("tahtaci_details", {})
            sub = tahtaci_details.get("sub_scores", {})
            
            # Kurum Profili
            top_buyer = tahtaci_details.get("top_buyer_name", "Bilinmiyor")
            top_type = tahtaci_details.get("top_buyer_type", "Nötr")
            top_mult = tahtaci_details.get("top_buyer_multiplier", 1.0)
            
            st.markdown(f"**🕵️‍♂️ Lider Alıcı Profili:** `{top_buyer}` ➔ **{top_type}** (Çarpan: {top_mult:.1f}x)")
            
            buyer_cost = tahtaci_details.get("buyer_cost", 0.0)
            cost_diff_pct = tahtaci_details.get("cost_diff_pct", 0.0)
            
            if buyer_cost > 0:
                is_profit = cost_diff_pct > 0
                c_color = "green" if is_profit else "red"
                c_icon = "🤑" if is_profit else "🥵"
                st.markdown(f"**{c_icon} Tahtacı Maliyeti (Son 10 Gün):** `{buyer_cost:.2f} TL` ➔ Anlık Durum: :{c_color}[% {cost_diff_pct:.2f} {'Kârda' if is_profit else 'Zararda'}]")
            
            st.markdown("##### Bileşen Skorları (Her biri 100 üzerinden standardize edilmiştir)")
            st.progress(min(score / 100, 1.0))
            
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Kalıntı Yoğunluğu", f"{sub.get('residual_intensity', 0):.1f}")
            m2.metric("Korelasyon Gücü", f"{sub.get('correlation_strength', 0):.1f}")
            m3.metric("Konsantrasyon", f"{sub.get('concentration_ratio', 0):.1f}")
            m4.metric("'Diğer' Eğimi", f"{sub.get('diger_slope', 0):.1f}")
            m5.metric("Süreklilik", f"{sub.get('continuity', 0):.1f}")
            
            # Sinyaller
            entries = r.get("entry_signals", [])
            exit_sig = r.get("exit_signal", False)
            
            if exit_sig:
                st.error("📉 **ÇIKIŞ SİNYALİ:** Dağıtım emareleri veya EMA21 kırılımı tespit edildi!")
            elif entries:
                st.success("🚀 **ALIM SİNYALLERİ:**")
                for e in entries:
                    st.write(f"- {e}")
            else:
                st.info("İzleme listesinde, henüz net bir alım veya çıkış sinyali yok.")
                    
            # Hızlı Takas Verisi Gösterimi
            with st.expander("💼 Güncel Takas Verileri (İlk 5 Kurum)"):
                takas_df = query_df("SELECT tarih, kurum_adi, saklama_adet, saklama_orani FROM takas_data WHERE hisse = ? ORDER BY tarih DESC LIMIT 5", params=(h,), db_path=DB_PATH)
                if not takas_df.empty:
                    st.dataframe(
                        takas_df, 
                        hide_index=True, 
                        use_container_width=True,
                        column_config={
                            "tarih": "Tarih",
                            "kurum_adi": "Kurum",
                            "saklama_adet": st.column_config.NumberColumn("Lot (Adet)", format="%,d"),
                            "saklama_orani": st.column_config.NumberColumn("Oran (%)", format="%.2f")
                        }
                    )
                else:
                    st.write("Bu hisse için güncel takas verisi bulunamadı.")
                    
            # İnteraktif Grafik Şov Alanı
            with st.expander("📊 Savaş Alanı Röntgeni (İnteraktif Grafik & AKD)", expanded=False):
                # 1. Mum Grafiği ve Maliyet Çizgisi
                c_df = query_df("SELECT tarih, open, high, low, close FROM price_data WHERE hisse = ? ORDER BY tarih ASC", params=(h,), db_path=DB_PATH)
                if not c_df.empty:
                    fig = go.Figure(data=[go.Candlestick(x=c_df['tarih'],
                        open=c_df['open'],
                        high=c_df['high'],
                        low=c_df['low'],
                        close=c_df['close'],
                        name="Fiyat")])
                    
                    if buyer_cost > 0:
                        fig.add_hline(y=buyer_cost, line_dash="dash", line_color="red", 
                                      annotation_text="🎯 Tahtacı Maliyeti", annotation_position="bottom right")
                    
                    fig.update_layout(title=f"{h} - Fiyat ve Tahtacı Maliyeti", template="plotly_dark", margin=dict(l=20, r=20, t=40, b=20), height=400)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.write("Grafik için fiyat verisi bulunamadı.")
                    
                # 2. AKD Halka Grafiği (Donut Chart)
                akd_df = query_df("SELECT kurum_adi, net_lot FROM akd_data WHERE hisse = ? AND tarih = (SELECT MAX(tarih) FROM akd_data WHERE hisse = ?) ORDER BY net_lot DESC", params=(h, h), db_path=DB_PATH)
                if not akd_df.empty:
                    # Alanlar (net_lot > 0)
                    alanlar = akd_df[akd_df["net_lot"] > 0]
                    if not alanlar.empty:
                        fig_pie = px.pie(alanlar, values='net_lot', names='kurum_adi', hole=0.4, title="Bugünkü Alıcıların Pasta Payı")
                        fig_pie.update_layout(template="plotly_dark", margin=dict(l=20, r=20, t=40, b=20), height=300)
                        st.plotly_chart(fig_pie, use_container_width=True)
                
            # ARAYUZ BOLME: Gercek Veri vs Teknik
            
            # --- GERCEK VERI (AKD/TAKAS) ---
            st.markdown("### 📊 Gerçek Veri Analizi (AKD & Takas)")
            if score >= 50:
                st.success(f"Tahtacı Skoru **{score:.1f}/100** seviyesinde. Yakın zamanlı verilere göre hissede belirgin bir kurumsal para girişi / toplanma emaresi var.")
            else:
                st.warning(f"Tahtacı Skoru düşük ({score:.1f}/100). Hissede an itibariyle ciddi bir kurumsal para girişi veya toplanma görünmüyor.")
            
            with st.expander("🔍 AKD ve Takas Ham Verilerini İncele (T1, T2)"):
                from database import query_df
                akd_df = query_df("SELECT tarih, kurum_adi, net_lot, avg_price FROM akd_data WHERE hisse = ? ORDER BY tarih DESC LIMIT 10", params=(h,), db_path=DB_PATH)
                takas_df = query_df("SELECT tarih, kurum_adi, saklama_adet, saklama_orani FROM takas_data WHERE hisse = ? ORDER BY tarih DESC LIMIT 10", params=(h,), db_path=DB_PATH)
                
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Günlük AKD (Alanlar/Satanlar)**")
                    st.dataframe(akd_df, use_container_width=True)
                with c2:
                    st.markdown("**Gün Sonu Takas (T1/T2)**")
                    st.dataframe(takas_df, use_container_width=True)
            
            with st.expander("🌊 Canlı Derinlik ve Spoofing Analizi (10 Kademe)"):
                from telegram_scraper import TelegramMiniAppScraper
                from depth_analyzer import analyze_depth_spoofing
                
                # Gerçek ortamda TelegramMiniAppScraper kullanılıyor
                try:
                    live_scraper = TelegramMiniAppScraper() 
                    derinlik_df = live_scraper.fetch_derinlik(h)
                    
                    if not derinlik_df.empty:
                        depth_analysis = analyze_depth_spoofing(derinlik_df)
                        
                        st.markdown(f"**Toplam Alış Lot:** {depth_analysis['total_bid']:,} | **Toplam Satış Lot:** {depth_analysis['total_ask']:,} | **Alış/Satış Oranı:** {depth_analysis['bid_ask_ratio']}")
                        
                        if depth_analysis['spoofing_detected']:
                            st.error(depth_analysis['warning_message'])
                        else:
                            st.success("🟢 Kademe dağılımı normal görünüyor. Korkutma (Spoofing) tespit edilmedi.")
                            
                        st.dataframe(derinlik_df, use_container_width=True)
                    else:
                        st.warning("Derinlik verisi alınamadı.")
                except Exception as e:
                    st.error(f"Derinlik analizinde hata: {e}")
            
            # --- TEKNIK GORUNUM (SMC & Destek/Direnc) ---
            st.markdown("### 📈 Teknik Görünüm & SMC (Destek/Direnç)")
            
            with st.expander("📊 Görsel Hacim Profili (POC Analizi)"):
                import plotly.graph_objects as go
                import yfinance as yf
                import pandas as pd
                import numpy as np
                
                try:
                    vp_df = yf.download(f"{h}.IS", period="3mo", interval="1d", progress=False)
                    if not vp_df.empty:
                        if isinstance(vp_df.columns, pd.MultiIndex):
                            vp_df.columns = vp_df.columns.get_level_values(0)
                        vp_df.columns = [col.lower() for col in vp_df.columns]
                        
                        vp_df = vp_df.dropna(subset=['close', 'volume'])
                        
                        min_price = vp_df['close'].min()
                        max_price = vp_df['close'].max()
                        bins = np.linspace(min_price, max_price, 20)
                        
                        vp_df['bin'] = np.digitize(vp_df['close'], bins)
                        vol_profile = vp_df.groupby('bin')['volume'].sum().reset_index()
                        bin_centers = 0.5 * (bins[1:] + bins[:-1])
                        
                        vol_profile['price'] = vol_profile['bin'].apply(lambda b: bin_centers[b-1] if 0 < b <= len(bin_centers) else max_price)
                        
                        poc_idx = vol_profile['volume'].idxmax()
                        poc_price = vol_profile.loc[poc_idx, 'price']
                        
                        fig2 = go.Figure(go.Bar(
                            x=vol_profile['volume'],
                            y=vol_profile['price'],
                            orientation='h',
                            marker_color='rgba(50, 171, 96, 0.6)',
                            name='Hacim Dağılımı'
                        ))
                        
                        fig2.add_hline(y=poc_price, line_dash="dash", line_color="red", annotation_text=f"POC (Maliyet): {poc_price:.2f}")
                        
                        fig2.update_layout(
                            title=f"{h} - Son 3 Aylık Hacim Profili (Volume Profile)",
                            yaxis_title="Fiyat Seviyeleri",
                            xaxis_title="Toplam Hacim",
                            height=400,
                            margin=dict(l=20, r=20, t=40, b=20)
                        )
                        
                        st.plotly_chart(fig2, use_container_width=True)
                        st.info(f"**POC (Point of Control):** {poc_price:.2f} TL. En çok hacmin döndüğü seviyedir. Fiyat bu seviyenin üstündeyse destek, altındaysa güçlü direnç olarak çalışır.")
                    else:
                        st.warning("Hacim profili için fiyat verisi bulunamadı.")
                except Exception as e:
                    st.error(f"Hacim profili oluşturulurken hata: {e}")
                    
            is_downtrend = tahtaci_details.get("is_downtrend", False)
            is_overextended = tahtaci_details.get("is_overextended", False)
            runup_pct = tahtaci_details.get("runup_pct", 0.0)
            
            if exit_sig:
                st.error("🚨 **Çıkış Modu:** Trend kırılımı (EMA21 altı) var. Mevcut pozisyonlar için stop-loss (zarar kes) seviyeleri kesinlikle işletilmelidir. Dağıtım ihtimali masada.")
            elif is_downtrend:
                st.error("💀 **DÜŞEN BIÇAK (Tehlikeli Düşüş Trendi):** Hisse son 6 aylık zirvesinden %30'dan fazla düşmüş durumda. AKD'de para girişi görülse de, yukarıdaki hacim blokları Tahtacı maliyetlenmesi değil, geçmişte yatırımcıya malın yıkıldığı **'Mezarlık Direnci'** bölgesidir. Düşüş bitip dirençler kırılmadan (sadece ucuz diye) alım yapmak çok risklidir.")
            elif is_overextended:
                st.warning(f"🚀 **AŞIRI FİYATLANMA (Tren Kaçmış Olabilir):** Bu hisse son 6 aylık dibinden **%{runup_pct:.1f}** oranında prim yapmış durumda! Tahtacı hala mal tutuyor veya sürüyor olabilir ancak bu seviyelerden yeni alım yapmak 'Tepeden Mal Kitlenme' (FOMO) riski taşır. Güvenli Pusu mantığına aykırıdır.")
            elif score >= 50 and entries:
                st.success("🟢 **Aksiyon Modu:** Tahtacının mal toplaması fiyata olumlu yansımaya başladı ve teknik onay (direnç kırılımı) geldi. Kademeli alım düşünülebilir. Trende katılmak için uygun bir zemin var.")
            elif score >= 50 and not entries:
                nearest = trap.details.get("nearest_support", 0.0) if trap else 0.0
                last_close_val = r.get("last_close")
                if not last_close_val and trap:
                    last_close_val = trap.details.get("last_close")
                if not last_close_val or last_close_val == 0:
                    last_close_val = 1.0
                
                if nearest > 0 and nearest < last_close_val:
                    drop_pct = ((last_close_val - nearest) / last_close_val) * 100
                    st.info(f"🟡 **Pusu Modu (Ayı Tuzağı Beklentisi):** Gerçek verilere göre para girişi var ancak yükseliş henüz başlamamış. Tahtacının silkeleme yapma ihtimaline karşı pusuya yatın. Beklenen teknik destek: **{nearest:.2f} TL** (Mevcut fiyattan **%{drop_pct:.1f}** aşağıda). Bu destek altına inilirse SMC Sniper kovalayın.")
                elif trap and hasattr(trap, 'poc_level') and trap.poc_level > last_close_val:
                    poc_val = f"{trap.poc_level:.2f}"
                    dist_pct = ((trap.poc_level - last_close_val) / last_close_val) * 100
                    st.info(f"🟡 **Pusu Modu (Direnç Kırılımı Beklentisi):** Gerçek verilere göre para girişi var ancak fiyat ana direnç bölgesinin altında. Fiyatın **{poc_val} TL** direncini (mevcut fiyattan **%{dist_pct:.1f}** yukarıda) hacimli kırmasını bekleyin.")
                else:
                    st.info("🟡 **Pusu Modu:** Teknik onay veya kırılım bekleniyor.")
            elif score < 50 and trap and trap.squeeze_active:
                st.info("🟠 **Sıkışma Modu:** Hissede Bollinger daralması (Squeeze) var ancak henüz para giriş yönü net değil. Sert bir teknik hareket kapıda, patlama yönü beklenmeli.")
            else:
                st.write("⚪ **Nötr Mod:** Özel bir teknik formasyon görünmüyor.")
            
            # Haber Akışı (Sentiment Analizi)
            with st.expander("📰 Haber, KAP ve Dedikodu Radarı (Sentiment Analizi)"):
                from news_engine import fetch_news_sentiment, fetch_news_headlines_only
                
                # AKILLI MOD SEÇİMİ:
                # "Belirli Hisseler" → Claude derin analiz (API çağrısı)
                # Diğer (BIST30/100/TÜM) → Hafif mod (sadece başlıklar, Claude yok)
                is_specific = st.session_state.get('analiz_modu_spesifik', False)
                
                if is_specific:
                    news_data = fetch_news_sentiment(h)  # Claude ile derin analiz
                else:
                    news_data = fetch_news_headlines_only(h)  # Sadece başlıklar, maliyet yok
                
                sentiment = news_data["sentiment"]
                s_score = news_data["sentiment_score"]
                count = news_data["news_count"]
                highlight = news_data["highlight"]
                mode = news_data.get("mode", "unknown")
                
                # Mod göstergesi
                if mode == "deep":
                    st.caption("🧠 **Claude YZ Derin Analiz** — Tahtacı perspektifinden analiz edildi")
                elif mode == "cached":
                    st.caption("⚡ **Önbellek** — Daha önce yapılan Claude analizi (API tasarrufu)")
                elif mode == "light":
                    st.caption("💡 **Hafif Mod** — Sadece haber başlıkları (Claude kullanılmadı, maliyet: $0)")
                
                st.markdown(f"**Son 24 Saatte Taranan Haber/KAP Sayısı:** {count}")
                st.markdown(f"**Öne Çıkan Başlık:** _{highlight}_")
                
                if sentiment == "POSITIVE":
                    st.success(f"🟢 **POZİTİF HABER AKIŞI (Skor: +{s_score})**\nTahtacının toplama hareketi bu olumlu gelişmelerle destekleniyor olabilir.")
                elif sentiment == "NEGATIVE":
                    st.error(f"🔴 **NEGATİF HABER AKIŞI (Skor: {s_score})**\nDikkat! Tahtacı fiyatı düşürmek için kötü haberi kullanıyor olabilir veya mal çıkışı yapılıyordur.")
                else:
                    st.info(f"⚪ **NÖTR HABER AKIŞI (Skor: {s_score})**\nFiyatı doğrudan etkileyecek sert bir haber akışı yok.")
                
                # Hafif moddaysa kullanıcıya Claude ile derin analiz seçeneği sun
                if mode == "light":
                    st.markdown("---")
                    if st.button(f"🧠 Claude ile Derin Analiz Yap ({h})", key=f"deep_{h}"):
                        deep_data = fetch_news_sentiment(h, force_deep=True)
                        st.markdown(f"**🧠 Claude Analizi:** _{deep_data['highlight']}_")
                        if deep_data["sentiment"] == "POSITIVE":
                            st.success(f"🟢 Claude: POZİTİF (+{deep_data['sentiment_score']})")
                        elif deep_data["sentiment"] == "NEGATIVE":
                            st.error(f"🔴 Claude: NEGATİF ({deep_data['sentiment_score']})")
                        else:
                            st.info(f"⚪ Claude: NÖTR ({deep_data['sentiment_score']})")
                
                st.markdown("---")
                st.write("Daha fazlası için:")
                st.markdown(f"- 🔎 **[Google Haberler'de {h} Ara](https://news.google.com/search?q={h}%20hisse&hl=tr&gl=TR&ceid=TR%3Atr)**")
                st.markdown(f"- 🏛️ **[KAP Bildirimleri](https://www.kap.org.tr/tr/arama/guncel-bildirimler?keyword={h})**")
            
            # Kümeler ve Koridorlar
            clusters = tahtaci_details.get("clusters", {})
            corridors = tahtaci_details.get("corridors", pd.DataFrame())
            
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                st.markdown("##### 👥 Tespit Edilen Kümeler")
                if clusters:
                    for cid, members in clusters.items():
                        safe_members = [m.replace('ı','i').replace('ş','s').replace('ğ','g').replace('ü','u').replace('ö','o').replace('ç','c').replace('İ','I').replace('Ş','S').replace('Ğ','G').replace('Ü','U').replace('Ö','O').replace('Ç','C') for m in members]
                        st.write(f"**Küme {cid}:** {', '.join(safe_members)}")
                else:
                    st.warning("⚠️ Takas (T+2) verisi eksik olduğu için kümeler hesaplanamadı. Lütfen veritabanını güncelleyiniz.")
            
            with c_col2:
                st.markdown("##### 🔄 Virman Koridorları (T+2)")
                if not corridors.empty:
                    for _, row in corridors.head(5).iterrows():
                        gonderici = str(row['gonderici']).replace('ı','i').replace('ş','s').replace('ğ','g').replace('ü','u').replace('ö','o').replace('ç','c').replace('İ','I').replace('Ş','S').replace('Ğ','G').replace('Ü','U').replace('Ö','O').replace('Ç','C')
                        alici = str(row['alici']).replace('ı','i').replace('ş','s').replace('ğ','g').replace('ü','u').replace('ö','o').replace('ç','c').replace('İ','I').replace('Ş','S').replace('Ğ','G').replace('Ü','U').replace('Ö','O').replace('Ç','C')
                        
                        gonderici_kasa = row.get('gonderici_kasa', 0)
                        alici_kasa = row.get('alici_kasa', 0)
                        
                        st.write(f"🛫 **{gonderici}** ({gonderici_kasa:,.0f} L) ➔ 🛬 **{alici}** ({alici_kasa:,.0f} L)")
                        st.caption(f"↳ Tahmini Transfer: {row['ort_transfer']:,.0f} Lot | %{row['olasilik']:.0f} Güven")
                else:
                    st.warning("⚠️ Takas verisi eksik veya yetersiz olduğu için virman koridoru çıkarılamadı.")
                    
            # --- AKSİYON PLANI VE GİRİŞ STRATEJİSİ ---
            st.markdown("---")
            st.markdown("#### 🎯 Aksiyon Planı & Giriş Stratejisi")
            
            is_downtrend = tahtaci_details.get("is_downtrend", False)
            is_overextended = tahtaci_details.get("is_overextended", False)
            trap = tahtaci_details.get("trap_analysis")
            t_score = tahtaci_details.get("tahtaci_score", 0)
            
            if trap:
                last_close = trap.details.get("last_close", 0.0)
                poc = trap.poc_level
                support = trap.details.get("nearest_support", 0.0)
                
                if is_downtrend or is_overextended:
                    st.error("🛑 **KARAR: UZAK DUR / İZLEMEDE KAL**")
                    st.write("Hisse sert bir düşüş trendinde (Düşen Bıçak) veya dipten çok fazla primlenmiş durumda. Herhangi bir alım yapılması çok risklidir.")
                elif trap.poc_breakout and trap.bear_trap_detected:
                    st.success("🟢 **KARAR: HEMEN AL (SMC Sinyali Onaylandı)**")
                    st.write(f"**Giriş Bölgesi:** {last_close:.2f} ₺ ile {poc:.2f} ₺ (POC) aralığı.")
                    st.write(f"**Stop-Loss (Zarar Kes):** {(support * 0.98):.2f} ₺ (Desteğin %2 altı)")
                    st.write(f"**Tahmini Hedef:** {(last_close * 1.15):.2f} ₺ (Minimum %15 Kar Marjı)")
                elif t_score >= 60 and not trap.poc_breakout:
                    st.warning("🟡 **KARAR: PUSUYA YAT (Geri Çekilme Bekle)**")
                    st.write("Tahtacı topluyor ancak henüz fiyat kırılımı yaşanmamış. Güvenli giriş için fiyatın hacim düğümüne (POC) veya desteğe sarkmasını bekleyin.")
                    if support > 0 and poc > 0:
                        st.write(f"**Pusu (Giriş) Bölgesi:** {support:.2f} ₺ ile {poc:.2f} ₺ arası kademeli alım.")
                        st.write(f"**Stop-Loss (Zarar Kes):** {(support * 0.97):.2f} ₺ (Desteğin %3 altı)")
                        st.write(f"**Tahmini Hedef:** {(poc * 1.15):.2f} ₺")
                    else:
                        st.write("Yeterli destek veya POC verisi oluşmamış.")
                elif t_score < 60:
                    st.info("⚪ **KARAR: İLGİ YOK (Başka Hisse Ara)**")
                    st.write("Tahtacı aktivitesi zayıf. Şu an için bir aksiyon alınması önerilmez.")
                else:
                    st.info("⚪ **KARAR: İZLEMEDE KAL**")
            else:
                st.info("Aksiyon planı oluşturulabilmesi için Tuzak Savar verisi eksik.")

            # ═══════════════════════════════════════════
            # 🧠 FİNANS AJANI (Claude Tam Kapsamlı Rapor)
            # ═══════════════════════════════════════════
            st.markdown("---")
            if st.button(f"🧠 Finans Ajanı Raporu Al ({h})", key=f"ajan_{h}", type="primary"):
                with st.spinner("🧠 SNAKE EYE Finans Ajanı tüm verileri analiz ediyor..."):
                    from finans_ajani import generate_ajan_report
                    from database import query_df
                    
                    # Trap özeti hazırla
                    trap_obj = r.get("trap_analysis")
                    trap_summary = "Tuzak verisi yok"
                    if trap_obj:
                        trap_summary = f"Squeeze: {'Aktif' if trap_obj.squeeze_active else 'Yok'} | Bear Trap: {'Var' if trap_obj.bear_trap_detected else 'Yok'} | POC: {trap_obj.poc_level:.2f} | POC Kırılım: {'Evet' if trap_obj.poc_breakout else 'Hayır'} | Tuzak Skoru: {trap_obj.trap_score:.1f}"
                    
                    # Koridor text
                    corr_df = tahtaci_details.get("corridors", pd.DataFrame())
                    corr_text = ""
                    if not corr_df.empty:
                        for _, row in corr_df.head(5).iterrows():
                            corr_text += f"{row['gonderici']} → {row['alici']} ({row['ort_transfer']:,.0f} Lot, %{row['olasilik']:.0f} güven)\n"
                    
                    # AKD özeti
                    akd_df = query_df("SELECT tarih, kurum_adi, net_lot FROM akd_data WHERE hisse = ? ORDER BY tarih DESC LIMIT 15", params=(h,), db_path=DB_PATH)
                    akd_text = ""
                    if not akd_df.empty:
                        for _, row in akd_df.iterrows():
                            direction = "ALIŞ" if row['net_lot'] > 0 else "SATIŞ"
                            akd_text += f"{row['tarih']} | {row['kurum_adi']}: {row['net_lot']:+,.0f} lot ({direction})\n"
                    
                    # Takas özeti
                    takas_df = query_df("SELECT tarih, kurum_adi, saklama_adet, saklama_orani FROM takas_data WHERE hisse = ? ORDER BY tarih DESC LIMIT 10", params=(h,), db_path=DB_PATH)
                    takas_text = ""
                    if not takas_df.empty:
                        for _, row in takas_df.iterrows():
                            takas_text += f"{row['tarih']} | {row['kurum_adi']}: {row['saklama_adet']:,.0f} adet (%{row['saklama_orani']:.2f})\n"
                    
                    # Haber başlıkları
                    from news_engine import fetch_news_headlines_only
                    news = fetch_news_headlines_only(h)
                    news_text = news.get("highlight", "")
                    
                    # Sosyal Medya Radarı
                    from social_radar import get_social_summary
                    social_data = get_social_summary(h)
                    social_text = social_data["summary_text"]
                    
                    # Rapor üret
                    report = generate_ajan_report(
                        hisse=h,
                        tahtaci_score=score,
                        sub_scores=sub,
                        clusters=tahtaci_details.get("clusters", {}),
                        corridors_text=corr_text,
                        trap_summary=trap_summary,
                        entry_signals=r.get("entry_signals", []),
                        exit_signal=r.get("exit_signal", False),
                        last_close=r.get("last_close", 0.0),
                        top_buyer=tahtaci_details.get("top_buyer_name", "Bilinmiyor"),
                        top_buyer_type=tahtaci_details.get("top_buyer_type", "Nötr"),
                        news_headlines=news_text,
                        akd_summary=akd_text,
                        takas_summary=takas_text,
                        social_summary=social_text,
                    )
                
                # Raporu göster
                mode = report.get("mode", "")
                if mode == "cached":
                    st.caption("⚡ Önbellek — Önceki analiz gösteriliyor (API tasarrufu)")
                elif mode == "ajan":
                    st.caption("🧠 Claude Finans Ajanı — Canlı analiz")
                
                aksiyon = report["aksiyon"]
                guven = report["guven"]
                
                # Aksiyon renk kodlaması
                if aksiyon == "AL":
                    st.success(f"### 🟢 FİNANS AJANI KARARI: **{aksiyon}** (Güven: %{guven})")
                elif aksiyon == "SAT" or aksiyon == "UZAK DUR":
                    st.error(f"### 🔴 FİNANS AJANI KARARI: **{aksiyon}** (Güven: %{guven})")
                elif aksiyon == "BEKLE":
                    st.warning(f"### 🟡 FİNANS AJANI KARARI: **{aksiyon}** (Güven: %{guven})")
                else:
                    st.info(f"### ⚪ FİNANS AJANI KARARI: **{aksiyon}** (Güven: %{guven})")
                
                # Sosyal Medya Radarı UI Gösterimi
                s_col1, s_col2 = st.columns([1, 2])
                with s_col1:
                    status = social_data["telegram"]["status"]
                    if "SESSİZ" in status:
                        st.info(f"📱 Sosyal Radar: **{status}**")
                    elif "AŞIRI" in status:
                        st.error(f"📱 Sosyal Radar: **{status}**")
                    else:
                        st.warning(f"📱 Sosyal Radar: **{status}**")
                with s_col2:
                    st.markdown(f"[🔍 X (Twitter)'da '{h}' Canlı Akışını Gör]({social_data['x_url']})")
                
                st.markdown(f"📝 **Rapor:** {report['rapor']}")
                
                aj_c1, aj_c2, aj_c3 = st.columns(3)
                aj_c1.metric("🎯 Hedef Fiyat", report["hedef_fiyat"])
                aj_c2.metric("🛑 Stop-Loss", report["stop_loss"])
                aj_c3.metric("⚠️ Risk", report["risk_notu"][:30])
                
                if report["risk_notu"]:
                    st.warning(f"⚠️ **Risk Notu:** {report['risk_notu']}")

    # ── PORTFÖY YÖNETİMİ ──
with tab_portfoy:
    st.header("💼 Fon ve Portföy Yönetimi")
    st.markdown("Tahtacı ile birlikte girdiğiniz hisseleri burada takip edin. Sistem, **enflasyondan arındırılmış %100 hedefine** ulaşıldığında 'Ana Parayı Çık' uyarısı verecektir.")
    
    from portfolio_engine import add_position, get_active_positions, close_position, calculate_inflation_adjusted_target
    import yfinance as yf
    
    col_add1, col_add2, col_add3, col_add4, col_add5 = st.columns(5)
    with col_add1:
        yeni_hisse = st.text_input("Hisse", placeholder="Örn: THYAO")
    with col_add2:
        yeni_maliyet = st.number_input("Maliyet", min_value=0.0, step=0.1)
    with col_add3:
        yeni_lot = st.number_input("Lot Miktarı", min_value=1, step=1)
    with col_add4:
        yeni_hedef = st.number_input("2X Hedefi", min_value=0.0, step=0.1, help="İsteğe bağlı")
    with col_add5:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Pozisyon Ekle", use_container_width=True):
            if yeni_hisse and yeni_maliyet > 0:
                h_hedef = yeni_hedef if yeni_hedef > 0 else (yeni_maliyet * 2.0)
                if add_position(yeni_hisse.upper(), yeni_maliyet, yeni_lot, h_hedef):
                    st.success("Pozisyon Eklendi!")
                    st.rerun()
    
    st.divider()
    st.subheader("📈 Aktif Pozisyonlar")
    
    df_portfoy = get_active_positions()
    
    if df_portfoy.empty:
        st.info("Henüz eklenmiş aktif bir pozisyonunuz yok.")
    else:
        for idx, row in df_portfoy.iterrows():
            pos_id = row['id']
            h = row['hisse']
            maliyet = row['alis_fiyati']
            lot = row['lot_miktari']
            alis_tarihi = row['alis_tarihi']
            
            # Anlık fiyatı yfinance ile çek
            try:
                ticker = yf.Ticker(f"{h}.IS")
                current_price = ticker.fast_info.last_price
            except:
                current_price = maliyet # Hata olursa maliyet göster
            
            # Gün hesaplama
            alis_dt = pd.to_datetime(alis_tarihi)
            gun_farki = (pd.Timestamp.now() - alis_dt).days
            ay_farki = max(1, gun_farki // 30)
            
            # Enflasyon Hedefi Hesaplama
            hedef_analiz = calculate_inflation_adjusted_target(maliyet, current_price, ay_farki, aylik_enflasyon=3.0)
            istenen_ana_para = hedef_analiz['istenen_ana_para_hedefi']
            satilacak_oran = hedef_analiz['satilmasi_gereken_oran']
            
            guncel_deger = current_price * lot
            yatirilan_para = maliyet * lot
            kar_zarar = guncel_deger - yatirilan_para
            kar_yuzde = (kar_zarar / yatirilan_para) * 100 if yatirilan_para > 0 else 0
            
            with st.expander(f"📦 {h} | Kâr: %{kar_yuzde:.1f} | Güncel Değer: {guncel_deger:,.0f} TL", expanded=True):
                p_col1, p_col2, p_col3, p_col4 = st.columns(4)
                p_col1.metric("Maliyet", f"{maliyet:.2f} TL")
                p_col2.metric("Anlık Fiyat", f"{current_price:.2f} TL", f"%{kar_yuzde:.1f}")
                p_col3.metric("Lot", f"{lot}")
                p_col4.metric("Kâr/Zarar", f"{kar_zarar:,.0f} TL")
                
                st.write(f"**Alış Tarihi:** {alis_tarihi} ({gun_farki} gün önce) | **Enflasyon (%3/ay) Düzeltilmiş Ana Para Değeri:** {istenen_ana_para:,.2f} TL")
                
                if current_price >= hedef_analiz['hedef_2x']:
                    st.success(f"🎉 **HEDEF GELDİ!** Hisse 2X yaptı. Ana paranızı (enflasyon düzeltmeli) kurtarmak için portföyün **%{satilacak_oran*100:.0f}** kısmını satın, kalanı bedava (kâr) lot olarak bırakın!")
                elif current_price > maliyet:
                    st.info(f"⏳ Yükseliş trendinde. Hedefe kalan: %{((hedef_analiz['hedef_2x'] - current_price) / current_price)*100:.1f}")
                else:
                    st.warning("Tahtacı henüz düğmeye basmadı veya maliyet altındayız. Pusuya devam.")
                
                if st.button(f"Kapat / Satış Ver ({h})", key=f"close_{pos_id}"):
                    close_position(pos_id)
                    st.rerun()

    # ── SEKTÖR ISI HARİTASI ──
with tab_sektor:
    st.header("🗺️ Sektörel Para Akışı ve Isı Haritası")
    st.markdown("Akıllı paranın (tahtacıların) hangi sektörlerde birikim yaptığını gösterir.")
    
    if st.button("🔄 Isı Haritasını Güncelle", type="primary"):
        with st.spinner("Sektörel veriler analiz ediliyor..."):
            from sector_analyzer import analyze_sectoral_money_flow
            sec_df = analyze_sectoral_money_flow()
            
            if not sec_df.empty:
                st.dataframe(
                    sec_df,
                    column_config={
                        "sektor": "Sektör",
                        "toplam_net_lot_girisi": st.column_config.NumberColumn("Net Lot Girişi (Hacim)", format="%,d"),
                        "hisse_sayisi": "Taranan Hisse",
                        "yogunluk_skoru": st.column_config.NumberColumn("Yoğunluk", format="%.2f"),
                        "isi_derecesi": st.column_config.ProgressColumn(
                            "Isı Derecesi (Sıcaklık)",
                            help="Sektördeki kurumsal alım yoğunluğu",
                            format="%.1f%%",
                            min_value=0,
                            max_value=100,
                        ),
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                en_sicak = sec_df.iloc[0]['sektor']
                st.success(f"🔥 **Günün En Sıcak Sektörü:** {en_sicak}. Kurumsal para şu an bu sektördeki hisselere giriyor.")
            else:
                st.warning("Yeterli veri bulunamadı. Lütfen veritabanını güncelleyin.")

    # ── BACKTEST MOTORU ──
with tab_backtest:
    st.header("🔄 Backtest Motoru")
    st.markdown("Sistemin geçmişteki 'Tahtacı' tespitlerini sanal olarak test edip başarı oranını ölçer.")
    
    b_col1, b_col2 = st.columns([1, 3])
    with b_col1:
        min_skor = st.slider("Minimum Tahtacı Skoru (Alış Koşulu)", 50, 95, 70)
        bekleme_suresi = st.slider("Elde Tutma Süresi (Gün)", 5, 60, 15)
        btn_backtest = st.button("🚀 Backtest'i Başlat", type="primary", use_container_width=True)
        
    with b_col2:
        if btn_backtest:
            with st.spinner("Geçmiş veriler üzerinden simülasyon çalıştırılıyor..."):
                from backtester import run_backtest
                res = run_backtest(min_score=min_skor, holding_period_days=bekleme_suresi)
                
                if "error" in res:
                    st.error(res["error"])
                elif res.get("toplam_islem", 0) == 0:
                    st.warning("Belirtilen kriterlere ve tutma süresine uyan geçmiş işlem bulunamadı.")
                else:
                    st.success(f"✅ **Backtest Tamamlandı!** Toplam {res['toplam_islem']} sanal işlem yapıldı.")
                    
                    r_c1, r_c2, r_c3, r_c4 = st.columns(4)
                    r_c1.metric("Kazanma Oranı (Win Rate)", f"%{res['win_rate']:.1f}")
                    r_c2.metric("Ortalama Getiri", f"%{res['ortalama_getiri']:.1f}")
                    r_c3.metric("Maks Kazanç", f"%{res['max_kazanc']:.1f}")
                    r_c4.metric("Maks Kayıp", f"%{res['max_kayip']:.1f}")
                    
                    st.markdown("### 📝 İşlem Detayları")
                    st.dataframe(pd.DataFrame(res["detaylar"]), use_container_width=True)

    # ── YABANCI TAKAS AVCISI ──
with tab_yabanci:
    st.header("🌍 Yabancı Takas Avcısı (Bıyıklı Avı)")
    st.markdown("Son günlerde Citi ve Deutsche takasında belirgin oranda (sürekli) artış olan hisseleri listeler.")
    
    y_gun = st.slider("Kaç Günlük Değişime Bakılsın?", 1, 30, 7)
    if st.button("🌍 Yabancı Takasını Tara", type="primary"):
        with st.spinner(f"Son {y_gun} gün için Yabancı Takası taranıyor..."):
            from database import get_foreign_accumulation
            yabanci_df = get_foreign_accumulation(days=y_gun, db_path=DB_PATH)
            
            if not yabanci_df.empty:
                st.success(f"✅ {len(yabanci_df)} farklı hissede Yabancı alımı tespit edildi.")
                st.dataframe(
                    yabanci_df,
                    column_config={
                        "hisse": "Hisse",
                        "kurum_adi": "Yabancı Kurum",
                        "baslangic_lot": st.column_config.NumberColumn("Başlangıç Lot", format="%,d"),
                        "bitis_lot": st.column_config.NumberColumn("Güncel Lot", format="%,d"),
                        "lot_degisim": st.column_config.NumberColumn("Net Lot Artışı", format="+%,d"),
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.warning("Belirtilen süre zarfında net Yabancı alımı olan hisse bulunamadı.")

    # ── SEKTÖREL PARA AKIŞI ──
with tab_para_akisi:
    st.header("💸 Sektörel Para Akışı Radarı")
    st.markdown("Bugün en çok hangi sektöre para girdiğini / çıktığını AKD (Aracı Kurum Dağılımı) tutarları üzerinden hesaplar.")
    
    if st.button("💸 Para Akışını Hesapla", type="primary"):
        with st.spinner("Tüm hisselerin günlük AKD verileri toplanıyor..."):
            from database import get_sectoral_money_flow
            flow_df = get_sectoral_money_flow(db_path=DB_PATH)
            
            if not flow_df.empty:
                st.success("✅ Günlük Sektörel Para Akışı (Temsili İlk Harf Gruplaması) hesaplandı.")
                st.bar_chart(flow_df.set_index("pseudo_sektor")["net_para_girisi"])
                st.dataframe(flow_df, hide_index=True, use_container_width=True)
            else:
                st.warning("AKD verisi bulunamadı.")

# ── CLAUDE API KULLANIM İSTATİSTİKLERİ (Sidebar Alt Kısım) ──
st.sidebar.markdown("---")
with st.sidebar.expander("🧠 Claude API Kullanımı"):
    from news_engine import get_api_stats
    from finans_ajani import get_ajan_stats
    
    news_stats = get_api_stats()
    ajan_stats = get_ajan_stats()
    
    total_calls = news_stats["api_calls"] + ajan_stats["calls"]
    total_tokens = news_stats["total_tokens"] + ajan_stats["tokens"]
    total_cost = news_stats["estimated_cost_usd"] + ajan_stats["cost"]
    
    st.metric("Toplam API Çağrısı", total_calls)
    
    ac1, ac2 = st.columns(2)
    ac1.metric("📰 Haber Analizi", news_stats["api_calls"])
    ac2.metric("🧠 Finans Ajanı", ajan_stats["calls"])
    
    st.metric("Toplam Token", f"{total_tokens:,}")
    st.metric("Tahmini Maliyet", f"${total_cost:.4f}")
    
    is_spesifik = st.session_state.get('analiz_modu_spesifik', False)
    if is_spesifik:
        st.success("🧠 **Derin Mod Aktif** — Claude otomatik haber analizi")
    else:
        st.info("💡 **Hafif Mod** — Claude sadece butonla çağrılır")
    
    st.caption("💰 $5 bütçe ≈ 300+ Finans Ajanı raporu veya 500+ haber analizi")
