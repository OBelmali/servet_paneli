import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import uuid
from datetime import datetime

# --- SAYFA VE PANEL AYARLARI ---
st.set_page_config(page_title="Kişisel Finans Yönetim Paneli", page_icon="📈", layout="wide")

# --- KESİNLİKLE DEĞİŞMEZ VARSAYILAN ŞABLON (İLK AÇILIŞ KORUMASI) ---
DEFAULT_DATA = {
    "ayarlar": {"USD": 32.50, "EUR": 35.20},
    "varliklar": {
        "kisa_vadeli": [],
        "stoklar": [],
        "orta_vadeli": [],
        "nakit": {
            "cuzdan": {"TRY": 0.0, "USD": 0.0, "EUR": 0.0},
            "banka": {"TRY": 0.0, "USD": 0.0, "EUR": 0.0},
            "guncelleme_tarihi": str(datetime.now().date())
        }
    },
    "borclar": {
        "kart_borclari": [],
        "yolcu_odemeleri": [],
        "uzun_vadeli": []
    }
}

# --- DEFANSİF VERİTABANI BAĞLANTI FONKSİYONLARI (JSON BLOB METODU) ---
def load_database():
    """Sheet1 A1 hüresindeki JSON objesini okur, yoksa varsayılan şablon döner."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        # Sadece ilk satır ve ilk sütun (A1) okunuyor
        df = conn.read(worksheet="Sheet1", usecols=[0], nrows=1)
        if not df.empty and pd.notna(df.iloc[0, 0]):
            return json.loads(df.iloc[0, 0])
        else:
            return DEFAULT_DATA
    except Exception as e:
        # Bağlantı hatalarında veya ilk kurulumda çökme önleyici koruma
        return DEFAULT_DATA

def save_database(data):
    """Tüm veriyi tek bir JSON string'ine dönüştürüp A1 hüresine mühürler."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        json_string = json.dumps(data, ensure_ascii=False)
        df = pd.DataFrame([[json_string]], columns=["Veritabanı_Blob"])
        conn.update(worksheet="Sheet1", data=df)
        st.success("Değişiklikler Google Sheets bulutuna başarıyla işlendi.")
    except Exception as e:
        st.error(f"Veritabanına yazılırken kritik hata oluştu: {e}")

# --- SEANS DURUMU YÖNETİMİ ---
if "db" not in st.session_state:
    st.session_state.db = load_database()

db = st.session_state.db

# --- DÖVİZ KUR HESAPLAMA MOTORU ---
def para_cevir(miktar, kaynak_doviz, hedef_doviz="TRY"):
    usd_kuru = db["ayarlar"].get("USD", 32.50)
    eur_kuru = db["ayarlar"].get("EUR", 35.20)
    
    # Önce TRY karşılığını bulalım
    if kaynak_doviz == "TRY":
        try_karsiligi = miktar
    elif kaynak_doviz == "USD":
        try_karsiligi = miktar * usd_kuru
    elif kaynak_doviz == "EUR":
        try_karsiligi = miktar * eur_kuru
    else:
        try_karsiligi = miktar
        
    # İstenen hedef birime dönüştürelim
    if hedef_doviz == "TRY":
        return try_karsiligi
    elif hedef_doviz == "USD":
        return try_karsiligi / usd_kuru if usd_kuru > 0 else 0
    elif hedef_doviz == "EUR":
        return try_karsiligi / eur_kuru if eur_kuru > 0 else 0
    return try_karsiligi

# --- SİLME MEKANİZMASI (POP FONKSİYONU) ---
def oge_sil(ana_kategori, alt_kategori, oge_id):
    db[ana_kategori][alt_kategori] = [oge for oge in db[ana_kategori][alt_kategori] if oge["id"] != oge_id]
    save_database(db)
    st.rerun()

