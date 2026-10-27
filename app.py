import pandas as pd
import streamlit as st
import requests
import io
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Akalın Kamyon Tamir İş Takip", page_icon="🚛", layout="wide")

# --- ŞİFRE KONTROLÜ ---
def check_password():
    def password_entered():if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
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
    if 'Tarih' in df.columns:
        df['Tarih_DT'] = pd.to_datetime(df['Tarih'], errors='coerce')

# --- TABLO GÖRÜNÜMÜ VE RENKLENDİRME FONKSİYONU ---
def get_clean_display_df(input_df):
    if input_df.empty:
        return input_df
    d_df = input_df.copy()
    if 'Ucret_Clean' in d_df.columns and 'Kalan_Clean' in d_df.columns:
        zero_ucret_mask = d_df['Ucret_Clean'] == 0
        
        # Ücret 0 ise "Ücret Giriniz"
        if c_ucret and c_ucret in d_df.columns:
            d_df[c_ucret] = d_df[c_ucret].astype(object)
            d_df.loc[zero_ucret_mask, c_ucret] = "Ücret Giriniz"
            
        if c_kalan and c_kalan in d_df.columns:
            d_df[c_kalan] = d_df[c_kalan].astype(object)
            # Ücret 0 ise kalan "Bekleniyor"
            d_df.loc[zero_ucret_mask, c_kalan] = "Bekleniyor"
            
            # Kalan 0 ve ücret 0'dan büyükse "Ödendi"
            zero_kalan_mask = (d_df['Kalan_Clean'] == 0) & (~zero_ucret_mask)
            d_df.loc[zero_kalan_mask, c_kalan] = "Ödendi"
            
    return d_df.drop(columns=['Tarih_DT', 'Ucret_Clean', 'Alinan_Clean', 'Kalan_Clean'], errors='ignore')

def display_styled_dataframe(input_df):
    display_df = get_clean_display_df(input_df)
    
    def color_status(val):
        if val == "Ücret Giriniz":
            return 'color: #ff4b4b; font-weight: bold;'  # Kırmızı
        elif val == "Bekleniyor":
            return 'color: #d4ac0d; font-weight: bold;'  # Sarı
        elif val == "Ödendi":
            return 'color: #27ae60; font-weight: bold;'  # Yeşil
        return ''
    
    try:
        styled = display_df.style.map(color_status)
    except AttributeError:
        styled = display_df.style.applymap(color_status)
        
    st.dataframe(styled, use_container_width=True)

st.sidebar.title("🚛 Akalın Servis")
menu = st.sidebar.radio("Menü", ["➕ Yeni İş Ekle", "📊 Özet Panel", "📋 İş Listesi & Arama", "✏️ Kayıt Düzenle", "🔍 Müşteri Geçmişi", "💰 Müşteri Borçları"])

