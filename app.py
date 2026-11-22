import pandas as pd
import streamlit as st
import io
from datetime import datetime
from supabase import create_client, Client

st.set_page_config(page_title="Akalın Kamyon Tamir İş Takip", page_icon="🚛", layout="wide")

# --- ŞİFRE KONTROLÜ ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
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

# --- SUPABASE BAĞLANTISI ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

def load_data():
    try:
        response = supabase.table("islemler").select("*").order("tarih", desc=False).order("id", desc=False).execute()
        data = response.data
        if not data:
            return pd.DataFrame(columns=[
                "id", "tarih", "plaka", "musteri", "marka", 
                "is_tipi", "yapilan_islem", "ucret", "alinan", "kalan"
            ])
        df = pd.DataFrame(data)
        df['Ucret_Clean'] = pd.to_numeric(df['ucret'], errors='coerce').fillna(0.0)
        df['Alinan_Clean'] = pd.to_numeric(df['alinan'], errors='coerce').fillna(0.0)
        df['Kalan_Clean'] = pd.to_numeric(df['kalan'], errors='coerce').fillna(0.0)
        df['Tarih_DT'] = pd.to_datetime(df['tarih'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Supabase veritabanından veri okunamadı: {e}")
        return pd.DataFrame()

df = load_data()

# --- TABLO GÖRÜNÜMÜ VE RENKLENDİRME FONKSİYONU ---
def get_clean_display_df(input_df):
    if input_df.empty:
        return input_df
    d_df = input_df.copy()
    
    # Görünüm için okunaklı sütun adları
    rename_map = {
        "id": "Kayıt No",
        "tarih": "Tarih",
        "plaka": "Plaka",
        "musteri": "Müşteri",
        "marka": "Marka / Model",
        "is_tipi": "İş Tipi",
        "yapilan_islem": "Yapılan İşlem",
        "ucret": "Ücret",
        "alinan": "Alınan",
        "kalan": "Kalan"
    }
    
    zero_ucret_mask = d_df['Ucret_Clean'] == 0
    d_df['ucret'] = d_df['Ucret_Clean'].astype(object)
    d_df.loc[zero_ucret_mask, 'ucret'] = "Ücret Giriniz"
    
    d_df['kalan'] = d_df['Kalan_Clean'].astype(object)
    d_df.loc[zero_ucret_mask, 'kalan'] = "Bekleniyor"
    
    zero_kalan_mask = (d_df['Kalan_Clean'] == 0) & (~zero_ucret_mask)
    d_df.loc[zero_kalan_mask, 'kalan'] = "Ödendi"
    
    cols_to_show = ["id", "tarih", "plaka", "musteri", "marka", "is_tipi", "yapilan_islem", "ucret", "alinan", "kalan"]
    existing_cols = [c for c in cols_to_show if c in d_df.columns]
    d_df = d_df[existing_cols].rename(columns=rename_map)
    return d_df

def display_styled_dataframe(input_df, selectable=False, key=None):
    display_df = get_clean_display_df(input_df)
    
    def color_status(val):
        if val == "Ücret Giriniz":
            return 'color: #ff4b4b; font-weight: bold;'
        elif val == "Bekleniyor":
            return 'color: #d4ac0d; font-weight: bold;'
        elif val == "Ödendi":
            return 'color: #27ae60; font-weight: bold;'
        return ''
    
    try:
        styled = display_df.style.map(color_status)
    except AttributeError:
        styled = display_df.style.applymap(color_status)
        
    if selectable:
        st.dataframe(styled, use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun", key=key)
    else:
        st.dataframe(styled, use_container_width=True, hide_index=True)

st.sidebar.title("🚛 Akalın Servis")
menu = st.sidebar.radio(
    "Menü", 
    [
        "➕ Yeni İş Ekle", 
        "📊 Özet Panel", 
        "📋 İş Listesi & Arama", 
        "🔍 Müşteri Geçmişi", 
        "💰 Müşteri Borçları",
        "📥 E-Tablodan Veri Aktar"
    ]
)

if menu == "➕ Yeni İş Ekle":
    st.title("➕ Yeni Araç / İş Ekle")
    
    if "form_plaka" not in st.session_state: st.session_state["form_plaka"] = ""
    if "form_musteri" not in st.session_state: st.session_state["form_musteri"] = ""
    if "form_marka" not in st.session_state: st.session_state["form_marka"] = ""
    if "form_ucret" not in st.session_state: st.session_state["form_ucret"] = 0.0
    if "form_alinan" not in st.session_state: st.session_state["form_alinan"] = 0.0
    if "form_yapilan" not in st.session_state: st.session_state["form_yapilan"] = ""

    known_records = []
    if not df.empty:
        records_df = df[['musteri', 'marka', 'plaka']].dropna().drop_duplicates()
        known_records = records_df.to_dict('records')
    
    select_options = ["-- Yeni Kayıt / Manuel Gir --"]
    for r in known_records:
        m_val = str(r.get('musteri', '')).strip()
        p_val = str(r.get('plaka', '')).strip()
        mk_val = str(r.get('marka', '')).strip()
        if p_val or m_val:
            select_options.append(f"{p_val} | {m_val} ({mk_val})")

    def on_select_change():
        secim = st.session_state["secilen_arac_box"]
        if secim != "-- Yeni Kayıt / Manuel Gir --":
            try:
                idx = select_options.index(secim) - 1
                record = known_records[idx]
                st.session_state["form_musteri"] = str(record.get('musteri', ''))
                st.session_state["form_marka"] = str(record.get('marka', ''))
                st.session_state["form_plaka"] = str(record.get('plaka', ''))
            except Exception:
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
            
        submit = st.form_submit_button("💾 Kaydet")
        
        if submit:
            kalan = float(ucret) - float(alinan)
            yeni_kayit = {
                "tarih": tarih.strftime('%Y-%m-%d'),
                "plaka": plaka.strip(),
                "musteri": musteri.strip(),
                "marka": marka.strip(),
                "is_tipi": is_tipi,
                "yapilan_islem": yapilan_islem.strip(),
                "ucret": float(ucret),
                "alinan": float(alinan),
                "kalan": kalan
            }
            try:
                supabase.table("islemler").insert(yeni_kayit).execute()
                st.success("✅ İş başarıyla veritabanına kaydedildi!")
                st.rerun()
            except Exception as e:
                st.error(f"Kayıt sırasında hata oluştu: {e}")

elif menu == "📊 Özet Panel":
    st.title("📊 Tamirhane Yönetim Paneli")
    
    if df.empty:
        st.info("Veritabanında henüz kayıt bulunmuyor.")
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
        st.subheader("Son Eklenen 10 İş")
        display_styled_dataframe(df.tail(10))

elif menu == "📋 İş Listesi & Arama":
    st.title("📋 İş Geçmişi ve Arama")
    
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
        search_cols = ['plaka', 'musteri', 'marka', 'yapilan_islem', 'is_tipi']
        mask = filtered_df[search_cols].astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
        filtered_df = filtered_df[mask]
        
    if not filtered_df.empty:
        filtered_df = filtered_df.sort_values(by=['Tarih_DT', 'id'], ascending=[True, True]).reset_index(drop=True)
        st.info("💡 **İpucu:** Tablodaki bir satıra tıklayarak seçebilir, hemen aşağıdaki alandan düzenleyebilir veya silebilirsiniz.")
        
        display_styled_dataframe(filtered_df, selectable=True, key="is_listesi_tablosu")
        
        selected_rows = []
        if "is_listesi_tablosu" in st.session_state:
            selection_state = st.session_state["is_listesi_tablosu"]
            if hasattr(selection_state, 'selection') and hasattr(selection_state.selection, 'rows'):
                selected_rows = selection_state.selection.rows
        
        if selected_rows:
            selected_relative_idx = selected_rows[0]
            if selected_relative_idx < len(filtered_df):
                row_data = filtered_df.iloc[selected_relative_idx]
                kayit_id = int(row_data['id'])
                
                st.markdown("---")
                st.success(f"📌 **Seçilen Kayıt No:** #{kayit_id} | Plaka: `{row_data.get('plaka', '')}` | Müşteri: `{row_data.get('musteri', '')}`")
                
                ex_musteri = str(row_data.get('musteri') or "")
                ex_marka = str(row_data.get('marka') or "")
                ex_plaka = str(row_data.get('plaka') or "")
                ex_islem = str(row_data.get('yapilan_islem') or "")
                ex_ucret = float(row_data.get('Ucret_Clean', 0.0))
                ex_alinan = float(row_data.get('Alinan_Clean', 0.0))
                
                is_tipi_secenekleri = ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"]
                ex_istipi_val = str(row_data.get('is_tipi') or "")
                istipi_index = 0
                for i, opt in enumerate(is_tipi_secenekleri):
                    if ex_istipi_val and (ex_istipi_val.lower() in opt.lower() or opt.lower() in ex_istipi_val.lower()):
                        istipi_index = i
                        break
                
                ex_tarih = datetime.now().date()
                if pd.notna(row_data.get('Tarih_DT')):
                    ex_tarih = row_data['Tarih_DT'].date()

                tab_duzenle, tab_sil = st.tabs(["✏️ Seçilen Kaydı Güncelle", "🗑️ Seçilen Kaydı Sil"])
                
                with tab_duzenle:
                    with st.form("tiklanan_duzenleme_formu"):
                        d_kol1, d_kol2 = st.columns(2)
                        with d_kol1:
                            d_plaka = st.text_input("Plaka", value=ex_plaka)
                            d_musteri = st.text_input("Müşteri Adı / Firma", value=ex_musteri)
                            d_marka = st.text_input("Marka / Model", value=ex_marka)
                            d_is_tipi = st.selectbox("İş Tipi", is_tipi_secenekleri, index=istipi_index)
                        with d_kol2:
                            d_tarih = st.date_input("İş Tarihi", value=ex_tarih)
                            d_ucret = st.number_input("Toplam Ücret (₺)", value=ex_ucret, min_value=0.0, step=100.0)
                            d_alinan = st.number_input("Alınan Ödenen (₺)", value=ex_alinan, min_value=0.0, step=100.0)
                            d_yapilan_islem = st.text_area("Yapılan İşlem / Değişen Parça", value=ex_islem)
                            
                        guncelle_btn = st.form_submit_button("💾 Değişiklikleri Kaydet ve Güncelle")
                        
                        if guncelle_btn:
                            d_kalan = float(d_ucret) - float(d_alinan)
                            guncel_veri = {
                                "tarih": d_tarih.strftime('%Y-%m-%d'),
                                "plaka": d_plaka.strip(),
                                "musteri": d_musteri.strip(),
                                "marka": d_marka.strip(),
                                "is_tipi": d_is_tipi,
                                "yapilan_islem": d_yapilan_islem.strip(),
                                "ucret": float(d_ucret),
                                "alinan": float(d_alinan),
                                "kalan": d_kalan
                            }
                            try:
                                supabase.table("islemler").update(guncel_veri).eq("id", kayit_id).execute()
                                st.success("✅ Kayıt anında güncellendi!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Güncelleme hatası: {e}")

                with tab_sil:
                    st.warning(f"Seçilen kayıt (#{kayit_id} - {ex_plaka}) veritabanından kalıcı olarak silinecektir.")
                    if st.button("🚨 Seçilen Kaydı Kalıcı Olarak Sil", type="primary"):
                        try:
                            supabase.table("islemler").delete().eq("id", kayit_id).execute()
                            st.success("🗑️ Kayıt kalıcı olarak silindi!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Silme hatası: {e}")
        else:
            st.info("👆 Düzenlemek veya silmek istediğiniz satıra tablonun en solundaki kutucuktan tıklayarak seçin.")
    else:
        st.info("Arama kriterlerinize uygun kayıt bulunamadı.")

elif menu == "🔍 Müşteri Geçmişi":
    st.title("🔍 Müşteri İşlem Geçmişi ve Tarih Aralığı")
    
    if df.empty:
        st.info("Veritabanında henüz müşteri verisi bulunmuyor.")
    else:
        unique_customers = sorted(df['musteri'].dropna().astype(str).unique().tolist())
        unique_customers = [c for c in unique_customers if c.strip() != ""]
        unique_customers.insert(0, "-- Müşteri Seçiniz --")
        
        selected_cust = st.selectbox("Rapor Alınacak Müşteriyi Seçin:", unique_customers)
        
        if selected_cust != "-- Müşteri Seçiniz --":
            cust_df = df[df['musteri'].astype(str) == selected_cust].copy()
            
            if not cust_df.empty:
                min_date = cust_df['Tarih_DT'].min()
                max_date = cust_df['Tarih_DT'].max()
                
                min_date = datetime.now().date() if pd.isna(min_date) else min_date.date()
                max_date = datetime.now().date() if pd.isna(max_date) else max_date.date()
                
                st.markdown("---")
                tarih_col1, tarih_col2 = st.columns(2)
                with tarih_col1:
                    start_date = st.date_input("Başlangıç Tarihi", value=min_date)
                with tarih_col2:
                    end_date = st.date_input("Bitiş Tarihi", value=max_date)
                    
                mask = (cust_df['Tarih_DT'].dt.date >= start_date) & (cust_df['Tarih_DT'].dt.date <= end_date)
                filtered_cust_df = cust_df[mask].sort_values(by=['Tarih_DT', 'id'], ascending=[True, True])
                
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

elif menu == "💰 Müşteri Borçları":
    st.title("💰 Müşteri Borç Listesi")
    if not df.empty:
        borc_df = df.groupby('musteri')[['Ucret_Clean', 'Alinan_Clean', 'Kalan_Clean']].sum().reset_index()
        borc_df.columns = ['Müşteri', 'Toplam Ücret', 'Alınan', 'Kalan Borç']
        borc_df = borc_df[borc_df['Kalan Borç'] > 0].sort_values(by='Kalan Borç', ascending=False)
        st.dataframe(borc_df, use_container_width=True, hide_index=True)
    else:
        st.info("Veritabanında henüz kayıt bulunmuyor.")

elif menu == "📥 E-Tablodan Veri Aktar":
    st.title("📥 Eski Google E-Tablo Verilerini Supabase'e Aktar")
    st.info("Bu ekranı yalnızca bir kez, eski Google E-Tablonuzdaki kayıtları yeni veritabanına aktarmak için kullanın.")
    
    if st.button("🚀 Google E-Tablodaki Kayıtları Oku ve Aktar", type="primary"):
        try:
            from streamlit_gsheets import GSheetsConnection
            conn = st.connection("gsheets", type=GSheetsConnection)
            old_df = conn.read(ttl=0)
            old_df.columns = [str(c).strip() for c in old_df.columns]
            
            def find_c(df_in, kws):
                for col in df_in.columns:
                    for kw in kws:
                        if kw.lower() in col.lower():
                            return col
                return None

            c_m = find_c(old_df, ['müşteri', 'firma'])
            c_mk = find_c(old_df, ['marka', 'model'])
            c_p = find_c(old_df, ['plaka'])
            c_u = find_c(old_df, ['ücret', 'tutar', 'fiyat'])
            c_a = find_c(old_df, ['alınan', 'ödenen', 'tahsil'])
            c_k = find_c(old_df, ['kalan', 'borç', 'bakiye'])
            c_i = find_c(old_df, ['yapılan', 'islem', 'işlem', 'parça'])
            c_t = find_c(old_df, ['tipi', 'istipi', 'is_tipi'])

            def clean_num(val):
                if pd.isna(val): return 0.0
                s = str(val).replace('₺', '').replace('TL', '').replace(' ', '')
                s = s.replace('.', '').replace(',', '.')
                try:
                    return float(s)
                except Exception:
                    return 0.0

            records_to_insert = []
            for _, r in old_df.iterrows():
                t_raw = pd.to_datetime(r.get('Tarih'), errors='coerce')
                tarih_str = t_raw.strftime('%Y-%m-%d') if pd.notna(t_raw) else datetime.now().strftime('%Y-%m-%d')
                
                u_val = clean_num(r.get(c_u)) if c_u else 0.0
                a_val = clean_num(r.get(c_a)) if c_a else 0.0
                k_val = clean_num(r.get(c_k)) if c_k else (u_val - a_val)

                records_to_insert.append({
                    "tarih": tarih_str,
                    "plaka": "" if not c_p or pd.isna(r.get(c_p)) else str(r.get(c_p)).strip(),
                    "musteri": "" if not c_m or pd.isna(r.get(c_m)) else str(r.get(c_m)).strip(),
                    "marka": "" if not c_mk or pd.isna(r.get(c_mk)) else str(r.get(c_mk)).strip(),
                    "is_tipi": "" if not c_t or pd.isna(r.get(c_t)) else str(r.get(c_t)).strip(),
                    "yapilan_islem": "" if not c_i or pd.isna(r.get(c_i)) else str(r.get(c_i)).strip(),
                    "ucret": u_val,
                    "alinan": a_val,
                    "kalan": k_val
                })

            if records_to_insert:
                supabase.table("islemler").insert(records_to_insert).execute()
                st.success(f"🎉 Toplam {len(records_to_insert)} kayıt başarıyla Supabase veritabanına aktarıldı!")
            else:
                st.warning("E-Tabloda aktarılacak kayıt bulunamadı.")
        except Exception as e:
            st.error(f"Aktarım sırasında hata oluştu: {e}")
