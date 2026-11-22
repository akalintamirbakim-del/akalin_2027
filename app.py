import io
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.set_page_config(
    page_title="Akalın Kamyon Tamir İş Takip",
    page_icon="🚛",
    layout="wide",
)


# --- ŞİFRE KONTROLÜ ---
def check_password() -> bool:
    def password_entered():
        if st.session_state.get("password") == st.secrets.get("APP_PASSWORD"):
            st.session_state["password_correct"] = True
            st.session_state.pop("password", None)
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.subheader("🔒 Lütfen Giriş Şifresini Girin")
        st.text_input("Şifre", type="password", on_change=password_entered, key="password")
        return False
    if not st.session_state["password_correct"]:
        st.text_input("Şifre", type="password", on_change=password_entered, key="password")
        st.error("😕 Şifre yanlış. Lütfen tekrar deneyin.")
        return False
    return True


if not check_password():
    st.stop()


# --- YARDIMCI FONKSİYONLAR ---
def find_col(frame: pd.DataFrame, keywords: list[str]) -> str | None:
    for col in frame.columns:
        col_lower = str(col).lower()
        for kw in keywords:
            if kw.lower() in col_lower:
                return col
    return None


def parse_money(frame: pd.DataFrame, col_name: str | None) -> pd.Series:
    if frame.empty or not col_name or col_name not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    s = frame[col_name].astype(str)
    s = (
        s.str.replace("₺", "", regex=False)
        .str.replace("TL", "", regex=False)
        .str.replace("tl", "", regex=False)
        .str.replace("\xa0", "", regex=False)
        .str.replace(" ", "", regex=False)
    )
    # Hem "1.250,50" hem "1250.50" formatlarını destekle
    has_comma = s.str.contains(",", regex=False)
    s_comma = s[has_comma].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    s_dot = s[~has_comma]
    cleaned = pd.concat([s_comma, s_dot]).reindex(frame.index)
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def post_to_sheet(payload: dict) -> tuple[bool, str]:
    try:
        response = requests.post(st.secrets["WEB_APP_URL"], json=payload, timeout=15)
        response.raise_for_status()
        res_data = response.json()
        if res_data.get("status") == "success":
            return True, res_data.get("message", "İşlem başarılı.")
        return False, res_data.get("message", "Bilinmeyen hata oluştu.")
    except requests.exceptions.Timeout:
        return False, "Sunucu yanıt verme süresi doldu (timeout)."
    except ValueError:
        return False, "Sunucudan geçerli bir JSON yanıtı alınamadı."
    except Exception as e:
        return False, f"Bağlantı hatası oluştu: {e}"


def refresh_app_data() -> None:
    try:
        conn.clear()
    except Exception:
        pass
    st.cache_data.clear()
    st.session_state.pop("is_listesi_tablosu", None)


# --- GOOGLE E-TABLO BAĞLANTISI ---
conn = st.connection("gsheets", type=GSheetsConnection)


def load_data() -> pd.DataFrame:
    try:
        loaded = conn.read(ttl=2)
        if loaded is None or loaded.empty:
            return pd.DataFrame()
        loaded = loaded.copy()
        loaded.columns = [str(c).strip() for c in loaded.columns]
        # Başlık satırı 1. satır kabul edilerek veri satırları 2. satırdan başlar
        loaded["_SheetRow"] = loaded.index + 2
        return loaded
    except Exception as e:
        st.error(f"Google E-Tablo'dan veri okunamadı: {e}")
        return pd.DataFrame()


df = load_data()

c_musteri = find_col(df, ["müşteri", "musteri", "firma"])
c_marka = find_col(df, ["marka", "model", "araç", "arac"])
c_plaka = find_col(df, ["plaka"])
c_ucret = find_col(df, ["ücret", "ucret", "tutar", "fiyat"])
c_alinan = find_col(df, ["alınan", "alinan", "ödenen", "odenen", "tahsil"])
c_kalan = find_col(df, ["kalan", "borç", "borc", "bakiye"])
c_islem = find_col(df, ["yapılan", "yapilan", "islem", "işlem", "parça", "parca"])
c_istipi = find_col(df, ["tipi", "istipi", "is_tipi", "iş tipi"])
c_tarih = find_col(df, ["tarih"])

