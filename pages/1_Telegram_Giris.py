import streamlit as st
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

st.set_page_config(page_title="Telegram Giriş", page_icon="🔐")

st.title("🔐 Telegram Bulut Doğrulaması")
st.write("Sistemin arka planda çalışabilmesi için Telegram'a bulut üzerinden bir kez giriş yapmalısınız.")

API_ID = 31078357
API_HASH = "0fd6f44418f0aa9ed74f2957f2f33e06"

# A helper to run async Telethon functions
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

if 'client' not in st.session_state:
    st.session_state.client = TelegramClient(StringSession(), API_ID, API_HASH)

if 'phone_sent' not in st.session_state:
    st.session_state.phone_sent = False

if 'phone_hash' not in st.session_state:
    st.session_state.phone_hash = ""

phone = st.text_input("Telefon Numaranız (Başında +90 ile)", placeholder="+905551234567")

if st.button("Kodu Gönder"):
    if phone:
        with st.spinner("Telegram'a bağlanılıyor..."):
            run_async(st.session_state.client.connect())
            result = run_async(st.session_state.client.send_code_request(phone))
            st.session_state.phone_hash = result.phone_code_hash
            st.session_state.phone_sent = True
            st.session_state.phone = phone
            st.success("Kod Telegram uygulamanıza gönderildi!")
            st.rerun()

if st.session_state.phone_sent:
    code = st.text_input("Telegram'dan Gelen 5 Haneli Kod", type="password")
    if st.button("Giriş Yap ve Şifreyi Üret"):
        if code:
            with st.spinner("Doğrulanıyor..."):
                try:
                    run_async(st.session_state.client.connect())
                    run_async(st.session_state.client.sign_in(phone=st.session_state.phone, code=code, phone_code_hash=st.session_state.phone_hash))
                    session_string = st.session_state.client.session.save()
                    st.success("Giriş Başarılı! İşte yeni BULUT SİHİRLİ ŞİFRENİZ:")
                    st.code(session_string, language="toml")
                    st.warning("Yukarıdaki şifreyi kopyalayıp GitHub'daki TELEGRAM_STRING_SESSION sırrına ve Streamlit Advanced Settings'e yapıştırın!")
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")
