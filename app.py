import io
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from supabase import Client, create_client

st.set_page_config(
    page_title="Akalın Kamyon Tamir İş Takip",
    page_icon="🚛",
    layout="wide",
)


# --- KULLANICI ADI & ŞİFRE KONTROLÜ ---
def check_password() -> bool:
    expected_user = str(st.secrets.get("APP_USERNAME", "admin")).strip().lower()
    expected_pass = str(st.secrets.get("APP_PASSWORD", ""))

    if st.session_state.get("password_correct"):
        return True

    st.subheader("🔒 Lütfen Giriş Yapın")
    with st.form("login_form"):
        entered_user = st.text_input(
            "Kullanıcı Adı",
            autocomplete="username",
            key="login_username_input",
        )
        entered_pass = st.text_input(
            "Şifre",
            type="password",
            autocomplete="current-password",
            key="login_password_input",
        )
        submitted = st.form_submit_button("Giriş Yap", type="primary", use_container_width=True)

    if submitted:
        if entered_user.strip().lower() == expected_user and entered_pass == expected_pass:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("😕 Kullanıcı adı veya şifre yanlış. Lütfen tekrar deneyin.")

    return False


if not check_password():
    st.stop()


# --- SAYI / PARA BİÇİMLENDİRME ---
def fmt_num(val: float) -> str:
    num = float(val or 0.0)
    if num.is_integer():
        return f"{int(num):,}".replace(",", ".")
    formatted = f"{num:,.2f}".rstrip("0").rstrip(".")
    parts = formatted.split(".")
    int_part = parts[0].replace(",", ".")
    return f"{int_part},{parts[1]}" if len(parts) > 1 else int_part


def fmt_tl(val: float) -> str:
    return f"{fmt_num(val)} ₺"


# --- SUPABASE BAĞLANTISI ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


supabase = init_supabase()


def load_data() -> pd.DataFrame:
    try:
        response = (
            supabase.table("islemler")
            .select("*")
            .order("tarih", desc=False)
            .order("id", desc=False)
            .execute()
        )
        data = response.data
        if not data:
            return pd.DataFrame(
                columns=[
                    "id",
                    "tarih",
                    "plaka",
                    "musteri",
                    "marka",
                    "is_tipi",
                    "yapilan_islem",
                    "ucret",
                    "alinan",
                    "kalan",
                ]
            )
        df = pd.DataFrame(data)
        df["Ucret_Clean"] = pd.to_numeric(df["ucret"], errors="coerce").fillna(0.0)
        df["Alinan_Clean"] = pd.to_numeric(df["alinan"], errors="coerce").fillna(0.0)
        df["Kalan_Clean"] = pd.to_numeric(df["kalan"], errors="coerce").fillna(0.0)
        df["Tarih_DT"] = pd.to_datetime(df["tarih"], errors="coerce")

        def get_row_status(row: pd.Series) -> str:
            u_val = float(row.get("Ucret_Clean", 0.0))
            k_val = float(row.get("Kalan_Clean", 0.0))
            if u_val == 0:
                return "Ücret Giriniz"
            if k_val == 0:
                return "Ödendi"
            return "Bekleniyor"

        df["Durum_Etiketi"] = df.apply(get_row_status, axis=1)
        return df
    except Exception as e:
        st.error(f"Supabase veritabanından veri okunamadı: {e}")
        return pd.DataFrame()


df = load_data()


# --- YEDEKLEME YARDIMCILARI ---
def build_excel_backup(source_df: pd.DataFrame) -> bytes:
    export_cols = [
        "id",
        "tarih",
        "plaka",
        "musteri",
        "marka",
        "is_tipi",
        "yapilan_islem",
        "ucret",
        "alinan",
        "kalan",
    ]
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
        "kalan": "Kalan",
    }
    existing = [c for c in export_cols if c in source_df.columns]
    exp_df = source_df[existing].rename(columns=rename_map) if not source_df.empty else pd.DataFrame()

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        exp_df.to_excel(writer, index=False, sheet_name="Tum_Islemler_Yedek")
    return buf.getvalue()


def sync_to_google_sheets(source_df: pd.DataFrame) -> tuple[bool, str]:
    web_app_url = st.secrets.get("WEB_APP_URL")
    api_token = st.secrets.get("API_TOKEN")
    if not web_app_url or not api_token:
        return False, "Secrets içinde WEB_APP_URL veya API_TOKEN bulunamadı."

    rows = []
    for _, r in source_df.iterrows():
        rows.append(
            [
                "" if pd.isna(r.get("tarih")) else str(r.get("tarih")),
                "" if pd.isna(r.get("plaka")) else str(r.get("plaka")),
                "" if pd.isna(r.get("musteri")) else str(r.get("musteri")),
                "" if pd.isna(r.get("marka")) else str(r.get("marka")),
                "" if pd.isna(r.get("is_tipi")) else str(r.get("is_tipi")),
                "" if pd.isna(r.get("yapilan_islem")) else str(r.get("yapilan_islem")),
                float(r.get("Ucret_Clean", 0.0)),
                float(r.get("Alinan_Clean", 0.0)),
                float(r.get("Kalan_Clean", 0.0)),
            ]
        )

    payload = {
        "token": api_token,
        "action": "backup_sync",
        "rows": rows,
    }
    try:
        resp = requests.post(web_app_url, json=payload, timeout=25)
        resp.raise_for_status()
        res_data = resp.json()
        if res_data.get("status") == "success":
            return True, f"{len(rows)} kayıt Google E-Tabloya yedeklendi."
        return False, res_data.get("message", "Bilinmeyen yanıt.")
    except Exception as e:
        return False, f"Yedekleme isteği başarısız: {e}"


