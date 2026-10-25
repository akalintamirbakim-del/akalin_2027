import pandas as pd
import streamlit as st
import requests
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Akalın Kamyon Tamir İş Takip", page_icon="🚛", layout="wide")

# --- ŞİFRE KONTROLÜ ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "Akalın.5444":
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
menu = st.sidebar.radio("Menü", ["➕ Yeni İş Ekle", "📊 Özet Panel", "📋 İş Listesi & Arama", "✏️ Kayıt Düzenle", "💰 Müşteri Borçları"])

if menu == "➕ Yeni İş Ekle":
    st.title("➕ Yeni Araç / İş Ekle")
    
    # Session state başlangıç değerleri
    if "form_plaka" not in st.session_state: st.session_state["form_plaka"] = ""
    if "form_musteri" not in st.session_state: st.session_state["form_musteri"] = ""
    if "form_marka" not in st.session_state: st.session_state["form_marka"] = ""
    if "form_ucret" not in st.session_state: st.session_state["form_ucret"] = 0.0
    if "form_alinan" not in st.session_state: st.session_state["form_alinan"] = 0.0
    if "form_yapilan" not in st.session_state: st.session_state["form_yapilan"] = ""

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

    # Araç seçildiğinde tetiklenen fonksiyon
    def on_select_change():
        secim = st.session_state["secilen_arac_box"]
        if secim != "-- Yeni Kayıt / Manuel Gir --":
            try:
                idx = select_options.index(secim) - 1
                record = known_records[idx]
                st.session_state["form_musteri"] = str(record.get(c_musteri, ''))
                st.session_state["form_marka"] = str(record.get(c_marka, ''))
                st.session_state["form_plaka"] = str(record.get(c_plaka, ''))
            except:
                pass
        else:
            st.session_state["form_musteri"] = ""
            st.session_state["form_marka"] = ""
            st.session_state["form_plaka"] = ""

    st.selectbox("🚘 Kayıtlı Araç/Müşteri Seç (Otomatik Doldurur):", select_options, key="secilen_arac_box", on_change=on_select_change)

    # Temizleme Butonu
    if st.button("🧹 Alanları Temizle"):
        st.session_state["form_plaka"] = ""
        st.session_state["form_musteri"] = ""
        st.session_state["form_marka"] = ""
        st.session_state["form_ucret"] = 0.0
        st.session_state["form_alinan"] = 0.0
        st.session_state["form_yapilan"] = ""
        st.rerun()

    with st.form("yeni_is_formu"):
        col1, col2 = st.columns(2)
        with col1:
            plaka = st.text_input("Plaka", value=st.session_state["form_plaka"])
            musteri = st.text_input("Müşteri Adı / Firma", value=st.session_state["form_musteri"])
            marka = st.text_input("Marka / Model", value=st.session_state["form_marka"])
            is_tipi = st.selectbox("İş Tipi", ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"])
        with col2:
            tarih = st.date_input("İş Tarihi", datetime.now())
            ucret = st.number_input("Toplam Ücret (₺)", value=st.session_state["form_ucret"], min_value=0.0, step=100.0)
            alinan = st.number_input("Alınan Ödenen (₺)", value=st.session_state["form_alinan"], min_value=0.0, step=100.0)
            yapilan_islem = st.text_area("Yapılan İşlem / Değişen Parça", value=st.session_state["form_yapilan"])
            
        submit = st.form_submit_button("Kaydet and Google E-Tabloya Gönder")
        
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
                    st.rerun()
                else:
                    st.error(f"Kayıt başarısız: {res_data.get('message', 'Bilinmeyen hata')}")
            except Exception as e:
                st.error(f"Bağlantı hatası oluştu: {e}")

elif menu == "📊 Özet Panel":
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
    
    if not df.empty:
        st.markdown("---")
        st.subheader("🗑️ Kayıt / Satır Sil")
        
        silme_secenekleri = []
        secenek_map = {}
        
        for idx, row in df.iterrows():
            tarih_val = str(row.get('Tarih', ''))
            plaka_val = str(row.get(c_plaka, '')) if c_plaka else ''
            musteri_val = str(row.get(c_musteri, '')) if c_musteri else ''
            islem_val = str(row.get('Yapılan İşlem', ''))
            
            label = f"Satır {idx+1} | Tarih: {tarih_val} | Plaka: {plaka_val} | Müşteri: {musteri_val} | İşlem: {islem_val[:30]}"
            silme_secenekleri.append(label)
            secenek_map[label] = idx
        
        secilen_silme = st.selectbox("Silmek istediğiniz kaydı seçin:", ["-- Seçiniz --"] + silme_secenekleri)
        
        if secilen_silme != "-- Seçiniz --":
            if st.button("Seçilen Kaydı Kalıcı Olarak Sil", type="primary"):
                gercek_idx = secenek_map[secilen_silme]
                sheets_row_index = gercek_idx + 2
                
                payload = {
                    "token": st.secrets["API_TOKEN"],
                    "action": "delete",
                    "rowIndex": sheets_row_index
                }
                
                try:
                    response = requests.post(st.secrets["WEB_APP_URL"], json=payload)
                    res_data = response.json()
                    if res_data.get("status") == "success":
                        st.success("Kayıt başarıyla silindi ve tablo güncellendi!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Silme başarısız: {res_data.get('message', 'Bilinmeyen hata')}")
                except Exception as e:
                    st.error(f"Bağlantı hatası oluştu: {e}")

elif menu == "✏️ Kayıt Düzenle":
    st.title("✏️ Mevcut Kaydı Düzenle")
    
    if df.empty:
        st.info("Düzenlenecek kayıt bulunamadı.")
    else:
        duzenle_secenekleri = []
        duzenle_map = {}
        
        for idx, row in df.iterrows():
            tarih_val = str(row.get('Tarih', ''))
            plaka_val = str(row.get(c_plaka, '')) if c_plaka else ''
            musteri_val = str(row.get(c_musteri, '')) if c_musteri else ''
            
            label = f"Satır {idx+1} | Tarih: {tarih_val} | Plaka: {plaka_val} | Müşteri: {musteri_val}"
            duzenle_secenekleri.append(label)
            duzenle_map[label] = (idx, row)
            
        secilen_duzenleme = st.selectbox("Düzenlemek istediğiniz kaydı seçin:", ["-- Seçiniz --"] + duzenle_secenekleri)
        
        if secilen_duzenleme != "-- Seçiniz --":
            gercek_idx, row_data = duzenle_map[secilen_duzenleme]
            
            def get_val(col_key, default=""):
                if col_key and col_key in row_data:
                    val = row_data[col_key]
                    return "" if pd.isna(val) else str(val)
                return default

            ex_musteri = get_val(c_musteri)
            ex_marka = get_val(c_marka)
            ex_plaka = get_val(c_plaka)
            ex_ucret = float(row_data.get('Ucret_Clean', 0.0))
            ex_alinan = float(row_data.get('Alinan_Clean', 0.0))
            
            with st.form("duzenleme_formu"):
                col1, col2 = st.columns(2)
                with col1:
                    d_plaka = st.text_input("Plaka", value=ex_plaka)
                    d_musteri = st.text_input("Müşteri Adı / Firma", value=ex_musteri)
                    d_marka = st.text_input("Marka / Model", value=ex_marka)
                    d_is_tipi = st.selectbox("İş Tipi", ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"])
                with col2:
                    d_tarih = st.date_input("İş Tarihi", datetime.now())
                    d_ucret = st.number_input("Toplam Ücret (₺)", value=ex_ucret, min_value=0.0, step=100.0)
                    d_alinan = st.number_input("Alınan Ödenen (₺)", value=ex_alinan, min_value=0.0, step=100.0)
                    d_yapilan_islem = st.text_area("Yapılan İşlem / Değişen Parça")
                    
                guncelle_submit = st.form_submit_button("Değişiklikleri Kaydet ve Güncelle")
                
                if guncelle_submit:
                    d_kalan = d_ucret - d_alinan
                    sheets_row_index = gercek_idx + 2
                    
                    payload = {
                        "token": st.secrets["API_TOKEN"],
                        "action": "update",
                        "rowIndex": sheets_row_index,
                        "Musteri": d_musteri,
                        "Marka": d_marka,
                        "Plaka": d_plaka,
                        "YapilanIslem": d_yapilan_islem,
                        "Ucret": d_ucret,
                        "Alinan": d_alinan,
                        "Kalan": d_kalan,
                        "Tarih": d_tarih.strftime('%Y-%m-%d'),
                        "IsTipi": d_is_tipi
                    }
                    
                    try:
                        response = requests.post(st.secrets["WEB_APP_URL"], json=payload)
                        res_data = response.json()
                        if res_data.get("status") == "success":
                            st.success("Kayıt başarıyla güncellendi!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"Güncelleme başarısız: {res_data.get('message', 'Bilinmeyen hata')}")
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
