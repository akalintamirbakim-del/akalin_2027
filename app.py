# Tutar & Kalan Canlı Önizleme (Form Dışı Anlık Hesap)
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

    # Hızlı Ödeme Kısayolları (Form Dışı - Anında Günceller)
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
