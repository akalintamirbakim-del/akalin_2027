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
        
    # Ana Temiz Tablo Görünümü
    display_styled_dataframe(filtered_df)
    
    if not df.empty:
        st.markdown("---")
        st.subheader("⚙️ Seçili Kayıt İşlemleri (Düzenle / Sil)")
        
        islem_secenekleri = []
        islem_map = {}
        
        secim_kaynagi = filtered_df if not filtered_df.empty else df
        for idx, row in secim_kaynagi.iterrows():
            tarih_val = str(row.get('Tarih', ''))
            plaka_val = str(row.get(c_plaka, '')) if c_plaka else ''
            musteri_val = str(row.get(c_musteri, '')) if c_musteri else ''
            islem_val = str(row.get(c_islem, '')) if c_islem else ''
            
            label = f"Satır {idx+1} | Tarih: {tarih_val} | Plaka: {plaka_val} | Müşteri: {musteri_val} | {islem_val[:25]}"
            islem_secenekleri.append(label)
            islem_map[label] = (idx, row)

        secilen_islem_kaydi = st.selectbox("İşlem yapmak istediğiniz kaydı listeden seçin:", ["-- Seçiniz --"] + islem_secenekleri)

        if secilen_islem_kaydi != "-- Seçiniz --":
            gercek_idx, row_data = islem_map[secilen_islem_kaydi]
            
            def get_val(col_key, default=""):
                if col_key and col_key in row_data:
                    val = row_data[col_key]
                    return "" if pd.isna(val) else str(val)
                return default

            ex_musteri = get_val(c_musteri)
            ex_marka = get_val(c_marka)
            ex_plaka = get_val(c_plaka)
            ex_islem = get_val(c_islem)
            ex_ucret = float(row_data.get('Ucret_Clean', 0.0))
            ex_alinan = float(row_data.get('Alinan_Clean', 0.0))
            
            is_tipi_secenekleri = ["İşçilik (İ)", "İşçilik+Parça (İS)", "Satış (S)"]
            ex_istipi_val = get_val(c_istipi)
            istipi_index = 0
            for i, opt in enumerate(is_tipi_secenekleri):
                if ex_istipi_val.lower() in opt.lower() or opt.lower() in ex_istipi_val.lower():
                    istipi_index = i
                    break
            
            ex_tarih = datetime.now().date()
            if 'Tarih_DT' in row_data and pd.notna(row_data['Tarih_DT']):
                ex_tarih = row_data['Tarih_DT'].date()
            elif 'Tarih' in row_data and pd.notna(row_data['Tarih']):
                parsed_date = pd.to_datetime(row_data['Tarih'], errors='coerce')
                if pd.notna(parsed_date):
                    ex_tarih = parsed_date.date()

            tab_duzenle, tab_sil = st.tabs(["✏️ Bu Kaydı Güncelle", "🗑️ Bu Kaydı Sil"])
            
            with tab_duzenle:
                with st.form("temiz_duzenleme_formu"):
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
                        
                    guncelle_btn = st.form_submit_button("💾 Değişiklikleri Kaydet")
                    
                    if guncelle_btn:
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

            with tab_sil:
                st.warning(f"Seçilen kayıt (Satır {gercek_idx+2}) Google E-Tablo'dan kalıcı olarak silinecektir.")
                if st.button("🚨 Seçilen Kaydı Kalıcı Olarak Sil", type="primary"):
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
                            st.success("Kayıt başarıyla silindi!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"Silme başarısız: {res_data.get('message', 'Bilinmeyen hata')}")
                    except Exception as e:
                        st.error(f"Bağlantı hatası oluştu: {e}")