# ==========================================
# MODÜL 1: FİNANSAL DASHBOARD & BİLANÇO
# ==========================================
def render_dashboard():
    st.title("📊 Finansal Analiz ve Bilanço")
    
    # Kur Güncelleme Formu
    with st.expander("💱 Manuel Döviz Kuru Ayarları", expanded=False):
        with st.form("kur_form"):
            col1, col2 = st.columns(2)
            yeni_usd = col1.number_input("USD / TRY", value=float(db["ayarlar"]["USD"]), step=0.01, format="%.4f")
            yeni_eur = col2.number_input("EUR / TRY", value=float(db["ayarlar"]["EUR"]), step=0.01, format="%.4f")
            if st.form_submit_button("Kurları Güncelle ve Kilitle"):
                db["ayarlar"]["USD"] = yeni_usd
                db["ayarlar"]["EUR"] = yeni_eur
                save_database(db)
                st.rerun()

    # Varlık Hesaplama Toplamları
    toplam_varlik_try = 0.0
    
    # Nakit varlıkların eklenmesi
    for konum in ["cuzdan", "banka"]:
        for doviz, miktar in db["varliklar"]["nakit"][konum].items():
            toplam_varlik_try += para_cevir(miktar, doviz, "TRY")
            
    # Dinamik varlık listelerinin eklenmesi
    for alt in ["kisa_vadeli", "stoklar", "orta_vadeli"]:
        for oge in db["varliklar"][alt]:
            toplam_varlik_try += para_cevir(oge["miktar"], oge["doviz"], "TRY")
            
    # Borç Hesaplama Toplamları
    toplam_borc_try = 0.0
    for alt in ["kart_borclari", "yolcu_odemeleri", "uzun_vadeli"]:
        for oge in db["borclar"][alt]:
            toplam_borc_try += para_cevir(oge["miktar"], oge["doviz"], "TRY")

    net_durum_try = toplam_varlik_try - toplam_borc_try
    net_durum_usd = para_cevir(net_durum_try, "TRY", "USD")

    # KPI Kartları Görünümü
    st.markdown("### Anlık Bilanço Durumu")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Toplam Varlıklar (Yatırım + Nakit)", f"₺{toplam_varlik_try:,.2f}")
    kpi2.metric("Toplam Yükümlülükler (Borçlar)", f"₺{toplam_borc_try:,.2f}", delta_color="inverse")
    kpi3.metric("Net Finansal Pozisyon (TRY)", f"₺{net_durum_try:,.2f}", delta=f"${net_durum_usd:,.2f} USD")

    st.markdown("---")
    st.markdown("### 📈 Net Bütçe Gelişim Grafiği (Kronolojik)");
    
    # KRONOLOJİK GRAFİK MOTORU OLUŞTURMA
    zaman_serisi = []
    
    # Sabit nakit durumunu nakit güncelleme tarihiyle ekle
    nakit_tarih = db["varliklar"]["nakit"].get("guncelleme_tarihi", str(datetime.now().date()))
    nakit_try_toplam = sum(para_cevir(m, d, "TRY") for d, m in db["varliklar"]["nakit"]["cuzdan"].items()) + \
                       sum(para_cevir(m, d, "TRY") for d, m in db["varliklar"]["nakit"]["banka"].items())
    zaman_serisi.append({"tarih": nakit_tarih, "tip": "varlik", "tl_deger": nakit_try_toplam})
    
    # Tüm varlık hareketlerinin tarihsel analizi
    for alt in ["kisa_vadeli", "stoklar", "orta_vadeli"]:
        for oge in db["varliklar"][alt]:
            zaman_serisi.append({"tarih": oge["tarih"], "tip": "varlik", "tl_deger": para_cevir(oge["miktar"], oge["doviz"], "TRY")})
            
    # Tüm borç hareketlerinin tarihsel analizi
    for alt in ["kart_borclari", "yolcu_odemeleri", "uzun_vadeli"]:
        for oge in db["borclar"][alt]:
            # Borçlar net durumu aşağı çekeceği için eksi değerle simüle edilir
            zaman_serisi.append({"tarih": oge["tarih"], "tip": "borc", "tl_deger": -para_cevir(oge["miktar"], oge["doviz"], "TRY")})

    if zaman_serisi:
        df_zaman = pd.DataFrame(zaman_serisi)
        df_zaman["tarih"] = pd.to_datetime(df_zaman["tarih"])
        # Gün bazlı kümülatif gruplama yapıp net bütçe gelişim çizgisi oluşturulur
        df_grouped = df_zaman.groupby("tarih")["tl_deger"].sum().reset_index().sort_values("tarih")
        df_grouped["Kümülâtif Net Bütçe (TRY)"] = df_grouped["tl_deger"].cumsum()
        df_grouped.set_index("tarih", inplace=True)
        
        st.line_chart(df_grouped["Kümülâtif Net Bütçe (TRY)"])
    else:
        st.info("Zaman grafiğinin çizilebilmesi için sisteme en az bir adet tarihli kayıt girmelisiniz.")