if not df.empty:
    df["Ucret_Clean"] = parse_money(df, c_ucret)
    df["Alinan_Clean"] = parse_money(df, c_alinan)
    df["Kalan_Clean"] = parse_money(df, c_kalan)
    if c_tarih:
        df["Tarih_DT"] = pd.to_datetime(df[c_tarih], errors="coerce")


# --- TABLO GÖRÜNÜMÜ VE RENKLENDİRME ---
def get_clean_display_df(input_df: pd.DataFrame) -> pd.DataFrame:
    if input_df.empty:
        return input_df
    d_df = input_df.copy()
    if "Ucret_Clean" in d_df.columns and "Kalan_Clean" in d_df.columns:
        zero_ucret_mask = d_df["Ucret_Clean"] == 0

        if c_ucret and c_ucret in d_df.columns:
            d_df[c_ucret] = d_df[c_ucret].astype(object)
            d_df.loc[zero_ucret_mask, c_ucret] = "Ücret Giriniz"

        if c_kalan and c_kalan in d_df.columns:
            d_df[c_kalan] = d_df[c_kalan].astype(object)
            d_df.loc[zero_ucret_mask, c_kalan] = "Bekleniyor"

            zero_kalan_mask = (d_df["Kalan_Clean"] == 0) & (~zero_ucret_mask)
            d_df.loc[zero_kalan_mask, c_kalan] = "Ödendi"

    drop_cols = ["_SheetRow", "Tarih_DT", "Ucret_Clean", "Alinan_Clean", "Kalan_Clean"]
    return d_df.drop(columns=drop_cols, errors="ignore")


def display_styled_dataframe(input_df: pd.DataFrame, table_key: str = "is_listesi_tablosu", selectable: bool = True):
    display_df = get_clean_display_df(input_df)

    def color_status(val):
        if val == "Ücret Giriniz":
            return "color: #ff4b4b; font-weight: bold;"
        if val == "Bekleniyor":
            return "color: #d4ac0d; font-weight: bold;"
        if val == "Ödendi":
            return "color: #27ae60; font-weight: bold;"
        return ""

    try:
        styled = display_df.style.map(color_status)
    except AttributeError:
        styled = display_df.style.applymap(color_status)

    if selectable:
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key=table_key,
        )
    else:
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
        )


# --- KENAR ÇUBUĞU MENÜSÜ ---
st.sidebar.title("🚛 Akalın Servis")
menu = st.sidebar.radio(
    "Menü",
    [
        "➕ Yeni İş Ekle",
        "📊 Özet Panel",
        "📋 İş Listesi & Arama",
        "🔍 Müşteri Geçmişi",
        "💰 Müşteri Borçları",
    ],
)

