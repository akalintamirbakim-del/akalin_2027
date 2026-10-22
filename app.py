import pandas as pd
import streamlit as st
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Akalın Kamyon Tamir İş Takip", page_icon="🚛", layout="wide")

# --- ŞİFRE KONTROLÜ ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "1234":
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

# --- GOOGLE E-TABLO BAĞLANTISI ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read(ttl=2)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Google E-Tablo'dan veri okunamadı: {e}")
        return pd.DataFrame()

df = load_data()

# Sütun adlarını akıllı bulma
def find_col(df, keywords):
    for col in df.columns:
        for kw in keywords:
            if kw.lower() in col.lower():
                return col
    return None

c_ucret = find_col(df, ['ücret', 'tutar', 'fiyat'])
c_alinan = find_col(df, ['alınan', 'ödenen', 'tahsil'])
c_kalan = find_col(df, ['kalan', 'borç', 'bakiye'])
c_musteri = find_col(df, ['müşteri', 'firma'])

# Türkçe para formatını sayıya çeviren akıllı fonksiyon (1.500,00 -> 1500.00)
def parse_money(series):
    if series is None or series.name not in df.columns:
        return pd.Series(0.0, index=df.index)
    
    s = df[series].astype(str)
    s = s.str.replace('₺', '', regex=False).str.replace('TL', '', regex=False).str.replace(' ', '', regex=False)
    # 1.234,56 formatını Python'un anlayacağı formata çevir
    s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0.0)

if not df.empty:
    df['Ucret_Clean'] = parse_money(c_ucret)
    df['Alinan_Clean'] = parse_money(c_alinan)
    df['Kalan_Clean'] = parse_money(c_kalan)

st.sidebar.title("🚛 Akalın Servis")
menu = st.sidebar.radio("Menü", ["📊 Özet Panel", "📋 İş Listesi & Arama", "➕ Yeni İş Ekle", "💰 Müşteri Borçları"])

if menu == "📊 Özet Panel":
    st.title("📊 Tamirhane Yönetim Paneli")
    
    if df.empty:
        st.warning("Google E-Tablonuz şu an boş veya veriler okunamadı.")
    else:
        total_is = len(df)
        total_ciro = df['Ucret_Clean'].sum()
        total_alinan = df['Alinan_Clean'].sum()
        total_kalan = df['Kalan_Clean'].sum()
        
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
    if search_term and not df.empty:
        mask = df.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
        filtered_df = df[mask]
        
    st.dataframe(filtered_df, use_container_width=True)

elif menu == "➕ Yeni İş Ekle":
    st.title("➕ Yeni Araç / İş Ekle")
    
    with st.form("yeni_is_formu"):
        col1, col2 = st.columns(2)
        with col1:
            musteri = st.text_input("Müşteri Adı / Firma")
            marka = st.text_input("Marka / Model")
            plaka = st.text_input("Plaka")
            is_tipi = st.selectbox("İş Tipi", ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"])
        with col2:
            tarih = st.date_input("İş Tarihi", datetime.now())
            ucret = st.number_input("Toplam Ücret (₺)", min_value=0.0, step=100.0)
            alinan = st.number_input("Alınan Ödenen (₺)", min_value=0.0, step=100.0)
            yapilan_islem = st.text_area("Yapılan İşlem / Değişen Parça")
            
        submit = st.form_submit_button("Kaydet ve Google E-Tabloya Gönder")
        
        if submit:
            kalan = ucret - alinan
            yeni_kayit = pd.DataFrame([{
                'Müşteri': musteri,
                'Marka/Model': marka,
                'Plaka': plaka,
                'Yapılan İşlem': yapilan_islem,
                'Ücret': ucret,
                'Alınan': alinan,
                'Kalan': kalan,
                'Tarih': tarih.strftime('%Y-%m-%d'),
                'İş Tipi': is_tipi
            }])
            
            guncel_df = pd.concat([df, yeni_kayit], ignore_index=True)
            # Temizlik için eklediğimiz geçici sütunları kayda göndermeden çıkar
            guncel_df = guncel_df.drop(columns=['Ucret_Clean', 'Alinan_Clean', 'Kalan_Clean'], errors='ignore')
            
            conn.update(data=guncel_df)
            st.success("İş başarıyla kaydedildi ve Google E-Tablo güncellendi!")
            st.cache_data.clear()

elif menu == "💰 Müşteri Borçları":
    st.title("💰 Müşteri Borç Listesi")
    if not df.empty and c_musteri:
        borc_df = df.groupby(c_musteri)[['Ucret_Clean', 'Alinan_Clean', 'Kalan_Clean']].sum().reset_index()
        borc_df.columns = ['Müşteri', 'Ücret', 'Alınan', 'Kalan']
        borc_df = borc_df[borc_df['Kalan'] > 0].sort_values(by='Kalan', ascending=False)
        st.dataframe(borc_df, use_container_width=True)
    else:
        st.info("Borç listesini gösterebilmek için müşteri sütunu bulunamadı.")