# ==========================================
# MODÜL 2: ALINACAKLAR VE VARLIKLAR
# ==========================================
def render_varliklar():
    st.title("💰 Varlık Yönetimi ve Alacaklar")
    sekme1, sekme2, sekme3, sekme4 = st.tabs([
        "📅 Kısa Vadeli Alacaklar", "📦 Stoklar ve Değerler", "⏳ Orta Vadeli Alacaklar", "💵 Nakit Durumu"
    ])
    
    with sekme1:
        st.subheader("1 Hafta Vadeli Alacak Girişi")
        with st.form("kisa_vadeli_form"):
            tarih = st.date_input("Kayıt Tarihi", datetime.now().date())
            aciklama = st.text_input("Alacak Detayı (Kimden/Neyin Ödemesi?)")
            col1, col2 = st.columns(2)
            miktar = col1.number_input("Miktar", min_value=0.0, step=0.01)
            doviz = col2.selectbox("Döviz Tipi", ["TRY", "USD", "EUR"], key="kv_d")
            if st.form_submit_button("Kısa Vadeli Alacak Ekle"):
                if aciklama:
                    yeni_oge = {
                        "id": str(uuid.uuid4()), "tarih": str(tarih), "aciklama": aciklama,
                        "miktar": miktar, "doviz": doviz
                    }
                    db["varliklar"]["kisa_vadeli"].append(yeni_oge)
                    save_database(db)
                    st.rerun()
                else:
                    st.error("Lütfen açıklama alanını boş bırakmayın.")

        # Listeleme ve Pop/Silme Alanı
        for oge in db["varliklar"]["kisa_vadeli"]:
            col_t, col_s = st.columns([5, 1])
            col_t.markdown(f"📅 **{oge['tarih']}** | {oge['aciklama']}: **{oge['miktar']:,} {oge['doviz']}**")
            if col_s.button("🗑️ Sil", key=f"del_kv_{oge['id']}"):
                oge_sil("varliklar", "kisa_vadeli", oge["id"])

    with sekme2:
        st.subheader("Eldeki Emtia, Ürün ve Fiziksel Stok Değerleri")
        with st.form("stok_form"):
            tarih = st.date_input("Değerleme Tarihi", datetime.now().date())
            aciklama = st.text_input("Varlık / Ürün Adı")
            col1, col2 = st.columns(2)
            miktar = col1.number_input("Piyasa Karşılığı Değeri", min_value=0.0, step=0.01)
            doviz = col2.selectbox("Döviz Tipi", ["TRY", "USD", "EUR"], key="st_d")
            if st.form_submit_button("Stok Değeri Ekle"):
                if aciklama:
                    yeni_oge = {
                        "id": str(uuid.uuid4()), "tarih": str(tarih), "aciklama": aciklama,
                        "miktar": miktar, "doviz": doviz
                    }
                    db["varliklar"]["stoklar"].append(yeni_oge)
                    save_database(db)
                    st.rerun()

        for oge in db["varliklar"]["stoklar"]:
            col_t, col_s = st.columns([5, 1])
            col_t.markdown(f"📦 **{oge['tarih']}** | {oge['aciklama']}: **{oge['miktar']:,} {oge['doviz']}**")
            if col_s.button("🗑️ Sil", key=f"del_st_{oge['id']}"):
                oge_sil("varliklar", "stoklar", oge["id"])

    with sekme3:
        st.subheader("Orta Vadeli Alacak Hesapları")
        with st.form("orta_vadeli_form"):
            tarih = st.date_input("Vade/Giriş Tarihi", datetime.now().date())
            aciklama = st.text_input("Açıklama / Borçlu")
            col1, col2 = st.columns(2)
            miktar = col1.number_input("Tutar", min_value=0.0, step=0.01)
            doviz = col2.selectbox("Döviz Tipi", ["TRY", "USD", "EUR"], key="ov_d")
            if st.form_submit_button("Orta Vadeli Alacak Ekle"):
                if aciklama:
                    yeni_oge = {
                        "id": str(uuid.uuid4()), "tarih": str(tarih), "aciklama": aciklama,
                        "miktar": miktar, "doviz": doviz
                    }
                    db["varliklar"]["orta_vadeli"].append(yeni_oge)
                    save_database(db)
                    st.rerun()

        for oge in db["varliklar"]["orta_vadeli"]:
            col_t, col_s = st.columns([5, 1])
            col_t.markdown(f"⏳ **{oge['tarih']}** | {oge['aciklama']}: **{oge['miktar']:,} {oge['doviz']}**")
            if col_s.button("🗑️ Sil", key=f"del_ov_{oge['id']}"):
                oge_sil("varliklar", "orta_vadeli", oge["id"])

    with sekme4:
        st.subheader("Likit Nakit Durumu (Cüzdan ve Bankalar)")
        with st.form("nakit_form"):
            tarih_nakit = st.date_input("Nakit Sayım Tarihi", datetime.now().date())
            st.markdown("#### 👛 Cüzdan (Eldeki Nakit)")
            c_try = st.number_input("Cüzdan - TRY", value=float(db["varliklar"]["nakit"]["cuzdan"].get("TRY", 0.0)), step=0.01)
            c_usd = st.number_input("Cüzdan - USD", value=float(db["varliklar"]["nakit"]["cuzdan"].get("USD", 0.0)), step=0.01)
            c_eur = st.number_input("Cüzdan - EUR", value=float(db["varliklar"]["nakit"]["cuzdan"].get("EUR", 0.0)), step=0.01)
            
            st.markdown("#### 🏦 Banka Hesapları")
            b_try = st.number_input("Banka - TRY", value=float(db["varliklar"]["nakit"]["banka"].get("TRY", 0.0)), step=0.01)
            b_usd = st.number_input("Banka - USD", value=float(db["varliklar"]["nakit"]["banka"].get("USD", 0.0)), step=0.01)
            b_eur = st.number_input("Banka - EUR", value=float(db["varliklar"]["nakit"]["banka"].get("EUR", 0.0)), step=0.01)
            
            if st.form_submit_button("Nakit Pozisyonlarını Güncelle"):
                db["varliklar"]["nakit"]["cuzdan"] = {"TRY": c_try, "USD": c_usd, "EUR": c_eur}
                db["varliklar"]["nakit"]["banka"] = {"TRY": b_try, "USD": b_usd, "EUR": b_eur}
                db["varliklar"]["nakit"]["guncelleme_tarihi"] = str(tarih_nakit)
                save_database(db)
                st.rerun()

