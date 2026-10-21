import pandas as pd
import streamlit as st
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Akalın Kamyon Tamir İş Takip", page_icon="🚛", layout="wide")

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

# --- GOOGLE E-TABLO BAĞLANTISI ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        # ttl=0 veya küçük bir değer sayesinde E-Tablo'daki değişimler anında çekilir
        df = conn.read(ttl=2)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Google E-Tablo'dan veri okunamadı: {e}")
        return pd.DataFrame(columns=['Müşteri', 'Marka/Model', 'Plaka', 'Yapılan İşlem', 'Ücret', 'Alınan', 'Kalan', 'Tarih', 'İş Tipi'])

df = load_data()

st.sidebar.title("🚛 Akalın Servis")
menu = st.sidebar.radio("Menü", ["📊 Özet Panel", "📋 İş Listesi & Arama", "➕ Yeni İş Ekle", "💰 Müşteri Borçları"])

if menu == "📊 Özet Panel":
    st.title("📊 Tamirhane Yönetim Paneli")
    
    total_is = len(df)
    total_ciro = pd.to_numeric(df['Ücret'], errors='coerce').sum() if 'Ücret' in df.columns else 0
    total_alinan = pd.to_numeric(df['Alınan'], errors='coerce').sum() if 'Alınan' in df.columns else 0
    total_kalan = pd.to_numeric(df['Kalan'], errors='coerce').sum() if 'Kalan' in df.columns else 0
    
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
            conn.update(data=guncel_df)
            st.success("İş başarıyla kaydedildi ve Google E-Tablo güncellendi!")
            st.cache_data.clear()

elif menu == "💰 Müşteri Borçları":
    st.title("💰 Müşteri Borç Listesi")
    if 'Müşteri' in df.columns and 'Kalan' in df.columns:
        df['Kalan_Num'] = pd.to_numeric(df['Kalan'], errors='coerce').fillna(0)
        df['Ücret_Num'] = pd.to_numeric(df['Ücret'], errors='coerce').fillna(0)
        df['Alınan_Num'] = pd.to_numeric(df['Alınan'], errors='coerce').fillna(0)
        
        borc_df = df.groupby('Müşteri')[['Ücret_Num', 'Alınan_Num', 'Kalan_Num']].sum().reset_index()
        borc_df.columns = ['Müşteri', 'Ücret', 'Alınan', 'Kalan']
        borc_df = borc_df[borc_df['Kalan'] > 0].sort_values(by='Kalan', ascending=False)
        st.dataframe(borc_df, use_container_width=True)
