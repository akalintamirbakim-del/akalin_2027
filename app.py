import pandas as pd
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Akalın Kamyon Tamir İş Takip", page_icon="🚛", layout="wide")

# BURAYA GOOGLE E-TABLO LINKINIZI YAPIŞTIRIN:
# Linkin sonundaki /edit... kısmını silip /export?format=csv ekliyoruz
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1nzBlypm7zDG7o2UE_35VrKVZvZzmFSbo5ua4b4eEYq0/edit?usp=sharing"

# --- ŞİFRE KONTROLÜ ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "1234":  # İstediğiniz şifreyi buraya yazabilirsiniz
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.subheader("🔒 Lütfen Giriş Şifresini Girin")
        st.text_input("Şifre", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Şifre", type="password", on_change=password_entered, key="password")
        st.error("😕 Şifre yanlış. Lütfen tekrar deneyin.")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- GOOGLE E-TABLODAN VERİ OKUMA ---
@st.cache_data(ttl=5) # 5 saniyede bir veriyi tazeler
def load_data():
    try:
        df = pd.read_csv(SPREADSHEET_URL)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Google E-Tablo'dan veri okunamadı: {e}")
        return pd.DataFrame(columns=['Müşteri', 'Marka/Model', 'Plaka', 'Yapılan İşlem', 'Ücret', 'Alınan', 'Kalan', 'Tarih', 'İş Tipi'])

df = load_data()

st.sidebar.title("🚛 Akalın Servis")
menu = st.sidebar.radio("Menü", ["📊 Özet Panel", "📋 İş Listesi & Arama", "💰 Müşteri Borçları"])

if menu == "📊 Özet Panel":
    st.title("📊 Tamirhane Yönetim Paneli")
    
    total_is = len(df)
    total_ciro = df['Ücret'].sum() if 'Ücret' in df.columns else 0
    total_alinan = df['Alınan'].sum() if 'Alınan' in df.columns else 0
    total_kalan = df['Kalan'].sum() if 'Kalan' in df.columns else 0
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Toplam İş / Araç", f"{total_is}")
    col2.metric("Toplam Ciro", f"{total_ciro:,.2f} ₺")
    col3.metric("Tahsil Edilen", f"{total_alinan:,.2f} ₺")
    col4.metric("Kalan Alacak (Borç)", f"{total_kalan:,.2f} ₺")
    
    st.markdown("---")
    st.subheader("Son Eklenen İşler")
    st.dataframe(df.tail(10), use_container_width=True)

elif menu == "📋 İş Listesi & Arama":
    st.title("📋 İş Geçmişi ve Arama")
    search_term = st.text_input("🔍 Müşteri, Plaka veya İşlem Ara:", "")
    
    filtered_df = df
    if search_term:
        mask = df.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
        filtered_df = df[mask]
        
    st.dataframe(filtered_df, use_container_width=True)

elif menu == "💰 Müşteri Borçları":
    st.title("💰 Müşteri Borç Listesi")
    if 'Müşteri' in df.columns and 'Kalan' in df.columns:
        borc_df = df.groupby('Müşteri')[['Ücret', 'Alınan', 'Kalan']].sum().reset_index()
        borc_df = borc_df[borc_df['Kalan'] > 0].sort_values(by='Kalan', ascending=False)
        st.dataframe(borc_df, use_container_width=True)