# ==========================================
# MODÜL 3: BORÇLAR VE YÜKÜMLÜLÜKLER
# ==========================================
def render_borclar():
    st.title("💳 Yükümlülük Yönetimi ve Borçlar")
    sekme1, sekme2, sekme3 = st.tabs([
        "💳 Kart Borçları", "✈️ Yolcu Ödemeleri", "🏦 Orta ve Uzun Vadeli Borçlar"
    ])

    with sekme1:
        st.subheader("Kredi Kartı Ekstre ve Dönem Borçları")
        with st.form("kart_form"):
            tarih = st.date_input("Kayıt Tarihi", datetime.now().date())
            kart_adi = st.text_input("Kredi Kartı İsmi")
            col1, col2 = st.columns(2)
            miktar = col1.number_input("Ekstre / Borç Tutarı", min_value=0.0, step=0.01)
            doviz = col2.selectbox("Döviz Tipi", ["TRY", "USD", "EUR"], key="cc_d")
            son_odeme = st.date_input("Son Ödeme Vadesi", datetime.now().date())
            if st.form_submit_button("Kart Borcu Kaydet"):
                if kart_adi:
                    yeni_oge = {
                        "id": str(uuid.uuid4()), "tarih": str(tarih), "kart_adi": kart_adi,
                        "miktar": miktar, "doviz": doviz, "son_odeme": str(son_odeme)
                    }
                    db["borclar"]["kart_borclari"].append(yeni_oge)
                    save_database(db)
                    st.rerun()

        for oge in db["borclar"]["kart_borclari"]:
            col_t, col_s = st.columns([5, 1])
            col_t.markdown(f"💳 **{oge['tarih']}** | {oge['kart_adi']} (Vade: {oge['son_odeme']}): **{oge['miktar']:,} {oge['doviz']}**")
            if col_s.button("🗑️ Sil", key=f"del_cc_{oge['id']}"):
                oge_sil("borclar", "kart_borclari", oge["id"])

    with sekme2:
        st.subheader("Yolcu Ödemeleri (Başkaları Adına/Emanet Yapılan Turlar)")
        with st.form("yolcu_form"):
            tarih = st.date_input("İşlem Tarihi", datetime.now().date())
            aciklama = st.text_input("Kişi İsmi ve Ödeme Nedeni")
            col1, col2 = st.columns(2)
            miktar = col1.number_input("Tutar", min_value=0.0, step=0.01)
            doviz = col2.selectbox("Döviz Tipi", ["TRY", "USD", "EUR"], key="yo_d")
            if st.form_submit_button("Yolcu Ödemesi Ekle"):
                if aciklama:
                    yeni_oge = {
                        "id": str(uuid.uuid4()), "tarih": str(tarih), "aciklama": aciklama,
                        "miktar": miktar, "doviz": doviz
                    }
                    db["borclar"]["yolcu_odemeleri"].append(yeni_oge)
                    save_database(db)
                    st.rerun()

        for oge in db["borclar"]["yolcu_odemeleri"]:
            col_t, col_s = st.columns([5, 1])
            col_t.markdown(f"✈️ **{oge['tarih']}** | {oge['aciklama']}: **{oge['miktar']:,} {oge['doviz']}**")
            if col_s.button("🗑️ Sil", key=f"del_yo_{oge['id']}"):
                oge_sil("borclar", "yolcu_odemeleri", oge["id"])

    with sekme3:
        st.subheader("Orta ve Uzun Vadeli Yapılandırılmış Yükümlülükler")
        with st.form("uzun_borc_form"):
            tarih = st.date_input("Yükümlülük Tarihi", datetime.now().date())
            aciklama = st.text_input("Borç Kaynağı / Detay")
            col1, col2 = st.columns(2)
            miktar = col1.number_input("Ana Para / Kalan Borç", min_value=0.0, step=0.01)
            doviz = col2.selectbox("Döviz Tipi", ["TRY", "USD", "EUR"], key="uv_d")
            if st.form_submit_button("Uzun Vadeli Borç Ekle"):
                if aciklama:
                    yeni_oge = {
                        "id": str(uuid.uuid4()), "tarih": str(tarih), "aciklama": aciklama,
                        "miktar": miktar, "doviz": doviz
                    }
                    db["borclar"]["uzun_vadeli"].append(yeni_oge)
                    save_database(db)
                    st.rerun()

        for oge in db["borclar"]["uzun_vadeli"]:
            col_t, col_s = st.columns([5, 1])
            col_t.markdown(f"🏦 **{oge['tarih']}** | {oge['aciklama']}: **{oge['miktar']:,} {oge['doviz']}**")
            if col_s.button("🗑️ Sil", key=f"del_uv_{oge['id']}"):
                oge_sil("borclar", "uzun_vadeli", oge["id"])

# --- CORE RUNNER / ANA TETİKLEYİCİ ---
def main():
    st.sidebar.title("📌 Navigasyon Paneli")
    sayfa = st.sidebar.radio("Modül Seçimi yapın:", ["Dashboard & Bilanço", "Alınacaklar (Varlıklar)", "Borçlar (Yükümlülükler)"])
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Veritabanını Buluttan Yenile"):
        st.session_state.db = load_database()
        st.sidebar.success("Senkronizasyon başarılı.")
        st.rerun()
        
    st.sidebar.info("Uygulama verileri Google Sheets üzerinde tek bir hücrede şifreli JSON Blob olarak saklanmaktadır.")

    # Sayfa Yönlendirmeleri
    if sayfa == "Dashboard & Bilanço":
        render_dashboard()
    elif sayfa == "Alınacaklar (Varlıklar)":
        render_varliklar()
    elif sayfa == "Borçlar (Yükümlülükler)":
        render_borclar()

if __name__ == "__main__":
    main()