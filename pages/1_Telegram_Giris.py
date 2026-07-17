import streamlit as st
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

st.set_page_config(page_title="Telegram Giriş", page_icon="🔐")

st.title("🔐 Telegram Bulut Doğrulaması")
st.write("Sistemin arka planda çalışabilmesi için Telegram'a bulut üzerinden bir kez giriş yapmalısınız.")

API_ID = 31078357
API_HASH = "0fd6f44418f0aa9ed74f2957f2f33e06"

if 'session_string' not in st.session_state:
    st.session_state.session_string = ""

if 'phone_sent' not in st.session_state:
    st.session_state.phone_sent = False

if 'phone_hash' not in st.session_state:
    st.session_state.phone_hash = ""

if 'phone' not in st.session_state:
    st.session_state.phone = ""

async def send_code(phone_num):
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    result = await client.send_code_request(phone_num)
    st.session_state.session_string = client.session.save()
    st.session_state.phone_hash = result.phone_code_hash
    st.session_state.phone = phone_num
    st.session_state.phone_sent = True
    await client.disconnect()

async def verify_code(code_str):
    client = TelegramClient(StringSession(st.session_state.session_string), API_ID, API_HASH)
    await client.connect()
    await client.sign_in(phone=st.session_state.phone, code=code_str, phone_code_hash=st.session_state.phone_hash)
    final_session = client.session.save()
    await client.disconnect()
    return final_session

phone = st.text_input("Telefon Numaranız (Başında +90 ile)", placeholder="+905551234567", disabled=st.session_state.phone_sent)

if not st.session_state.phone_sent:
    if st.button("Kodu Gönder"):
        if phone:
            with st.spinner("Telegram'a bağlanılıyor..."):
                try:
                    asyncio.run(send_code(phone))
                    st.success("Kod Telegram uygulamanıza gönderildi!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")
else:
    code = st.text_input("Telegram'dan Gelen 5 Haneli Kod", type="password")
    if st.button("Giriş Yap ve Şifreyi Üret"):
        if code:
            with st.spinner("Doğrulanıyor..."):
                try:
                    final_session_str = asyncio.run(verify_code(code))
                    st.success("Giriş Başarılı! İşte yeni BULUT SİHİRLİ ŞİFRENİZ:")
                    st.code(final_session_str, language="toml")
                    st.warning("Yukarıdaki şifreyi kopyalayıp GitHub'daki TELEGRAM_STRING_SESSION sırrına ve Streamlit Advanced Settings'e yapıştırın!")
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")
    if st.button("Başa Dön / Tekrar Dene"):
        st.session_state.phone_sent = False
        st.rerun()
