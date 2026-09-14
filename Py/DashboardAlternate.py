from pathlib import Path

import pandas as pd
import geopandas as gpd
import plotly.express as px
import streamlit as st

# =========================================================
# KONFIGURASI HALAMAN
# =========================================================

st.set_page_config(
    page_title="Dashboard Penyaluran Sembako",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Ubah dua baris ini jika lokasi file kamu berbeda.
DEFAULT_DATA_PATH = Path("C:/Users/HP/PycharmProjects/DashboardPenyaluranBansos/Data/Cleaned/DataPenerimaCleaned.xlsx")
DEFAULT_MAP_PATH = Path("C:/Users/HP/PycharmProjects/DashboardPenyaluranBansos/Geo/Map.geojson")

KELURAHAN_TO_KECAMATAN = {
    # TANJUNGPINANG KOTA
    "TANJUNG PINANG KOTA": "TANJUNGPINANG KOTA",
    "TANJUNGPINANG KOTA": "TANJUNGPINANG KOTA",
    "KAMPUNG BUGIS": "TANJUNGPINANG KOTA",
    "SENGGARANG": "TANJUNGPINANG KOTA",
    "PENYENGAT": "TANJUNGPINANG KOTA",
    # TANJUNGPINANG BARAT
    "TANJUNG PINANG BARAT": "TANJUNGPINANG BARAT",
    "TANJUNGPINANG BARAT": "TANJUNGPINANG BARAT",
    "KEMBOJA": "TANJUNGPINANG BARAT",
    "KAMPUNG BARU": "TANJUNGPINANG BARAT",
    "BUKIT CERMIN": "TANJUNGPINANG BARAT",
    # TANJUNGPINANG TIMUR
    "AIR RAJA": "TANJUNGPINANG TIMUR",
    "BATU IX": "TANJUNGPINANG TIMUR",
    "BATU 9": "TANJUNGPINANG TIMUR",
    "KAMPUNG BULANG": "TANJUNGPINANG TIMUR",
    "MELAYU KOTA PIRING": "TANJUNGPINANG TIMUR",
    "PINANG KENCANA": "TANJUNGPINANG TIMUR",
    # BUKIT BESTARI
    "DOMPAK": "BUKIT BESTARI",
    "SEI JANG": "BUKIT BESTARI",
    "SUNGAI JANG": "BUKIT BESTARI",
    "TANJUNG AYUN SAKTI": "BUKIT BESTARI",
    "TANJUNGAYUN SAKTI": "BUKIT BESTARI",
    "TANJUNG UNGGAT": "BUKIT BESTARI",
    "TANJUNG PINANG TIMUR": "BUKIT BESTARI",
    "TANJUNGPINANG TIMUR": "BUKIT BESTARI",
}

GEOJSON_NAME_FIX = {
    "BUKITBESTARI": "BUKIT BESTARI",
    "TANJUNGPINANGBARAT": "TANJUNGPINANG BARAT",
    "TANJUNGPINANGKOTA": "TANJUNGPINANG KOTA",
    "TANJUNGPINANGTIMUR": "TANJUNGPINANG TIMUR",
}


# =========================================================
# PEMUATAN DATA — OTOMATIS, TANPA PERLU UPLOAD
# =========================================================

@st.cache_data(show_spinner="Memuat data penerima...")
def load_data(file_or_path):
    return pd.read_excel(file_or_path, dtype=str)


@st.cache_data(show_spinner="Memuat data peta...")
def load_map(file_or_path):
    return gpd.read_file(file_or_path)


def get_source(default_path: Path, uploader_label: str, uploader_key: str):
    """Coba pakai file lokal secara otomatis. Hanya tampilkan uploader di
    sidebar sebagai cadangan kalau file default benar-benar tidak ada."""
    if default_path.exists():
        return default_path
    st.sidebar.warning(f"⚠️ `{default_path}` tidak ditemukan.")
    return st.sidebar.file_uploader(uploader_label, type=["xlsx", "geojson", "json"], key=uploader_key)


data_source = get_source(DEFAULT_DATA_PATH, "Unggah Data Penerima (.xlsx)", "up_data")
map_source = get_source(DEFAULT_MAP_PATH, "Unggah Peta (.geojson)", "up_map")

if data_source is None or map_source is None:
    st.error(
        "❌ Data belum bisa dimuat. Pastikan file berada di "
        f"`{DEFAULT_DATA_PATH}` dan `{DEFAULT_MAP_PATH}` relatif terhadap "
        "lokasi script ini, atau unggah lewat sidebar."
    )
    st.stop()

try:
    df = load_data(data_source)
except Exception as e:
    st.error(f"❌ Gagal membaca file data penerima: {e}")
    st.stop()

try:
    gdf = load_map(map_source)
except Exception as e:
    st.error(f"❌ Gagal membaca file peta: {e}")
    st.stop()

required_cols = {"NIK", "NO_KK", "DESA_KELURAHAN"}
missing_cols = required_cols - set(df.columns)
if missing_cols:
    st.error(f"❌ Kolom berikut tidak ditemukan di data: {', '.join(sorted(missing_cols))}")
    st.stop()

if "NAME_3" not in gdf.columns:
    st.error("❌ Kolom `NAME_3` tidak ditemukan di file GeoJSON peta.")
    st.stop()


# =========================================================
# PEMBERSIHAN & AGREGASI DATA
# =========================================================

df["DESA_KELURAHAN"] = df["DESA_KELURAHAN"].astype(str).str.strip().str.upper()
df["KECAMATAN"] = df["DESA_KELURAHAN"].map(KELURAHAN_TO_KECAMATAN)

if "JENIS_KELAMIN" in df.columns:
    df["JENIS_KELAMIN"] = df["JENIS_KELAMIN"].astype(str).str.strip().str.title()

if "DESIL_NASIONAL" in df.columns:
    df["DESIL_NASIONAL_NUM"] = pd.to_numeric(df["DESIL_NASIONAL"], errors="coerce")

unmapped = sorted(df.loc[df["KECAMATAN"].isna(), "DESA_KELURAHAN"].unique())
if unmapped:
    st.sidebar.warning(
        "⚠️ Kelurahan berikut belum ada di kamus pemetaan kecamatan dan "
        "tidak dihitung:\n\n" + "\n".join(f"- {k}" for k in unmapped)
    )

df_mapped = df.dropna(subset=["KECAMATAN"]).copy()

kecamatan_summary = (
    df_mapped.groupby("KECAMATAN")
    .agg(
        TOTAL_PENERIMA=("NIK", "count"),
        TOTAL_KK=("NO_KK", "nunique"),
        JUMLAH_KELURAHAN=("DESA_KELURAHAN", "nunique"),
    )
    .reset_index()
)

kota_total_penerima = int(kecamatan_summary["TOTAL_PENERIMA"].sum())
kota_total_kk = int(df_mapped["NO_KK"].nunique())
kota_total_kelurahan = int(df_mapped["DESA_KELURAHAN"].nunique())
kota_total_kecamatan = int(kecamatan_summary["KECAMATAN"].nunique())

kecamatan_summary["PERSENTASE"] = kecamatan_summary["TOTAL_PENERIMA"] / kota_total_penerima * 100

kelurahan_summary = (
    df_mapped.groupby(["KECAMATAN", "DESA_KELURAHAN"])
    .agg(TOTAL_PENERIMA=("NIK", "count"), TOTAL_KK=("NO_KK", "nunique"))
    .reset_index()
)
kelurahan_summary["PERSENTASE_KECAMATAN"] = (
    kelurahan_summary["TOTAL_PENERIMA"]
    / kelurahan_summary.groupby("KECAMATAN")["TOTAL_PENERIMA"].transform("sum")
    * 100
)
kelurahan_summary["RATA_ANGGOTA_PER_KK"] = (
    kelurahan_summary["TOTAL_PENERIMA"] / kelurahan_summary["TOTAL_KK"]
)


# =========================================================
# SIAPKAN GEODATAFRAME
# =========================================================

gdf = gdf.copy()
gdf["KECAMATAN"] = (
    gdf["NAME_3"].astype(str).str.strip().str.upper().str.replace(r"\s+", " ", regex=True)
)
gdf["KECAMATAN"] = gdf["KECAMATAN"].replace(GEOJSON_NAME_FIX)
gdf = gdf.merge(kecamatan_summary, on="KECAMATAN", how="left")


def make_kelurahan_hover(kecamatan):
    data = kelurahan_summary[kelurahan_summary["KECAMATAN"] == kecamatan].sort_values(
        "TOTAL_PENERIMA", ascending=False
    )
    if data.empty:
        return "Tidak ada data kelurahan"
    rows = [
        f"<b>{row['DESA_KELURAHAN'].title()}</b>: {row['TOTAL_PENERIMA']:,} penerima"
        for _, row in data.iterrows()
    ]
    return "<br>".join(rows)


gdf["DETAIL_KELURAHAN"] = gdf["KECAMATAN"].apply(make_kelurahan_hover)

map_data = gdf.copy()
map_data["HOVER_PENERIMA"] = map_data["TOTAL_PENERIMA"].fillna(0).astype(int)
map_data["HOVER_KK"] = map_data["TOTAL_KK"].fillna(0).astype(int)
map_data["HOVER_KELURAHAN"] = map_data["JUMLAH_KELURAHAN"].fillna(0).astype(int)
map_data["HOVER_PERSENTASE"] = map_data["PERSENTASE"].fillna(0)
map_data["HOVER_DETAIL"] = map_data["DETAIL_KELURAHAN"].fillna("Tidak ada data")


# =========================================================
# FUNGSI INSIGHT OTOMATIS
# =========================================================

def build_insights(scope_df, scope_kecamatan_summary, scope_kelurahan_summary, scope_label):
    """Menghasilkan daftar kalimat insight otomatis berdasarkan data yang
    diberikan (bisa untuk seluruh kota atau satu kecamatan saja)."""
    insights = []

    if not scope_kecamatan_summary.empty and len(scope_kecamatan_summary) > 1:
        top = scope_kecamatan_summary.sort_values("TOTAL_PENERIMA", ascending=False).iloc[0]
        bottom = scope_kecamatan_summary.sort_values("TOTAL_PENERIMA", ascending=True).iloc[0]
        insights.append(
            f"**{top['KECAMATAN'].title()}** memiliki jumlah penerima terbanyak di {scope_label} "
            f"dengan {int(top['TOTAL_PENERIMA']):,} penerima ({top['PERSENTASE']:.1f}%), sedangkan "
            f"**{bottom['KECAMATAN'].title()}** paling sedikit dengan {int(bottom['TOTAL_PENERIMA']):,} "
            f"penerima ({bottom['PERSENTASE']:.1f}%)."
        )

    if not scope_kelurahan_summary.empty:
        top3 = scope_kelurahan_summary.sort_values("TOTAL_PENERIMA", ascending=False).head(3)
        top3_share = top3["TOTAL_PENERIMA"].sum() / scope_kelurahan_summary["TOTAL_PENERIMA"].sum() * 100
        top3_names = ", ".join(top3["DESA_KELURAHAN"].str.title())
        insights.append(
            f"Tiga kelurahan dengan penerima terbanyak ({top3_names}) menyumbang "
            f"**{top3_share:.1f}%** dari total penerima di {scope_label}, menunjukkan tingkat "
            f"konsentrasi kebutuhan yang cukup tinggi di area tersebut."
        )

    if "RATA_ANGGOTA_PER_KK" in scope_kelurahan_summary.columns and not scope_kelurahan_summary.empty:
        rata2 = scope_df["NIK"].count() / scope_df["NO_KK"].nunique() if scope_df["NO_KK"].nunique() else 0
        insights.append(
            f"Rata-rata jumlah anggota penerima per Kartu Keluarga (KK) di {scope_label} adalah "
            f"**{rata2:.2f} orang**."
        )

    if "JENIS_KELAMIN" in scope_df.columns and scope_df["JENIS_KELAMIN"].notna().any():
        gender_counts = scope_df["JENIS_KELAMIN"].value_counts()
        total_gender = gender_counts.sum()
        if total_gender > 0:
            parts = ", ".join(
                f"{g} {c/total_gender*100:.1f}%" for g, c in gender_counts.items()
            )
            dominant = gender_counts.idxmax()
            insights.append(
                f"Komposisi jenis kelamin penerima di {scope_label}: {parts}. Penerima "
                f"**{dominant.lower()}** mendominasi."
            )

    if "DESIL_NASIONAL_NUM" in scope_df.columns and scope_df["DESIL_NASIONAL_NUM"].notna().any():
        desil = scope_df["DESIL_NASIONAL_NUM"].dropna()
        miskin_share = (desil <= 3).sum() / len(desil) * 100
        modus_desil = int(desil.mode().iloc[0]) if not desil.mode().empty else None
        insights.append(
            f"Sekitar **{miskin_share:.1f}%** penerima di {scope_label} berada pada desil "
            f"kesejahteraan nasional 1–3 (kelompok paling rentan secara nasional)"
            + (f", dengan desil {modus_desil} sebagai kelompok terbanyak." if modus_desil else ".")
        )

    return insights


# =========================================================
# HEADER & KPI KOTA (SELALU TAMPIL)
# =========================================================

st.title("📦 Dashboard Penyaluran Sembako — Kota Tanjungpinang")
st.caption("Klik salah satu kecamatan pada peta untuk melihat rincian kelurahannya.")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Total Penerima", f"{kota_total_penerima:,}")
kpi2.metric("Total KK", f"{kota_total_kk:,}")
kpi3.metric("Jumlah Kecamatan", kota_total_kecamatan)
kpi4.metric("Jumlah Kelurahan", kota_total_kelurahan)

st.divider()

tab_peta, tab_insight = st.tabs(["🗺️ Peta Sebaran", "📈 Statistik & Insight"])


# =========================================================
# TAB 1 — PETA CHOROPLETH + DETAIL KECAMATAN
# =========================================================

with tab_peta:
    fig = px.choropleth_map(
        map_data,
        geojson=map_data.__geo_interface__,
        locations="KECAMATAN",
        featureidkey="properties.KECAMATAN",
        color="HOVER_PENERIMA",
        color_continuous_scale="Blues",
        map_style="carto-positron",
        zoom=10,
        center={"lat": 0.9167, "lon": 104.4500},
        opacity=0.70,
    )

    fig.update_traces(
        customdata=map_data[
            ["KECAMATAN", "HOVER_PENERIMA", "HOVER_KELURAHAN", "HOVER_PERSENTASE", "HOVER_DETAIL"]
        ].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br><br>"
            "Penerima: %{customdata[1]:,}<br>"
            "Kelurahan: %{customdata[2]}<br>"
            "Persentase: %{customdata[3]:.1f}%"
            "<br><br><b>Kelurahan:</b><br>%{customdata[4]}"
            "<extra></extra>"
        ),
        marker_line_width=1.5,
        marker_line_color="white",
    )

    fig.update_layout(
        coloraxis_colorbar=dict(title="Jumlah<br>Penerima", thickness=15, len=0.6),
        margin=dict(l=0, r=0, t=10, b=0),
    )

    event = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key="kecamatan_map",
    )

    if event and event.get("selection", {}).get("points"):
        point = event["selection"]["points"][0]
        clicked_location = point.get("location")
        if clicked_location:
            st.session_state["selected_kecamatan"] = clicked_location

    selected_kecamatan = st.session_state.get("selected_kecamatan")

    if selected_kecamatan:
        st.divider()

        col_title, col_reset = st.columns([5, 1])
        with col_title:
            st.subheader(f"📍 Detail Kecamatan — {selected_kecamatan.title()}")
        with col_reset:
            if st.button("↩ Reset", key="reset_kecamatan", use_container_width=True):
                st.session_state["selected_kecamatan"] = None
                st.rerun()

        kec_detail = kecamatan_summary[kecamatan_summary["KECAMATAN"] == selected_kecamatan]

        if kec_detail.empty:
            st.info("Tidak ada data untuk kecamatan ini.")
        else:
            kec_detail = kec_detail.iloc[0]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Penerima", f"{int(kec_detail['TOTAL_PENERIMA']):,}")
            c2.metric("Total KK", f"{int(kec_detail['TOTAL_KK']):,}")
            c3.metric("Jumlah Kelurahan", int(kec_detail["JUMLAH_KELURAHAN"]))
            c4.metric("Persentase Kota", f"{float(kec_detail['PERSENTASE']):.1f}%")

            tab_tabel, tab_grafik = st.tabs(["📋 Tabel Kelurahan", "📊 Grafik Kelurahan"])

            detail = kelurahan_summary[kelurahan_summary["KECAMATAN"] == selected_kecamatan].copy()
            detail["PERSENTASE"] = detail["TOTAL_PENERIMA"] / detail["TOTAL_PENERIMA"].sum() * 100
            detail = detail.sort_values("TOTAL_PENERIMA", ascending=False)

            with tab_tabel:
                search = st.text_input(
                    "🔍 Cari kelurahan", key="search_kelurahan", placeholder="Ketik nama kelurahan..."
                )
                filtered = detail
                if search:
                    filtered = detail[detail["DESA_KELURAHAN"].str.contains(search, case=False, na=False)]

                display = filtered[["DESA_KELURAHAN", "TOTAL_PENERIMA", "TOTAL_KK", "PERSENTASE"]].copy()
                display.columns = ["Kelurahan", "Total Penerima", "Total KK", "Persentase"]
                display["Persentase"] = display["Persentase"].map(lambda x: f"{x:.1f}%")

                st.dataframe(display, use_container_width=True, hide_index=True)

                st.download_button(
                    "⬇️ Unduh data kelurahan (CSV)",
                    data=filtered.to_csv(index=False).encode("utf-8"),
                    file_name=f"kelurahan_{selected_kecamatan.lower().replace(' ', '_')}.csv",
                    mime="text/csv",
                )

            with tab_grafik:
                fig_kelurahan = px.bar(
                    detail,
                    x="TOTAL_PENERIMA",
                    y="DESA_KELURAHAN",
                    orientation="h",
                    text="TOTAL_PENERIMA",
                    color="TOTAL_PENERIMA",
                    color_continuous_scale="Blues",
                )
                fig_kelurahan.update_layout(
                    xaxis_title="Jumlah Penerima",
                    yaxis_title="Kelurahan",
                    yaxis=dict(categoryorder="total ascending"),
                    height=400,
                    margin=dict(l=0, r=0, t=20, b=0),
                    coloraxis_showscale=False,
                )
                fig_kelurahan.update_traces(texttemplate="%{text:,}", textposition="outside")
                st.plotly_chart(fig_kelurahan, use_container_width=True)

            st.markdown("#### 💡 Insight otomatis untuk kecamatan ini")
            kec_scope_df = df_mapped[df_mapped["KECAMATAN"] == selected_kecamatan]
            for point_text in build_insights(
                kec_scope_df,
                kecamatan_summary[kecamatan_summary["KECAMATAN"] == selected_kecamatan],
                detail,
                selected_kecamatan.title(),
            ):
                st.markdown(f"- {point_text}")
    else:
        st.info("👆 Klik salah satu kecamatan pada peta di atas untuk melihat rincian kelurahannya.")

    with st.expander("📊 Lihat ringkasan semua kecamatan"):
        ringkasan = kecamatan_summary.sort_values("TOTAL_PENERIMA", ascending=False).copy()
        ringkasan_display = ringkasan[
            ["KECAMATAN", "TOTAL_PENERIMA", "TOTAL_KK", "JUMLAH_KELURAHAN", "PERSENTASE"]
        ].copy()
        ringkasan_display.columns = ["Kecamatan", "Total Penerima", "Total KK", "Jumlah Kelurahan", "Persentase Kota"]
        ringkasan_display["Persentase Kota"] = ringkasan_display["Persentase Kota"].map(lambda x: f"{x:.1f}%")
        st.dataframe(ringkasan_display, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Unduh ringkasan kecamatan (CSV)",
            data=ringkasan.to_csv(index=False).encode("utf-8"),
            file_name="ringkasan_kecamatan.csv",
            mime="text/csv",
        )