# --- YAZDIRILABİLİR SERVİS FİŞİ ---
def render_printable_receipt(row_data: pd.Series) -> None:
    kayit_no = row_data.get("id", "")
    tarih_str = "" if pd.isna(row_data.get("tarih")) else str(row_data.get("tarih"))
    plaka_str = str(row_data.get("plaka") or "-")
    musteri_str = str(row_data.get("musteri") or "-")
    marka_str = str(row_data.get("marka") or "-")
    istipi_str = str(row_data.get("is_tipi") or "-")
    islem_str = str(row_data.get("yapilan_islem") or "-").replace("\n", "<br>")

    ucret_val = float(row_data.get("Ucret_Clean", 0.0))
    alinan_val = float(row_data.get("Alinan_Clean", 0.0))
    kalan_val = float(row_data.get("Kalan_Clean", 0.0))

    ucret_txt = "Ücret Giriniz" if ucret_val == 0 else fmt_tl(ucret_val)
    alinan_txt = fmt_tl(alinan_val)
    kalan_txt = "Bekleniyor" if ucret_val == 0 else ("Ödendi" if kalan_val == 0 else fmt_tl(kalan_val))

    html_doc = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <style>
        body {{
          font-family: Arial, Helvetica, sans-serif;
          color: #111;
          margin: 0;
          padding: 16px;
          background: #fff;
        }}
        .receipt-box {{
          max-width: 720px;
          margin: 0 auto;
          border: 1.5px solid #222;
          border-radius: 8px;
          padding: 20px 24px;
        }}
        .header {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 2px solid #222;
          padding-bottom: 12px;
          margin-bottom: 16px;
        }}
        .title {{
          font-size: 20px;
          font-weight: 700;
        }}
        .meta {{
          text-align: right;
          font-size: 13px;
          color: #444;
        }}
        .info-grid {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px 18px;
          font-size: 14px;
          margin-bottom: 16px;
        }}
        .work-box {{
          border: 1px solid #ccc;
          background: #fafafa;
          border-radius: 6px;
          padding: 12px;
          font-size: 14px;
          line-height: 1.5;
          margin-bottom: 16px;
        }}
        .totals {{
          width: 100%;
          border-collapse: collapse;
          font-size: 14px;
          margin-bottom: 16px;
        }}
        .totals td {{
          padding: 8px 10px;
          border-bottom: 1px solid #ddd;
        }}
        .totals td.val {{
          text-align: right;
          font-weight: 700;
        }}
        .print-btn {{
          background: #1f2937;
          color: #fff;
          border: none;
          padding: 10px 18px;
          font-size: 14px;
          border-radius: 6px;
          cursor: pointer;
        }}
        .footer-note {{
          font-size: 12px;
          color: #666;
          margin-top: 10px;
        }}
        @media print {{
          .no-print {{ display: none !important; }}
          body {{ padding: 0; }}
          .receipt-box {{ border: none; max-width: 100%; }}
        }}
      </style>
    </head>
    <body>
      <div class="no-print" style="max-width:720px; margin:0 auto 12px auto;">
        <button class="print-btn" onclick="window.print()">🖨️ Fişi Yazdır / PDF Kaydet</button>
      </div>
      <div class="receipt-box">
        <div class="header">
          <div class="title">🚛 AKALIN KAMYON TAMİR SERVİSİ</div>
          <div class="meta">
            <strong>Kayıt No:</strong> #{kayit_no}<br>
            <strong>Tarih:</strong> {tarih_str}
          </div>
        </div>
        <div class="info-grid">
          <div><strong>Müşteri / Firma:</strong> {musteri_str}</div>
          <div><strong>Plaka:</strong> {plaka_str}</div>
          <div><strong>Marka / Model:</strong> {marka_str}</div>
          <div><strong>İş Tipi:</strong> {istipi_str}</div>
        </div>
        <div class="work-box">
          <strong>Yapılan İşlem / Değişen Parçalar:</strong><br><br>
          {islem_str}
        </div>
        <table class="totals">
          <tr>
            <td>Toplam Ücret</td>
            <td class="val">{ucret_txt}</td>
          </tr>
          <tr>
            <td>Alınan / Ödenen Tutar</td>
            <td class="val">{alinan_txt}</td>
          </tr>
          <tr>
            <td>Kalan Bakiye / Durum</td>
            <td class="val">{kalan_txt}</td>
          </tr>
        </table>
        <div class="footer-note">
          İş / Tahsilat Bilgilendirme Fişi — Akalın Servis Kayıt Sistemi
        </div>
      </div>
    </body>
    </html>
    """
    components.html(html_doc, height=490, scrolling=True)


# --- TABLO GÖRÜNÜMÜ VE RENKLENDİRME ---
def get_clean_display_df(input_df: pd.DataFrame) -> pd.DataFrame:
    if input_df.empty:
        return input_df
    d_df = input_df.copy()

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
        "kalan": "Kalan",
    }

    zero_ucret_mask = d_df["Ucret_Clean"] == 0
    zero_kalan_mask = (d_df["Kalan_Clean"] == 0) & (~zero_ucret_mask)

    d_df["ucret"] = d_df["Ucret_Clean"].map(fmt_num).astype(object)
    d_df.loc[zero_ucret_mask, "ucret"] = "Ücret Giriniz"

    d_df["alinan"] = d_df["Alinan_Clean"].map(fmt_num).astype(object)

    d_df["kalan"] = d_df["Kalan_Clean"].map(fmt_num).astype(object)
    d_df.loc[zero_ucret_mask, "kalan"] = "Bekleniyor"
    d_df.loc[zero_kalan_mask, "kalan"] = "Ödendi"

    cols_to_show = [
        "id",
        "tarih",
        "plaka",
        "musteri",
        "marka",
        "is_tipi",
        "yapilan_islem",
        "ucret",
        "alinan",
        "kalan",
    ]
    existing_cols = [c for c in cols_to_show if c in d_df.columns]
    return d_df[existing_cols].rename(columns=rename_map)


def display_styled_dataframe(input_df: pd.DataFrame, selectable: bool = False, key: str | None = None):
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
            key=key,
        )
    else:
        st.dataframe(styled, use_container_width=True, hide_index=True)


# --- MENÜ ---
st.sidebar.title("🚛 Akalın Servis")
menu = st.sidebar.radio(
    "Menü",
    [
        "➕ Yeni İş Ekle",
        "📊 Özet Panel",
        "📋 İş Listesi & Arama",
        "🔍 Müşteri & Plaka Geçmişi",
        "💰 Müşteri Borçları",
    ],
)

# ==========================================
# 1. YENİ İŞ EKLE (UI/UX İYİLEŞTİRİLMİŞ)
# ==========================================
if menu == "➕ Yeni İş Ekle":
    st.title("➕ Yeni Araç / İş Ekle")
    st.caption("Kayıtlı araç/müşteri seçerek hızlıca doldurabilir veya doğrudan yeni kayıt açabilirsiniz.")

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

    if st.session_state.pop("reset_new_job_form", False):
        for k, v in defaults.items():
            st.session_state[k] = v
        st.session_state["secilen_arac_box"] = "-- Yeni Kayıt / Manuel Gir --"
        st.session_state["kayit_basarili_bildirim"] = True

    if st.session_state.pop("kayit_basarili_bildirim", False):
        st.success("✅ İş başarıyla veritabanına kaydedildi!")

    known_records = []
    if not df.empty:
        records_df = df[["musteri", "marka", "plaka"]].copy()
        for col in ["musteri", "marka", "plaka"]:
            records_df[col] = records_df[col].fillna("").astype(str).str.strip()
        records_df = records_df[
            (records_df["musteri"] != "") | (records_df["plaka"] != "")
        ].drop_duplicates()
        known_records = records_df.to_dict("records")

    select_options = ["-- Yeni Kayıt / Manuel Gir --"]
    for r in known_records:
        m_val = r.get("musteri", "")
        p_val = r.get("plaka", "")
        mk_val = r.get("marka", "")
        label = " | ".join([part for part in [p_val, m_val] if part])
        if mk_val:
            label = f"{label} ({mk_val})"
        select_options.append(label)

    def on_select_change():
        secim = st.session_state.get("secilen_arac_box")
        if secim and secim != "-- Yeni Kayıt / Manuel Gir --":
            try:
                idx = select_options.index(secim) - 1
                record = known_records[idx]
                st.session_state["form_musteri"] = record.get("musteri", "")
                st.session_state["form_marka"] = record.get("marka", "")
                st.session_state["form_plaka"] = record.get("plaka", "")
            except Exception:
                pass
        else:
            st.session_state["form_musteri"] = ""
            st.session_state["form_marka"] = ""
            st.session_state["form_plaka"] = ""

    with st.container(border=True):
        col_sel, col_clr = st.columns([5, 1])
        with col_sel:
            st.selectbox(
                "🚘 Kayıtlı Araç / Müşteri Seç (Otomatik Doldurur)",
                select_options,
                key="secilen_arac_box",
                on_change=on_select_change,
            )
        with col_clr:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("🧹 Temizle", use_container_width=True):
                st.session_state["reset_new_job_form"] = True
                st.rerun()

    preview_ucret = float(st.session_state.get("form_ucret", 0.0) or 0.0)
    preview_alinan = float(st.session_state.get("form_alinan", 0.0) or 0.0)
    preview_kalan = preview_ucret - preview_alinan

    if preview_ucret == 0:
        durum_ozet = "🔴 Ücret Giriniz (Bekleniyor)"
    elif preview_kalan <= 0:
        durum_ozet = "🟢 Ödendi"
    else:
        durum_ozet = "🟡 Kısmi Ödeme / Açık Bakiye"

    p_col1, p_col2, p_col3 = st.columns(3)
    p_col1.metric("Girilen Ücret", fmt_tl(preview_ucret))
    p_col2.metric("Tahmini Kalan Bakiye", fmt_tl(max(0.0, preview_kalan)))
    p_col3.metric("Kayıt Durumu", durum_ozet)

    h_col1, h_col2, h_col3 = st.columns(3)
    with h_col1:
        if st.button("✅ Tamamı Ödendi", use_container_width=True):
            st.session_state["form_alinan"] = float(st.session_state.get("form_ucret", 0.0) or 0.0)
            st.rerun()
    with h_col2:
        if st.button("🌗 Yarısı Alındı (%50)", use_container_width=True):
            u_curr = float(st.session_state.get("form_ucret", 0.0) or 0.0)
            st.session_state["form_alinan"] = round(u_curr / 2.0, 2)
            st.rerun()
    with h_col3:
        if st.button("↩️ Alınan Sıfırla", use_container_width=True):
            st.session_state["form_alinan"] = 0.0
            st.rerun()

    with st.form("yeni_is_formu"):
        yeni_col1, yeni_col2 = st.columns(2)
        with yeni_col1:
            st.markdown("**🚛 Araç ve Müşteri Bilgileri**")
            plaka = st.text_input("Plaka", placeholder="Örn: 16 ABC 123", key="form_plaka")
            musteri = st.text_input("Müşteri Adı / Firma", placeholder="Örn: Yılmaz Nakliyat", key="form_musteri")
            marka = st.text_input("Marka / Model", placeholder="Örn: Mercedes Axor 1840", key="form_marka")
            is_tipi = st.selectbox("İş Tipi", ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"])
        with yeni_col2:
            st.markdown("**💰 Tarih, Tutar ve İş Detayı**")
            tarih = st.date_input("İş Tarihi", datetime.now(ZoneInfo("Europe/Istanbul")).date())
            ucret = st.number_input("Toplam Ücret (₺)", key="form_ucret", min_value=0.0, step=100.0)
            alinan = st.number_input("Alınan Ödenen (₺)", key="form_alinan", min_value=0.0, step=100.0)
            yapilan_islem = st.text_area(
                "Yapılan İşlem / Değişen Parça",
                placeholder="Yapılan işçilik ve değişen parçaları yazın...",
                height=105,
                key="form_yapilan",
            )

        submit = st.form_submit_button("💾 Kaydet ve Veritabanına Ekle", type="primary", use_container_width=True)

        if submit:
            if not musteri.strip() and not plaka.strip():
                st.warning("Lütfen en azından Müşteri Adı veya Plaka bilgisi girin.")
            else:
                kalan = float(ucret) - float(alinan)
                yeni_kayit = {
                    "tarih": tarih.strftime("%Y-%m-%d"),
                    "plaka": plaka.strip().upper(),
                    "musteri": musteri.strip(),
                    "marka": marka.strip(),
                    "is_tipi": is_tipi,
                    "yapilan_islem": yapilan_islem.strip(),
                    "ucret": float(ucret),
                    "alinan": float(alinan),
                    "kalan": kalan,
                }
                try:
                    supabase.table("islemler").insert(yeni_kayit).execute()
                    st.session_state["reset_new_job_form"] = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Kayıt sırasında hata oluştu: {e}")

# ==========================================
# 2. ÖZET PANEL, UYARI & MANUEL YEDEKLEME
# ==========================================
elif menu == "📊 Özet Panel":
    st.title("📊 Tamirhane Yönetim Paneli")

    if df.empty:
        st.info("Veritabanında henüz kayıt bulunmuyor.")
    else:
        total_is = len(df)
        total_ciro = df["Ucret_Clean"].sum()
        total_alinan = df["Alinan_Clean"].sum()
        total_kalan = df["Kalan_Clean"].sum()
        ucret_bekleyen_df = df[df["Ucret_Clean"] == 0]
        ucret_bekleyen_adet = len(ucret_bekleyen_df)

        ozet_col1, ozet_col2, ozet_col3, ozet_col4, ozet_col5 = st.columns(5)
        ozet_col1.metric("Toplam İş / Araç", f"{total_is}")
        ozet_col2.metric("Toplam Ciro", fmt_tl(total_ciro))
        ozet_col3.metric("Tahsil Edilen", fmt_tl(total_alinan))
        ozet_col4.metric("Kalan Alacak (Borç)", fmt_tl(total_kalan))
        ozet_col5.metric("Ücret Girilmemiş", f"{ucret_bekleyen_adet}")

        if ucret_bekleyen_adet > 0:
            st.warning(
                f"⚠️ **Dikkat:** Ücreti henüz girilmemiş **{ucret_bekleyen_adet}** açık iş kaydı bulunuyor."
            )
            with st.expander(f"🔴 Ücret Girilmesi Beklenen Kayıtları Gör ({ucret_bekleyen_adet})"):
                display_styled_dataframe(ucret_bekleyen_df)

        st.markdown("---")
        st.subheader("💾 Manuel Yedekleme")
        yedek_col1, yedek_col2 = st.columns(2)
        with yedek_col1:
            excel_bytes = build_excel_backup(df)
            tr_simdi = datetime.now(ZoneInfo("Europe/Istanbul"))
            tarih_etiketi = tr_simdi.strftime("%d-%m-%Y_%H-%M")
            st.download_button(
                label="📥 Tüm Verileri Excel (.xlsx) Yedek İndir",
                data=excel_bytes,
                file_name=f"akalin_servis_yedek_{tarih_etiketi}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with yedek_col2:
            if st.button("☁️ Google E-Tablo'ya Şimdi Yedekle", use_container_width=True):
                with st.spinner("E-Tablo yedeği alınıyor..."):
                    ok, msg = sync_to_google_sheets(df)
                if ok:
                    st.success(f"✅ {msg}")
                else:
                    st.warning(msg)

        st.markdown("---")
        st.subheader("Son Eklenen 10 İş")
        display_styled_dataframe(df.tail(10))

# ==========================================
# 3. İŞ LİSTESİ, ARAMA & YAZDIRILABİLİR FİŞ
# ==========================================
elif menu == "📋 İş Listesi & Arama":
    st.title("📋 İş Geçmişi ve Arama")

    if st.session_state.pop("reset_list_filters", False):
        st.session_state["list_year"] = "Tümü"
        st.session_state["list_month"] = "Tümü"
        st.session_state["list_status"] = "Tümü"
        st.session_state["list_search"] = ""

    years = ["Tümü"]
    if not df.empty and "Tarih_DT" in df.columns:
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
    status_options = ["Tümü", "Ücret Giriniz", "Bekleniyor", "Ödendi"]

    f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([1.2, 1.2, 1.4, 2.2, 1.0])
    with f_col1:
        selected_year = st.selectbox("📅 Yıl Seçin", years, key="list_year")
    with f_col2:
        selected_month_name = st.selectbox("🗓️ Ay Seçin", list(months.keys()), key="list_month")
    with f_col3:
        selected_status = st.selectbox("🏷️ Ödeme Durumu", status_options, key="list_status")
    with f_col4:
        search_term = st.text_input("🔍 Müşteri, Plaka veya İşlem Ara:", key="list_search").strip()
    with f_col5:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Sıfırla", use_container_width=True):
            st.session_state["reset_list_filters"] = True
            st.session_state.pop("is_listesi_tablosu", None)
            st.rerun()

    filtered_df = df.copy()
    if not filtered_df.empty and "Tarih_DT" in filtered_df.columns:
        if selected_year != "Tümü":
            filtered_df = filtered_df[filtered_df["Tarih_DT"].dt.year == selected_year]
        if selected_month_name != "Tümü":
            m_num = months[selected_month_name]
            filtered_df = filtered_df[filtered_df["Tarih_DT"].dt.month == m_num]

    if selected_status != "Tümü" and not filtered_df.empty and "Durum_Etiketi" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Durum_Etiketi"] == selected_status]

    if search_term and not filtered_df.empty:
        search_cols = ["plaka", "musteri", "marka", "yapilan_islem", "is_tipi"]
        mask = (
            filtered_df[search_cols]
            .astype(str)
            .apply(lambda x: x.str.contains(search_term, case=False, na=False))
            .any(axis=1)
        )
        filtered_df = filtered_df[mask]

    if not filtered_df.empty:
        filtered_df = filtered_df.sort_values(by=["Tarih_DT", "id"], ascending=[True, True]).reset_index(
            drop=True
        )

        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        s_col1.metric("Filtrelenen İş", f"{len(filtered_df)}")
        s_col2.metric("Toplam Ücret", fmt_tl(filtered_df["Ucret_Clean"].sum()))
        s_col3.metric("Alınan Toplam", fmt_tl(filtered_df["Alinan_Clean"].sum()))
        s_col4.metric("Kalan Bakiye", fmt_tl(filtered_df["Kalan_Clean"].sum()))

        st.info(
            "💡 **İpucu:** Tablodaki bir satıra tıklayarak seçebilir, hemen aşağıdaki alandan düzenleyebilir, silebilir veya yazdırılabilir fiş alabilirsiniz."
        )

        display_styled_dataframe(filtered_df, selectable=True, key="is_listesi_tablosu")

        selected_rows = []
        selection_state = st.session_state.get("is_listesi_tablosu")
        if (
            selection_state is not None
            and hasattr(selection_state, "selection")
            and hasattr(selection_state.selection, "rows")
        ):
            selected_rows = selection_state.selection.rows

        if selected_rows:
            selected_relative_idx = selected_rows[0]
            if selected_relative_idx < len(filtered_df):
                row_data = filtered_df.iloc[selected_relative_idx]
                kayit_id = int(row_data["id"])

                st.markdown("---")
                st.success(
                    f"📌 **Seçilen Kayıt No:** #{kayit_id} | Plaka: `{row_data.get('plaka', '')}` | Müşteri: `{row_data.get('musteri', '')}`"
                )

                ex_musteri = str(row_data.get("musteri") or "")
                ex_marka = str(row_data.get("marka") or "")
                ex_plaka = str(row_data.get("plaka") or "")
                ex_islem = str(row_data.get("yapilan_islem") or "")
                ex_ucret = float(row_data.get("Ucret_Clean", 0.0))
                ex_alinan = float(row_data.get("Alinan_Clean", 0.0))

                is_tipi_secenekleri = ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"]
                ex_istipi_val = str(row_data.get("is_tipi") or "")
                istipi_index = 0
                for i, opt in enumerate(is_tipi_secenekleri):
                    if ex_istipi_val and (
                        ex_istipi_val.lower() in opt.lower() or opt.lower() in ex_istipi_val.lower()
                    ):
                        istipi_index = i
                        break

                ex_tarih = datetime.now(ZoneInfo("Europe/Istanbul")).date()
                if pd.notna(row_data.get("Tarih_DT")):
                    ex_tarih = row_data["Tarih_DT"].date()

                tab_duzenle, tab_fis, tab_sil = st.tabs(
                    ["✏️ Seçilen Kaydı Güncelle", "🧾 Yazdırılabilir Fiş / Özet", "🗑️ Seçilen Kaydı Sil"]
                )

                with tab_duzenle:
                    u_key = f"edit_ucret_{kayit_id}"
                    a_key = f"edit_alinan_{kayit_id}"
                    if u_key not in st.session_state:
                        st.session_state[u_key] = ex_ucret
                    if a_key not in st.session_state:
                        st.session_state[a_key] = ex_alinan

                    q_col1, q_col2, q_col3 = st.columns([1.2, 1.2, 2.6])
                    with q_col1:
                        if st.button("✅ Tamamı Ödendi", key=f"q_paid_{kayit_id}", use_container_width=True):
                            st.session_state[a_key] = float(st.session_state.get(u_key, ex_ucret) or 0.0)
                            st.rerun()
                    with q_col2:
                        if st.button("↩️ Alınan Sıfırla", key=f"q_zero_{kayit_id}", use_container_width=True):
                            st.session_state[a_key] = 0.0
                            st.rerun()
                    with q_col3:
                        cur_edit_u = float(st.session_state.get(u_key, 0.0) or 0.0)
                        cur_edit_a = float(st.session_state.get(a_key, 0.0) or 0.0)
                        st.caption(
                            f"Güncel Kalan Bakiye: **{fmt_tl(max(0.0, cur_edit_u - cur_edit_a))}**"
                        )

                    with st.form(f"tiklanan_duzenleme_formu_{kayit_id}"):
                        d_kol1, d_kol2 = st.columns(2)
                        with d_kol1:
                            d_plaka = st.text_input("Plaka", value=ex_plaka)
                            d_musteri = st.text_input("Müşteri Adı / Firma", value=ex_musteri)
                            d_marka = st.text_input("Marka / Model", value=ex_marka)
                            d_is_tipi = st.selectbox("İş Tipi", is_tipi_secenekleri, index=istipi_index)
                        with d_kol2:
                            d_tarih = st.date_input("İş Tarihi", value=ex_tarih)
                            d_ucret = st.number_input(
                                "Toplam Ücret (₺)", key=u_key, min_value=0.0, step=100.0
                            )
                            d_alinan = st.number_input(
                                "Alınan Ödenen (₺)", key=a_key, min_value=0.0, step=100.0
                            )
                            d_yapilan_islem = st.text_area(
                                "Yapılan İşlem / Değişen Parça", value=ex_islem
                            )

                        guncelle_btn = st.form_submit_button("💾 Değişiklikleri Kaydet ve Güncelle")

                        if guncelle_btn:
                            d_kalan = float(d_ucret) - float(d_alinan)
                            guncel_veri = {
                                "tarih": d_tarih.strftime("%Y-%m-%d"),
                                "plaka": d_plaka.strip().upper(),
                                "musteri": d_musteri.strip(),
                                "marka": d_marka.strip(),
                                "is_tipi": d_is_tipi,
                                "yapilan_islem": d_yapilan_islem.strip(),
                                "ucret": float(d_ucret),
                                "alinan": float(d_alinan),
                                "kalan": d_kalan,
                            }
                            try:
                                supabase.table("islemler").update(guncel_veri).eq("id", kayit_id).execute()
                                st.session_state.pop("is_listesi_tablosu", None)
                                st.session_state.pop(u_key, None)
                                st.session_state.pop(a_key, None)
                                st.success("✅ Kayıt anında güncellendi!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Güncelleme hatası: {e}")

                with tab_fis:
                    render_printable_receipt(row_data)

                with tab_sil:
                    st.warning(
                        f"Seçilen kayıt (#{kayit_id} - {ex_plaka}) veritabanından kalıcı olarak silinecektir."
                    )
                    sil_onay = st.checkbox(
                        "Bu kaydı kalıcı olarak silmek istediğimi onaylıyorum.",
                        key=f"del_confirm_{kayit_id}",
                    )
                    if st.button("🚨 Seçilen Kaydı Kalıcı Olarak Sil", type="primary", disabled=not sil_onay):
                        try:
                            supabase.table("islemler").delete().eq("id", kayit_id).execute()
                            st.session_state.pop("is_listesi_tablosu", None)
                            st.success("🗑️ Kayıt kalıcı olarak silindi!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Silme hatası: {e}")
        else:
            st.info(
                "👆 İşlem yapmak istediğiniz satıra tablonun en solundaki kutucuktan tıklayarak seçin."
            )
    else:
        st.info("Arama kriterlerinize uygun kayıt bulunamadı.")

# ==========================================
# 4. MÜŞTERİ & PLAKA GEÇMİŞİ
# ==========================================
elif menu == "🔍 Müşteri & Plaka Geçmişi":
    st.title("🔍 Müşteri ve Plaka Bazlı İşlem Geçmişi")

    if df.empty:
        st.info("Veritabanında henüz kayıt bulunmuyor.")
    else:
        gecmis_tab1, gecmis_tab2 = st.tabs(["👤 Müşteri Geçmişi", "🚘 Plaka Bazlı Geçmiş"])

        with gecmis_tab1:
            unique_customers = sorted(df["musteri"].dropna().astype(str).str.strip().unique().tolist())
            unique_customers = [c for c in unique_customers if c != ""]
            unique_customers.insert(0, "-- Müşteri Seçiniz --")

            selected_cust = st.selectbox("Rapor Alınacak Müşteriyi Seçin:", unique_customers)

            if selected_cust != "-- Müşteri Seçiniz --":
                cust_df = df[df["musteri"].astype(str).str.strip() == selected_cust].copy()

                if not cust_df.empty:
                    min_date = cust_df["Tarih_DT"].min()
                    max_date = cust_df["Tarih_DT"].max()

                    today_tr = datetime.now(ZoneInfo("Europe/Istanbul")).date()
                    min_date = today_tr if pd.isna(min_date) else min_date.date()
                    max_date = today_tr if pd.isna(max_date) else max_date.date()

                    st.markdown("---")
                    tarih_col1, tarih_col2 = st.columns(2)
                    with tarih_col1:
                        start_date = st.date_input("Başlangıç Tarihi", value=min_date, key="m_start")
                    with tarih_col2:
                        end_date = st.date_input("Bitiş Tarihi", value=max_date, key="m_end")

                    if start_date > end_date:
                        st.error("Başlangıç tarihi bitiş tarihinden büyük olamaz.")
                    else:
                        mask = (cust_df["Tarih_DT"].dt.date >= start_date) & (
                            cust_df["Tarih_DT"].dt.date <= end_date
                        )
                        filtered_cust_df = cust_df[mask].sort_values(
                            by=["Tarih_DT", "id"], ascending=[True, True]
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
                            m_col2.metric("Toplam Ücret", fmt_tl(t_ciro))
                            m_col3.metric("Ödenen", fmt_tl(t_alinan))
                            m_col4.metric("Kalan Borç", fmt_tl(t_kalan))

                            st.markdown("---")
                            display_df = get_clean_display_df(filtered_cust_df)

                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                                display_df.to_excel(writer, index=False, sheet_name="Müşteri Geçmişi")
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

        with gecmis_tab2:
            unique_plates = sorted(
                df["plaka"].dropna().astype(str).str.strip().str.upper().unique().tolist()
            )
            unique_plates = [p for p in unique_plates if p != ""]
            unique_plates.insert(0, "-- Plaka Seçiniz --")

            selected_plate = st.selectbox("Geçmişi Görüntülenecek Plakayı Seçin:", unique_plates)

            if selected_plate != "-- Plaka Seçiniz --":
                plate_df = df[
                    df["plaka"].astype(str).str.strip().str.upper() == selected_plate
                ].sort_values(by=["Tarih_DT", "id"], ascending=[False, False])

                if not plate_df.empty:
                    p_is = len(plate_df)
                    p_ciro = plate_df["Ucret_Clean"].sum()
                    p_alinan = plate_df["Alinan_Clean"].sum()
                    p_kalan = plate_df["Kalan_Clean"].sum()
                    marka_bilgi = ", ".join(
                        sorted(
                            [
                                m
                                for m in plate_df["marka"].dropna().astype(str).str.strip().unique()
                                if m
                            ]
                        )
                    )

                    st.markdown("---")
                    if marka_bilgi:
                        st.caption(f"Kayıtlı Marka / Model: **{marka_bilgi}**")

                    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
                    p_col1.metric("Toplam Servis Girişi", f"{p_is}")
                    p_col2.metric("Toplam İşlem Tutarı", fmt_tl(p_ciro))
                    p_col3.metric("Ödenen", fmt_tl(p_alinan))
                    p_col4.metric("Kalan Borç", fmt_tl(p_kalan))

                    st.markdown("---")
                    display_styled_dataframe(plate_df)

# ==========================================
# 5. MÜŞTERİ BORÇLARI & HIZLI TAHSİLAT
# ==========================================
elif menu == "💰 Müşteri Borçları":
    st.title("💰 Müşteri Borç Listesi")
    if not df.empty:
        temp_df = df.copy()
        temp_df["musteri"] = temp_df["musteri"].fillna("").astype(str).str.strip()
        temp_df = temp_df[temp_df["musteri"] != ""]

        borc_df = (
            temp_df.groupby("musteri", as_index=False)[
                ["Ucret_Clean", "Alinan_Clean", "Kalan_Clean"]
            ].sum()
        )
        borc_df = borc_df[borc_df["Kalan_Clean"] > 0].sort_values(
            by="Kalan_Clean", ascending=False
        )

        if not borc_df.empty:
            st.metric("Toplam Açık Müşteri Borcu", fmt_tl(borc_df["Kalan_Clean"].sum()))

            formatted_borc = pd.DataFrame(
                {
                    "Müşteri": borc_df["musteri"],
                    "Toplam Ücret": borc_df["Ucret_Clean"].map(fmt_tl),
                    "Alınan": borc_df["Alinan_Clean"].map(fmt_tl),
                    "Kalan Borç": borc_df["Kalan_Clean"].map(fmt_tl),
                }
            )
            st.dataframe(formatted_borc, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("💳 Hızlı Tahsilat / Ödeme Ekle")

            secili_borclu = st.selectbox(
                "Tahsilat Yapılacak Müşteriyi Seçin:", borc_df["musteri"].tolist()
            )
            cust_debt_rows = temp_df[
                (temp_df["musteri"] == secili_borclu) & (temp_df["Kalan_Clean"] > 0)
            ].sort_values(by=["Tarih_DT", "id"], ascending=[True, True])

            if not cust_debt_rows.empty:
                target_row = cust_debt_rows.iloc[0]
                target_id = int(target_row["id"])
                cur_ucret = float(target_row["Ucret_Clean"])
                cur_alinan = float(target_row["Alinan_Clean"])
                cur_kalan = float(target_row["Kalan_Clean"])

                st.info(
                    f"Hedef Kayıt **#{target_id}** | Plaka: `{target_row.get('plaka', '')}` | "
                    f"Tarih: `{target_row.get('tarih', '')}` | Kalan Borç: `{fmt_tl(cur_kalan)}`"
                )

                with st.form("hizli_tahsilat_formu"):
                    tahsilat_tutari = st.number_input(
                        "Alınan Tahsilat Tutarı (₺)",
                        min_value=0.0,
                        max_value=cur_kalan,
                        value=0.0,
                        step=100.0,
                    )
                    if st.form_submit_button("✅ Tahsilatı Kaydet"):
                        if tahsilat_tutari <= 0:
                            st.warning("Lütfen 0'dan büyük bir tutar girin.")
                        else:
                            yeni_alinan = cur_alinan + float(tahsilat_tutari)
                            yeni_kalan = max(0.0, cur_ucret - yeni_alinan)
                            try:
                                supabase.table("islemler").update(
                                    {"alinan": yeni_alinan, "kalan": yeni_kalan}
                                ).eq("id", target_id).execute()
                                st.success(
                                    f"✅ {fmt_tl(tahsilat_tutari)} tahsilat #{target_id} numaralı kayda işlendi!"
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(f"Tahsilat kaydedilirken hata oluştu: {e}")
        else:
            st.success("Borcu bulunan müşteri kaydı görünmüyor.")
    else:
        st.info("Veritabanında henüz kayıt bulunmuyor.")
