import pandas as pd
import streamlit as st
import requests
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

# --- GOOGLE E-TABLO BAĞLANTISI (OKUMA) ---
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

# Sütun isimlerini esnek yakalama
def find_col(df, keywords):
    for col in df.columns:
        for kw in keywords:
            if kw.lower() in col.lower():
                return col
    return None

c_musteri = find_col(df, ['müşteri', 'firma'])
c_marka = find_col(df, ['marka', 'model'])
c_plaka = find_col(df, ['plaka'])
c_ucret = find_col(df, ['ücret', 'tutar', 'fiyat'])
c_alinan = find_col(df, ['alınan', 'ödenen', 'tahsil'])
c_kalan = find_col(df, ['kalan', 'borç', 'bakiye'])

# Temiz para dönüştürücü
def parse_money(series_name):
    if not series_name or series_name not in df.columns:
        return pd.Series(0.0, index=df.index)
    s = df[series_name].astype(str)
    s = s.str.replace('₺', '', regex=False).str.replace('TL', '', regex=False).str.replace(' ', '', regex=False)
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
        st.info("Google E-Tablonuz şu an boş veya veriler yükleniyor...")
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
    
    known_records = []
    if not df.empty and c_musteri and c_plaka:
        records_df = df[[c_musteri, c_marka, c_plaka]].dropna().drop_duplicates()
        known_records = records_df.to_dict('records')
    
    select_options = ["-- Yeni Kayıt / Manuel Gir --"]
    for r in known_records:
        m_val = str(r.get(c_musteri, '')).strip()
        p_val = str(r.get(c_plaka, '')).strip()
        mk_val = str(r.get(c_marka, '')).strip()
        select_options.append(f"{p_val} | {m_val} ({mk_val})")

    selected_existing = st.selectbox("🚘 Kayıtlı Araç/Müşteri Seç (Otomatik Doldurur):", select_options)
    
    default_musteri = ""
    default_marka = ""
    default_plaka = ""
    
    if selected_existing != "-- Yeni Kayıt / Manuel Gir --":
        idx = select_options.index(selected_existing) - 1
        record = known_records[idx]
        default_musteri = str(record.get(c_musteri, ''))
        default_marka = str(record.get(c_marka, ''))
        default_plaka = str(record.get(c_plaka, ''))

    with st.form("yeni_is_formu"):
        col1, col2 = st.columns(2)
        with col1:
            plaka = st.text_input("Plaka", value=default_plaka)
            musteri = st.text_input("Müşteri Adı / Firma", value=default_musteri)
            marka = st.text_input("Marka / Model", value=default_marka)
            is_tipi = st.selectbox("İş Tipi", ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"])
        with col2:
            tarih = st.date_input("İş Tarihi", datetime.now())
            ucret = st.number_input("Toplam Ücret (₺)", min_value=0.0, step=100.0)
            alinan = st.number_input("Alınan Ödenen (₺)", min_value=0.0, step=100.0)
            yapilan_islem = st.text_area("Yapılan İşlem / Değişen Parça")
            
        submit = st.form_submit_button("Kaydet ve Google E-Tabloya Gönder")
        
        if submit:
            kalan = ucret - alinan
            payload = {
                "token": st.secrets["API_TOKEN"],
                "Musteri": musteri,
                "Marka": marka,
                "Plaka": plaka,
                "YapilanIslem": yapilan_islem,
                "Ucret": ucret,
                "Alinan": alinan,
                "Kalan": kalan,
                "Tarih": tarih.strftime('%Y-%m-%d'),
                "IsTipi": is_tipi
            }
            
            try:
                response = requests.post(st.secrets["WEB_APP_URL"], json=payload)
                res_data = response.json()
                if res_data.get("status") == "success":
                    st.success("İş başarıyla kaydedildi ve Google E-Tablo güncellendi!")
                    st.cache_data.clear()
                    st.rerun()  # <--- BURASI EKLENDİ: Kayıttan hemen sonra sayfayı yeniler
                else:
                    st.error(f"Kayıt başarısız: {res_data.get('message', 'Bilinmeyen hata')}")
            except Exception as e:
                st.error(f"Bağlantı hatası oluştu: {e}")

elif menu == "💰 Müşteri Borçları":
    st.title("💰 Müşteri Borç Listesi")
    if not df.empty and c_musteri:
        borc_df = df.groupby(c_musteri)[['Ucret_Clean', 'Alinan_Clean', 'Kalan_Clean']].sum().reset_index()
        borc_df.columns = ['Müşteri', 'Ücret', 'Alınan', 'Kalan']
        borc_df = borc_df[borc_df['Kalan'] > 0].sort_values(by='Kalan', ascending=False)
        st.dataframe(borc_df, use_container_width=True)
    else:
        st.info("Borç listesini gösterebilmek için müşteri sütunu bulunamadı.")