# =========================================================
# TAB 2 — STATISTIK & INSIGHT KOTA
# =========================================================

with tab_insight:
    st.subheader("📈 Statistik & Insight Tingkat Kota")

    colA, colB = st.columns(2)

    # ---- Distribusi jenis kelamin ----
    with colA:
        if "JENIS_KELAMIN" in df_mapped.columns and df_mapped["JENIS_KELAMIN"].notna().any():
            gender_df = df_mapped["JENIS_KELAMIN"].value_counts().reset_index()
            gender_df.columns = ["Jenis Kelamin", "Jumlah"]
            fig_gender = px.pie(
                gender_df,
                names="Jenis Kelamin",
                values="Jumlah",
                hole=0.5,
                color="Jenis Kelamin",
                color_discrete_map={"Laki-Laki": "#4C78A8", "Perempuan": "#F58518"},
                title="Komposisi Jenis Kelamin Penerima",
            )
            fig_gender.update_traces(textinfo="percent+label")
            st.plotly_chart(fig_gender, use_container_width=True)
        else:
            st.info("Kolom JENIS_KELAMIN tidak tersedia di data.")

    # ---- Distribusi desil nasional ----
    with colB:
        if "DESIL_NASIONAL_NUM" in df_mapped.columns and df_mapped["DESIL_NASIONAL_NUM"].notna().any():
            desil_df = (
                df_mapped["DESIL_NASIONAL_NUM"]
                .dropna()
                .astype(int)
                .value_counts()
                .sort_index()
                .reset_index()
            )
            desil_df.columns = ["Desil Nasional", "Jumlah"]
            fig_desil = px.bar(
                desil_df,
                x="Desil Nasional",
                y="Jumlah",
                text="Jumlah",
                color="Jumlah",
                color_continuous_scale="Reds_r",
                title="Distribusi Desil Kesejahteraan Nasional",
            )
            fig_desil.update_layout(
                xaxis=dict(dtick=1),
                coloraxis_showscale=False,
                yaxis_title="Jumlah Penerima",
            )
            fig_desil.update_traces(texttemplate="%{text:,}", textposition="outside")
            st.plotly_chart(fig_desil, use_container_width=True)
            st.caption(
                "Semakin kecil angka desil, semakin rendah tingkat kesejahteraan rumah tangga "
                "tersebut secara nasional (Desil 1 = 10% termiskin di Indonesia)."
            )
        else:
            st.info("Kolom DESIL_NASIONAL tidak tersedia di data.")

    st.divider()

    colC, colD = st.columns(2)

    # ---- Top & bottom kelurahan ----
    with colC:
        st.markdown("**Top 5 Kelurahan — Penerima Terbanyak**")
        top5 = kelurahan_summary.sort_values("TOTAL_PENERIMA", ascending=False).head(5)
        fig_top5 = px.bar(
            top5,
            x="TOTAL_PENERIMA",
            y="DESA_KELURAHAN",
            orientation="h",
            text="TOTAL_PENERIMA",
            color_discrete_sequence=["#4C78A8"],
        )
        fig_top5.update_layout(
            yaxis=dict(categoryorder="total ascending"),
            xaxis_title="Jumlah Penerima",
            yaxis_title="",
            height=300,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        fig_top5.update_traces(texttemplate="%{text:,}", textposition="outside")
        st.plotly_chart(fig_top5, use_container_width=True)

    with colD:
        st.markdown("**Rata-rata Anggota Penerima per KK — per Kecamatan**")
        rasio_kk = (
            df_mapped.groupby("KECAMATAN")
            .apply(lambda g: g["NIK"].count() / g["NO_KK"].nunique())
            .reset_index(name="RATA_ANGGOTA_PER_KK")
            .sort_values("RATA_ANGGOTA_PER_KK", ascending=False)
        )
        fig_rasio = px.bar(
            rasio_kk,
            x="RATA_ANGGOTA_PER_KK",
            y="KECAMATAN",
            orientation="h",
            text="RATA_ANGGOTA_PER_KK",
            color_discrete_sequence=["#72B7B2"],
        )
        fig_rasio.update_layout(
            yaxis=dict(categoryorder="total ascending"),
            xaxis_title="Rata-rata Anggota / KK",
            yaxis_title="",
            height=300,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        fig_rasio.update_traces(texttemplate="%{text:.2f}", textposition="outside")
        st.plotly_chart(fig_rasio, use_container_width=True)

    st.divider()

    st.markdown("### 💡 Insight Otomatis — Seluruh Kota")
    for point_text in build_insights(df_mapped, kecamatan_summary, kelurahan_summary, "Kota Tanjungpinang"):
        st.markdown(f"- {point_text}")