# ==========================================
# 1. YENİ İŞ EKLE
# ==========================================
if menu == "➕ Yeni İş Ekle":
    st.title("➕ Yeni Araç / İş Ekle")

    defaults = {
        "form_plaka": "",
        "form_musteri": "",
        "form_marka": "",
        "form_ucret": 0.0,
        "form_alinan": 0.0,
        "form_yapilan": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    known_records = []
    if not df.empty and c_musteri:
        cols_for_known = [c for c in [c_plaka, c_musteri, c_marka] if c and c in df.columns]
        records_df = df[cols_for_known].copy()
        records_df[c_musteri] = records_df[c_musteri].fillna("").astype(str).str.strip()
        records_df = records_df[records_df[c_musteri] != ""].drop_duplicates()
        known_records = records_df.to_dict("records")

    select_options = ["-- Yeni Kayıt / Manuel Gir --"]
    for r in known_records:
        m_val = str(r.get(c_musteri, "")).strip() if c_musteri else ""
        p_val = str(r.get(c_plaka, "")).strip() if c_plaka else ""
        mk_val = str(r.get(c_marka, "")).strip() if c_marka else ""
        label_parts = [part for part in [p_val, m_val] if part]
        label = " | ".join(label_parts) if label_parts else "Kayıt"
        if mk_val:
            label = f"{label} ({mk_val})"
        select_options.append(label)

    def on_select_change():
        secim = st.session_state.get("secilen_arac_box")
        if secim and secim != "-- Yeni Kayıt / Manuel Gir --":
            try:
                idx = select_options.index(secim) - 1
                record = known_records[idx]
                st.session_state["form_musteri"] = str(record.get(c_musteri, "") or "")
                st.session_state["form_marka"] = str(record.get(c_marka, "") or "")
                st.session_state["form_plaka"] = str(record.get(c_plaka, "") or "")
            except Exception:
                pass
        else:
            st.session_state["form_musteri"] = ""
            st.session_state["form_marka"] = ""
            st.session_state["form_plaka"] = ""

    col_sel, col_clr = st.columns([4, 1])
    with col_sel:
        st.selectbox(
            "🚘 Kayıtlı Araç/Müşteri Seç (Otomatik Doldurur):",
            select_options,
            key="secilen_arac_box",
            on_change=on_select_change,
        )
    with col_clr:
        st.write("")
        st.write("")
        if st.button("🧹 Alanları Temizle", use_container_width=True):
            for k, v in defaults.items():
                st.session_state[k] = v
            st.session_state["secilen_arac_box"] = "-- Yeni Kayıt / Manuel Gir --"
            st.rerun()

    with st.form("yeni_is_formu"):
        yeni_col1, yeni_col2 = st.columns(2)
        with yeni_col1:
            plaka = st.text_input("Plaka", key="form_plaka")
            musteri = st.text_input("Müşteri Adı / Firma", key="form_musteri")
            marka = st.text_input("Marka / Model", key="form_marka")
            is_tipi = st.selectbox("İş Tipi", ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"])
        with yeni_col2:
            tarih = st.date_input("İş Tarihi", value=datetime.now().date())
            ucret = st.number_input("Toplam Ücret (₺)", key="form_ucret", min_value=0.0, step=100.0)
            alinan = st.number_input("Alınan Ödenen (₺)", key="form_alinan", min_value=0.0, step=100.0)
            yapilan_islem = st.text_area("Yapılan İşlem / Değişen Parça", key="form_yapilan")

        submit = st.form_submit_button("Kaydet ve Google E-Tabloya Gönder")

        if submit:
            if not musteri.strip() and not plaka.strip():
                st.warning("Lütfen en azından Müşteri Adı veya Plaka bilgisi girin.")
            else:
                kalan = ucret - alinan
                payload = {
                    "token": st.secrets["API_TOKEN"],
                    "Musteri": musteri.strip(),
                    "Marka": marka.strip(),
                    "Plaka": plaka.strip().upper(),
                    "YapilanIslem": yapilan_islem.strip(),
                    "Ucret": float(ucret),
                    "Alinan": float(alinan),
                    "Kalan": float(kalan),
                    "Tarih": tarih.strftime("%Y-%m-%d"),
                    "IsTipi": is_tipi,
                }
                ok, msg = post_to_sheet(payload)
                if ok:
                    st.success("İş başarıyla kaydedildi ve Google E-Tablo güncellendi!")
                    refresh_app_data()
                    st.rerun()
                else:
                    st.error(f"Kayıt başarısız: {msg}")

# ==========================================
# 2. ÖZET PANEL
# ==========================================
elif menu == "📊 Özet Panel":
    st.title("📊 Tamirhane Yönetim Paneli")

    if df.empty:
        st.info("Google E-Tablonuz şu an boş veya veriler yükleniyor...")
    else:
        total_is = len(df)
        total_ciro = df["Ucret_Clean"].sum()
        total_alinan = df["Alinan_Clean"].sum()
        total_kalan = df["Kalan_Clean"].sum()

        ozet_col1, ozet_col2, ozet_col3, ozet_col4 = st.columns(4)
        ozet_col1.metric("Toplam İş / Araç", f"{total_is}")
        ozet_col2.metric("Toplam Ciro", f"{total_ciro:,.2f} ₺")
        ozet_col3.metric("Tahsil Edilen", f"{total_alinan:,.2f} ₺")
        ozet_col4.metric("Kalan Alacak (Borç)", f"{total_kalan:,.2f} ₺")

        st.markdown("---")
        st.subheader("Son Eklenen İşler")
        display_styled_dataframe(df.tail(10), table_key="ozet_son_isler", selectable=False)

# ==========================================
# 3. İŞ LİSTESİ & ARAMA
# ==========================================
elif menu == "📋 İş Listesi & Arama":
    st.title("📋 İş Geçmişi ve Arama")

    if df.empty:
        st.info("Tabloda henüz kayıt bulunmuyor.")
    else:
        f_col1, f_col2, f_col3 = st.columns(3)

        years = ["Tümü"]
        if "Tarih_DT" in df.columns:
            valid_years = df["Tarih_DT"].dt.year.dropna().unique()
            years.extend(sorted([int(y) for y in valid_years], reverse=True))

        months = {
            "Tümü": 0,
            "Ocak": 1,
            "Şubat": 2,
            "Mart": 3,
            "Nisan": 4,
            "Mayıs": 5,
            "Haziran": 6,
            "Temmuz": 7,
            "Ağustos": 8,
            "Eylül": 9,
            "Ekim": 10,
            "Kasım": 11,
            "Aralık": 12,
        }

        with f_col1:
            selected_year = st.selectbox("📅 Yıl Seçin", years)
        with f_col2:
            selected_month_name = st.selectbox("🗓️ Ay Seçin", list(months.keys()))
        with f_col3:
            search_term = st.text_input("🔍 Müşteri, Plaka veya İşlem Ara:", "").strip()

        filtered_df = df.copy()
        if "Tarih_DT" in filtered_df.columns:
            if selected_year != "Tümü":
                filtered_df = filtered_df[filtered_df["Tarih_DT"].dt.year == selected_year]
            if selected_month_name != "Tümü":
                m_num = months[selected_month_name]
                filtered_df = filtered_df[filtered_df["Tarih_DT"].dt.month == m_num]

        if search_term and not filtered_df.empty:
            searchable_cols = [
                c
                for c in [c_musteri, c_plaka, c_marka, c_islem, c_istipi, c_tarih]
                if c and c in filtered_df.columns
            ]
            if searchable_cols:
                mask = (
                    filtered_df[searchable_cols]
                    .astype(str)
                    .apply(lambda col: col.str.contains(search_term, case=False, na=False))
                    .any(axis=1)
                )
                filtered_df = filtered_df[mask]

        if not filtered_df.empty and "Tarih_DT" in filtered_df.columns:
            filtered_df = filtered_df.sort_values(by="Tarih_DT", ascending=True, na_position="last")

        st.info("💡 **İpucu:** Tablodaki bir satıra tıklayarak seçebilir, hemen aşağıdaki alandan düzenleyebilir veya silebilirsiniz.")

        display_styled_dataframe(filtered_df, table_key="is_listesi_tablosu", selectable=True)

        selected_rows = []
        selection_state = st.session_state.get("is_listesi_tablosu")
        if selection_state is not None:
            if hasattr(selection_state, "selection") and hasattr(selection_state.selection, "rows"):
                selected_rows = selection_state.selection.rows
            elif isinstance(selection_state, dict):
                selected_rows = selection_state.get("selection", {}).get("rows", [])

        if selected_rows and len(filtered_df) > 0:
            selected_relative_idx = selected_rows[0]
            if 0 <= selected_relative_idx < len(filtered_df):
                row_data = filtered_df.iloc[selected_relative_idx]
                sheets_row_index = int(row_data.get("_SheetRow", row_data.name + 2))

                def get_val(col_key: str | None, default: str = "") -> str:
                    if col_key and col_key in row_data.index:
                        val = row_data[col_key]
                        return default if pd.isna(val) else str(val)
                    return default

                ex_musteri = get_val(c_musteri)
                ex_marka = get_val(c_marka)
                ex_plaka = get_val(c_plaka)
                ex_islem = get_val(c_islem)
                ex_ucret = float(row_data.get("Ucret_Clean", 0.0))
                ex_alinan = float(row_data.get("Alinan_Clean", 0.0))

                st.markdown("---")
                st.success(f"📌 **Seçilen Kayıt:** E-Tablo Satır `{sheets_row_index}` | Plaka: `{ex_plaka}` | Müşteri: `{ex_musteri}`")

                is_tipi_secenekleri = ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"]
                ex_istipi_val = get_val(c_istipi)
                istipi_index = 0
                for i, opt in enumerate(is_tipi_secenekleri):
                    if ex_istipi_val.lower() and (
                        ex_istipi_val.lower() in opt.lower() or opt.lower() in ex_istipi_val.lower()
                    ):
                        istipi_index = i
                        break

                ex_tarih = datetime.now().date()
                if "Tarih_DT" in row_data.index and pd.notna(row_data["Tarih_DT"]):
                    ex_tarih = row_data["Tarih_DT"].date()
                elif c_tarih and c_tarih in row_data.index and pd.notna(row_data[c_tarih]):
                    parsed_date = pd.to_datetime(row_data[c_tarih], errors="coerce")
                    if pd.notna(parsed_date):
                        ex_tarih = parsed_date.date()

                tab_duzenle, tab_sil = st.tabs(["✏️ Seçilen Kaydı Güncelle", "🗑️ Seçilen Kaydı Sil"])

                with tab_duzenle:
                    with st.form(f"tiklanan_duzenleme_formu_{sheets_row_index}"):
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
                            d_kalan = d_ucret - d_alinan
                            payload = {
                                "token": st.secrets["API_TOKEN"],
                                "action": "update",
                                "rowIndex": sheets_row_index,
                                "Musteri": d_musteri.strip(),
                                "Marka": d_marka.strip(),
                                "Plaka": d_plaka.strip().upper(),
                                "YapilanIslem": d_yapilan_islem.strip(),
                                "Ucret": float(d_ucret),
                                "Alinan": float(d_alinan),
                                "Kalan": float(d_kalan),
                                "Tarih": d_tarih.strftime("%Y-%m-%d"),
                                "IsTipi": d_is_tipi,
                            }
                            ok, msg = post_to_sheet(payload)
                            if ok:
                                st.success("Kayıt başarıyla güncellendi!")
                                refresh_app_data()
                                st.rerun()
                            else:
                                st.error(f"Güncelleme başarısız: {msg}")

                with tab_sil:
                    st.warning(f"Seçilen kayıt (E-Tablo Satır {sheets_row_index}) kalıcı olarak silinecektir.")
                    if st.button("🚨 Seçilen Kaydı Kalıcı Olarak Sil", type="primary"):
                        payload = {
                            "token": st.secrets["API_TOKEN"],
                            "action": "delete",
                            "rowIndex": sheets_row_index,
                        }
                        ok, msg = post_to_sheet(payload)
                        if ok:
                            st.success("Kayıt başarıyla silindi!")
                            refresh_app_data()
                            st.rerun()
                        else:
                            st.error(f"Silme başarısız: {msg}")
        else:
            st.info("👆 Düzenlemek veya silmek istediğiniz satıra tıklayarak seçin.")

# ==========================================
# 4. MÜŞTERİ GEÇMİŞİ
# ==========================================
elif menu == "🔍 Müşteri Geçmişi":
    st.title("🔍 Müşteri İşlem Geçmişi ve Tarih Aralığı")

    if df.empty or not c_musteri:
        st.info("Tabloda gösterilecek müşteri verisi bulunamadı.")
    else:
        unique_customers = sorted(df[c_musteri].dropna().astype(str).str.strip().unique().tolist())
        unique_customers = [u for u in unique_customers if u]
        unique_customers.insert(0, "-- Müşteri Seçiniz --")

        selected_cust = st.selectbox("Rapor Alınacak Müşteriyi Seçin:", unique_customers)

        if selected_cust != "-- Müşteri Seçiniz --":
            if "Tarih_DT" in df.columns:
                cust_df = df[df[c_musteri].astype(str).str.strip() == selected_cust].copy()

                if not cust_df.empty:
                    min_date = cust_df["Tarih_DT"].min()
                    max_date = cust_df["Tarih_DT"].max()

                    start_default = datetime.now().date() if pd.isna(min_date) else min_date.date()
                    end_default = datetime.now().date() if pd.isna(max_date) else max_date.date()

                    st.markdown("---")
                    tarih_col1, tarih_col2 = st.columns(2)
                    with tarih_col1:
                        start_date = st.date_input("Başlangıç Tarihi", value=start_default)
                    with tarih_col2:
                        end_date = st.date_input("Bitiş Tarihi", value=end_default)

                    if start_date > end_date:
                        st.error("Başlangıç tarihi bitiş tarihinden büyük olamaz.")
                    else:
                        valid_dates = cust_df["Tarih_DT"].dropna()
                        mask = (valid_dates.dt.date >= start_date) & (valid_dates.dt.date <= end_date)
                        filtered_cust_df = cust_df.loc[mask.index[mask]].copy()

                        if not filtered_cust_df.empty:
                            filtered_cust_df = filtered_cust_df.sort_values(
                                by="Tarih_DT", ascending=True, na_position="last"
                            )

                        st.markdown("---")
                        st.subheader(f"📊 {selected_cust} İçin Tarih Aralığı Raporu")

                        if not filtered_cust_df.empty:
                            t_is = len(filtered_cust_df)
                            t_ciro = filtered_cust_df["Ucret_Clean"].sum()
                            t_alinan = filtered_cust_df["Alinan_Clean"].sum()
                            t_kalan = filtered_cust_df["Kalan_Clean"].sum()

                            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                            m_col1.metric("Toplam İş", f"{t_is}")
                            m_col2.metric("Toplam Ücret", f"{t_ciro:,.2f} ₺")
                            m_col3.metric("Ödenen", f"{t_alinan:,.2f} ₺")
                            m_col4.metric("Kalan Borç", f"{t_kalan:,.2f} ₺")

                            st.markdown("---")
                            display_df = get_clean_display_df(filtered_cust_df)

                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                                display_df.to_excel(writer, index=False, sheet_name="Müşteri Geçmişi")
                            excel_data = output.getvalue()

                            safe_name = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in selected_cust)
                            st.download_button(
                                label="📥 Bu Raporu Excel (.xlsx) Olarak İndir",
                                data=excel_data,
                                file_name=f"{safe_name}_islem_gecmisi.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )

                            display_styled_dataframe(
                                filtered_cust_df,
                                table_key="musteri_gecmis_tablosu",
                                selectable=False,
                            )
                        else:
                            st.warning("Seçilen tarih aralığında bu müşteriye ait kayıt bulunamadı.")
                else:
                    st.warning("Bu müşteriye ait kayıt bulunamadı.")
            else:
                st.error("Tabloda 'Tarih' sütunu bulunamadığı için tarih filtrelemesi yapılamıyor.")

# ==========================================
# 5. MÜŞTERİ BORÇLARI
# ==========================================
elif menu == "💰 Müşteri Borçları":
    st.title("💰 Müşteri Borç Listesi")
    if not df.empty and c_musteri:
        temp_df = df.copy()
        temp_df[c_musteri] = temp_df[c_musteri].fillna("").astype(str).str.strip()
        temp_df = temp_df[temp_df[c_musteri] != ""]

        borc_df = (
            temp_df.groupby(c_musteri, as_index=False)[["Ucret_Clean", "Alinan_Clean", "Kalan_Clean"]].sum()
        )
        borc_df = borc_df[borc_df["Kalan_Clean"] > 0].sort_values(by="Kalan_Clean", ascending=False)

        if not borc_df.empty:
            toplam_borc = borc_df["Kalan_Clean"].sum()
            st.metric("Toplam Açık Müşteri Borcu", f"{toplam_borc:,.2f} ₺")

            formatted_borc = pd.DataFrame(
                {
                    "Müşteri": borc_df[c_musteri],
                    "Toplam Ücret": borc_df["Ucret_Clean"].map(lambda x: f"{x:,.2f} ₺"),
                    "Alınan": borc_df["Alinan_Clean"].map(lambda x: f"{x:,.2f} ₺"),
                    "Kalan Borç": borc_df["Kalan_Clean"].map(lambda x: f"{x:,.2f} ₺"),
                }
            )
            st.dataframe(formatted_borc, use_container_width=True, hide_index=True)
        else:
            st.success("Borcu bulunan müşteri kaydı görünmüyor.")
    else:
        st.info("Bu listede borçları gösterebilmek için müşteri sütunu bulunamadı.")