if menu == "➕ Yeni İş Ekle":
    st.title("➕ Yeni Araç / İş Ekle")
    
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

    if st.button("🧹 Alanları Temizle"):
        st.session_state["form_plaka"] = ""
        st.session_state["form_musteri"] = ""
        st.session_state["form_marka"] = ""
        st.session_state["form_ucret"] = 0.0
        st.session_state["form_alinan"] = 0.0
        st.session_state["form_yapilan"] = ""
        st.rerun()

    with st.form("yeni_is_formu"):
        yeni_col1, yeni_col2 = st.columns(2)
        with yeni_col1:
            plaka = st.text_input("Plaka", value=st.session_state["form_plaka"])
            musteri = st.text_input("Müşteri Adı / Firma", value=st.session_state["form_musteri"])
            marka = st.text_input("Marka / Model", value=st.session_state["form_marka"])
            is_tipi = st.selectbox("İş Tipi", ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"])
        with yeni_col2:
            tarih = st.date_input("İş Tarihi", datetime.now())
            ucret = st.number_input("Toplam Ücret (₺)", value=st.session_state["form_ucret"], min_value=0.0, step=100.0)
            alinan = st.number_input("Alınan Ödenen (₺)", value=st.session_state["form_alinan"], min_value=0.0, step=100.0)
            yapilan_islem = st.text_area("Yapılan İşlem / Değişen Parça", value=st.session_state["form_yapilan"])
            
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
        
        ozet_col1, ozet_col2, ozet_col3, ozet_col4 = st.columns(4)
        ozet_col1.metric("Toplam İş / Araç", f"{total_is}")
        ozet_col2.metric("Toplam Ciro", f"{total_ciro:,.2f} ₺")
        ozet_col3.metric("Tahsil Edilen", f"{total_alinan:,.2f} ₺")
        ozet_col4.metric("Kalan Alacak (Borç)", f"{total_kalan:,.2f} ₺")
        
        st.markdown("---")
        st.subheader("Son Eklenen İşler")
        display_styled_dataframe(df.tail(10))

elif menu == "📋 İş Listesi & Arama":
    st.title("📋 İş Geçmişi ve Arama")
    
    # Yıl ve Ay Seçim Filtreleri
    f_col1, f_col2, f_col3 = st.columns(3)
    
    years = ["Tümü"]
    if not df.empty and 'Tarih_DT' in df.columns:
        valid_years = df['Tarih_DT'].dt.year.dropna().unique()
        years.extend(sorted([int(y) for y in valid_years], reverse=True))
        
    months = {
        "Tümü": 0, "Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, 
        "Mayıs": 5, "Haziran": 6, "Temmuz": 7, "Ağustos": 8, 
        "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12
    }
    
    with f_col1:
        selected_year = st.selectbox("📅 Yıl Seçin", years)
    with f_col2:
        selected_month_name = st.selectbox("🗓️ Ay Seçin", list(months.keys()))
    with f_col3:
        search_term = st.text_input("🔍 Müşteri, Plaka veya İşlem Ara:", "")
        
    filtered_df = df.copy()
    if not filtered_df.empty and 'Tarih_DT' in filtered_df.columns:
        if selected_year != "Tümü":
            filtered_df = filtered_df[filtered_df['Tarih_DT'].dt.year == selected_year]
        if selected_month_name != "Tümü":
            m_num = months[selected_month_name]
            filtered_df = filtered_df[filtered_df['Tarih_DT'].dt.month == m_num]
            
    if search_term and not filtered_df.empty:
        mask = filtered_df.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
        filtered_df = filtered_df[mask]
        
    # Tarihe göre sıralama: En üstte en eski olacak şekilde (Artan sıralama)
    if not filtered_df.empty and 'Tarih_DT' in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by='Tarih_DT', ascending=True)
        
    display_styled_dataframe(filtered_df)
    
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
                duzen_col1, duzen_col2 = st.columns(2)
                with duzen_col1:
                    d_plaka = st.text_input("Plaka", value=ex_plaka)
                    d_musteri = st.text_input("Müşteri Adı / Firma", value=ex_musteri)
                    d_marka = st.text_input("Marka / Model", value=ex_marka)
                    d_is_tipi = st.selectbox("İş Tipi", ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"])
                with duzen_col2:
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

elif menu == "🔍 Müşteri Geçmişi":
    st.title("🔍 Müşteri İşlem Geçmişi ve Tarih Aralığı")
    
    if df.empty or not c_musteri:
        st.info("Tabloda gösterilecek müşteri verisi bulunamadı.")
    else:
        unique_customers = df[c_musteri].dropna().astype(str).unique().tolist()
        unique_customers.insert(0, "-- Müşteri Seçiniz --")
        
        selected_cust = st.selectbox("Rapor Alınacak Müşteriyi Seçin:", unique_customers)
        
        if selected_cust != "-- Müşteri Seçiniz --":
            if 'Tarih' in df.columns:
                cust_df = df[df[c_musteri].astype(str) == selected_cust].copy()
                
                if not cust_df.empty:
                    min_date = cust_df['Tarih_DT'].min()
                    max_date = cust_df['Tarih_DT'].max()
                    
                    if pd.isna(min_date): min_date = datetime.now().date()
                    else: min_date = min_date.date()
                        
                    if pd.isna(max_date): max_date = datetime.now().date()
                    else: max_date = max_date.date()
                    
                    st.markdown("---")
                    tarih_col1, tarih_col2 = st.columns(2)
                    with tarih_col1:
                        start_date = st.date_input("Başlangıç Tarihi", value=min_date)
                    with tarih_col2:
                        end_date = st.date_input("Bitiş Tarihi", value=max_date)
                        
                    mask = (cust_df['Tarih_DT'].dt.date >= start_date) & (cust_df['Tarih_DT'].dt.date <= end_date)
                    filtered_cust_df = cust_df[mask]
                    
                    # En üstte en eski olacak şekilde sıralama (Artan tarih)
                    if not filtered_cust_df.empty and 'Tarih_DT' in filtered_cust_df.columns:
                        filtered_cust_df = filtered_cust_df.sort_values(by='Tarih_DT', ascending=True)
                    
                    st.markdown("---")
                    st.subheader(f"📊 {selected_cust} İçin Tarih Aralığı Raporu")
                    
                    if not filtered_cust_df.empty:
                        t_is = len(filtered_cust_df)
                        t_ciro = filtered_cust_df['Ucret_Clean'].sum()
                        t_alinan = filtered_cust_df['Alinan_Clean'].sum()
                        t_kalan = filtered_cust_df['Kalan_Clean'].sum()
                        
                        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                        m_col1.metric("Toplam İş", f"{t_is}")
                        m_col2.metric("Toplam Ücret", f"{t_ciro:,.2f} ₺")
                        m_col3.metric("Ödenen", f"{t_alinan:,.2f} ₺")
                        m_col4.metric("Kalan Borç", f"{t_kalan:,.2f} ₺")
                        
                        st.markdown("---")
                        display_df = get_clean_display_df(filtered_cust_df)
                        
                        # --- EXCEL (.xlsx) OLARAK İNDİRME ---
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            display_df.to_excel(writer, index=False, sheet_name='Müşteri Geçmişi')
                        excel_data = output.getvalue()

                        st.download_button(
                            label="📥 Bu Raporu Excel (.xlsx) Olarak İndir",
                            data=excel_data,
                            file_name=f"{selected_cust}_islem_gecmisi.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                        
                        display_styled_dataframe(filtered_cust_df)
                    else:
                        st.warning("Seçilen tarih aralığında bu müşteriye ait kayıt bulunamadı.")
                else:
                    st.warning("Bu müşteriye ait kayıt bulunamadı.")
            else:
                st.error("Tabloda 'Tarih' sütunu bulunamadığı için tarih filtrelemesi yapılamıyor.")

elif menu == "💰 Müşteri Borçları":
    st.title("💰 Müşteri Borç Listesi")
    if not df.empty and c_musteri:
        borc_df = df.groupby(c_musteri)[['Ucret_Clean', 'Alinan_Clean', 'Kalan_Clean']].sum().reset_index()
        borc_df.columns = ['Müşteri', 'Ücret', 'Alınan', 'Kalan']
        borc_df = borc_df[borc_df['Kalan'] > 0].sort_values(by='Kalan', ascending=False)
        st.dataframe(borc_df, use_container_width=True)
    else:
        st.info("Bu listede borçları gösterebilmek için müşteri sütunu bulunamadı.")
