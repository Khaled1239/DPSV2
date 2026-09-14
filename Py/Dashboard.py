# ============================================================
# DPS - Dashboard Penyaluran Sembako
# Sistem Monitoring, Analitik, Prediksi, dan Early Warning
# ============================================================

from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px
import geopandas as gpd


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="DPS - Dashboard Penyaluran Sembako",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ============================================================
# PATH CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

GEOJSON_PATH = (
    BASE_DIR
    / "Geo"
    / "Map.geojson"
)


# ============================================================
# REQUIRED COLUMNS
# ============================================================

REQUIRED_COLUMNS = [
    "DESA_KELURAHAN",
    "ALAMAT",
    "RW",
    "RT",
    "DESIL_NASIONAL",
    "NO_KK",
    "NIK",
    "NAMA",
    "JENIS_KELAMIN"
]


# ============================================================
# SESSION STATE
# ============================================================

if "selected_kecamatan" not in st.session_state:
    st.session_state["selected_kecamatan"] = "SEMUA"


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def normalize_text(value):
    """
    Normalize text untuk kebutuhan matching.
    """

    if pd.isna(value):
        return ""

    value = str(value).strip().upper()

    value = " ".join(value.split())

    return value


def normalize_kecamatan_name(value):
    """
    Normalize nama kecamatan dari GeoJSON.
    """

    value = normalize_text(value)

    replacements = {
        "TANJUNGPINANGBARAT":
            "TANJUNGPINANG BARAT",

        "TANJUNGPINANGKOTA":
            "TANJUNGPINANG KOTA",

        "TANJUNGPINANGTIMUR":
            "TANJUNGPINANG TIMUR",

        "BUKITBESTARI":
            "BUKIT BESTARI",
    }

    return replacements.get(value, value)


# ============================================================
# KELURAHAN -> KECAMATAN
# ============================================================

KELURAHAN_TO_KECAMATAN = {

    # --------------------------------------------------------
    # TANJUNGPINANG KOTA
    # --------------------------------------------------------

    "TANJUNG PINANG KOTA":
        "TANJUNGPINANG KOTA",

    "TANJUNGPINANG KOTA":
        "TANJUNGPINANG KOTA",

    "KAMPUNG BUGIS":
        "TANJUNGPINANG KOTA",

    "SENGGARANG":
        "TANJUNGPINANG KOTA",

    "PENYENGAT":
        "TANJUNGPINANG KOTA",


    # --------------------------------------------------------
    # TANJUNGPINANG BARAT
    # --------------------------------------------------------

    "TANJUNG PINANG BARAT":
        "TANJUNGPINANG BARAT",

    "TANJUNGPINANG BARAT":
        "TANJUNGPINANG BARAT",

    "KEMBOJA":
        "TANJUNGPINANG BARAT",

    "KAMPUNG BARU":
        "TANJUNGPINANG BARAT",

    "BUKIT CERMIN":
        "TANJUNGPINANG BARAT",


    # --------------------------------------------------------
    # TANJUNGPINANG TIMUR
    # --------------------------------------------------------

    "AIR RAJA":
        "TANJUNGPINANG TIMUR",

    "BATU IX":
        "TANJUNGPINANG TIMUR",

    "BATU 9":
        "TANJUNGPINANG TIMUR",

    "KAMPUNG BULANG":
        "TANJUNGPINANG TIMUR",

    "MELAYU KOTA PIRING":
        "TANJUNGPINANG TIMUR",

    "PINANG KENCANA":
        "TANJUNGPINANG TIMUR",


    # --------------------------------------------------------
    # BUKIT BESTARI
    # --------------------------------------------------------

    "DOMPAK":
        "BUKIT BESTARI",

    "SEI JANG":
        "BUKIT BESTARI",

    "SUNGAI JANG":
        "BUKIT BESTARI",

    "TANJUNG AYUN SAKTI":
        "BUKIT BESTARI",

    "TANJUNGAYUN SAKTI":
        "BUKIT BESTARI",

    "TANJUNG UNGGAT":
        "BUKIT BESTARI",

    # TANJUNG PINANG TIMUR merupakan KELURAHAN
    # di Kecamatan Bukit Bestari.

    "TANJUNG PINANG TIMUR":
        "BUKIT BESTARI",

    "TANJUNGPINANG TIMUR":
        "BUKIT BESTARI",
}


# ============================================================
# LOAD UPLOADED DATA
# ============================================================

def load_uploaded_data(uploaded_file):

    try:

        df = pd.read_excel(
            uploaded_file,
            dtype=str
        )

    except Exception as e:

        st.error(
            "File tidak dapat dibaca."
        )

        st.exception(e)

        return None


    # --------------------------------------------------------
    # Normalize column names
    # --------------------------------------------------------

    df.columns = [
        str(col).strip().upper()
        for col in df.columns
    ]


    # --------------------------------------------------------
    # Validate columns
    # --------------------------------------------------------

    missing_columns = [
        col
        for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]


    if missing_columns:

        st.error(
            "Format file tidak sesuai."
        )

        st.write(
            "Kolom berikut tidak ditemukan:"
        )

        for col in missing_columns:

            st.write(
                f"- `{col}`"
            )

        st.info(
            "Pastikan file Excel memiliki "
            "9 kolom berikut:"
        )

        st.code(
            "\n".join(REQUIRED_COLUMNS)
        )

        return None


    # --------------------------------------------------------
    # Keep required columns
    # --------------------------------------------------------

    df = df[
        REQUIRED_COLUMNS
    ].copy()


    # --------------------------------------------------------
    # Clean values
    # --------------------------------------------------------

    for col in df.columns:

        df[col] = (
            df[col]
            .fillna("")
            .astype(str)
            .str.strip()
        )


    # --------------------------------------------------------
    # Normalize kelurahan
    # --------------------------------------------------------

    df["KELURAHAN"] = (
        df["DESA_KELURAHAN"]
        .apply(normalize_text)
    )


    # --------------------------------------------------------
    # Mapping kecamatan
    # --------------------------------------------------------

    df["KECAMATAN"] = (
        df["KELURAHAN"]
        .map(KELURAHAN_TO_KECAMATAN)
        .fillna("TIDAK TERIDENTIFIKASI")
    )


    return df


# ============================================================
# LOAD GEOJSON
# ============================================================

@st.cache_data
def load_geojson():

    if not GEOJSON_PATH.exists():

        st.error(
            "File peta tidak ditemukan."
        )

        st.code(
            str(GEOJSON_PATH)
        )

        st.stop()


    try:

        gdf = gpd.read_file(
            GEOJSON_PATH
        )

    except Exception as e:

        st.error(
            "GeoJSON tidak dapat dibaca."
        )

        st.exception(e)

        st.stop()


    # --------------------------------------------------------
    # Validate NAME_3
    # --------------------------------------------------------

    if "NAME_3" not in gdf.columns:

        st.error(
            "Kolom `NAME_3` tidak ditemukan "
            "pada GeoJSON."
        )

        st.stop()


    # --------------------------------------------------------
    # Normalize kecamatan
    # --------------------------------------------------------

    gdf["KECAMATAN"] = (
        gdf["NAME_3"]
        .apply(normalize_kecamatan_name)
    )


    return gdf


# ============================================================
# HEADER
# ============================================================

st.title(
    "Dashboard Penyaluran Sembako"
)

st.caption(
    "Sistem Monitoring, Analitik, Prediksi, dan Early Warning "
    "untuk Optimalisasi Penyaluran Bantuan Sembako"
)

st.divider()


# ============================================================
# UPLOAD DATA PENERIMA
# ============================================================

st.subheader(
    "Upload Data Penerima"
)

st.write(
    "Upload file Excel data penerima untuk memulai dashboard."
)

st.caption(
    "File peta kecamatan tidak perlu di-upload. "
    "Peta akan menggunakan GeoJSON yang tersedia di sistem."
)


uploaded_file = st.file_uploader(

    "Pilih file data penerima",

    type=[
        "xlsx",
        "xls"
    ],

    help=(
        "File harus memiliki kolom: "
        "DESA_KELURAHAN, ALAMAT, RW, RT, "
        "DESIL_NASIONAL, NO_KK, NIK, NAMA, "
        "JENIS_KELAMIN"
    )
)


# ============================================================
# STOP IF NO FILE
# ============================================================

if uploaded_file is None:

    st.info(
        "Silakan upload data penerima terlebih dahulu "
        "untuk menampilkan dashboard."
    )

    st.markdown(
        "### Format data yang diperlukan"
    )

    format_df = pd.DataFrame(
        {
            "Kolom": REQUIRED_COLUMNS,

            "Keterangan": [
                "Nama desa/kelurahan",
                "Alamat penerima",
                "Rukun Warga",
                "Rukun Tetangga",
                "Desil nasional",
                "Nomor Kartu Keluarga",
                "Nomor Induk Kependudukan",
                "Nama penerima",
                "Jenis kelamin"
            ]
        }
    )

    st.dataframe(
        format_df,
        use_container_width=True,
        hide_index=True
    )

    st.stop()


# ============================================================
# PROCESS UPLOADED DATA
# ============================================================

df = load_uploaded_data(
    uploaded_file
)


# ============================================================
# STOP IF INVALID DATA
# ============================================================

if df is None:

    st.stop()


# ============================================================
# LOAD MAP
# ============================================================

gdf = load_geojson()


# ============================================================
# UPLOAD SUCCESS
# ============================================================

st.success(
    f"Data berhasil dimuat: **{len(df):,} baris**"
)

st.caption(
    f"File: `{uploaded_file.name}`"
)

st.divider()


# ============================================================
# ACTIVE FILTER
# ============================================================

selected_kecamatan = (
    st.session_state[
        "selected_kecamatan"
    ]
)


if selected_kecamatan == "SEMUA":

    filtered_df = df.copy()

else:

    filtered_df = df[
        df["KECAMATAN"]
        == selected_kecamatan
    ].copy()


# ============================================================
# OVERVIEW KPI
# ============================================================

total_penerima = len(
    filtered_df
)


total_kk = (
    filtered_df["NO_KK"]
    .replace("", pd.NA)
    .nunique()
)


if selected_kecamatan == "SEMUA":

    total_kecamatan = (
        df["KECAMATAN"]
        .replace(
            "TIDAK TERIDENTIFIKASI",
            pd.NA
        )
        .nunique()
    )

else:

    total_kecamatan = 1


total_kelurahan = (
    filtered_df["KELURAHAN"]
    .replace("", pd.NA)
    .nunique()
)


# ============================================================
# KPI
# ============================================================

col1, col2, col3, col4 = st.columns(4)


with col1:

    st.metric(
        "Total Penerima",
        f"{total_penerima:,}"
    )


with col2:

    st.metric(
        "Total KK",
        f"{total_kk:,}"
    )


with col3:

    st.metric(
        "Kecamatan",
        f"{total_kecamatan:,}"
    )


with col4:

    st.metric(
        "Kelurahan",
        f"{total_kelurahan:,}"
    )


st.divider()


# ============================================================
# ACTIVE FILTER
# ============================================================

if selected_kecamatan == "SEMUA":

    st.info(
        "Menampilkan seluruh wilayah Kota Tanjungpinang. "
        "Klik kecamatan pada peta untuk memfilter dashboard."
    )

else:

    reset_col, info_col = st.columns(
        [1, 5]
    )


    with reset_col:

        if st.button(
            "Reset",
            use_container_width=True
        ):

            st.session_state[
                "selected_kecamatan"
            ] = "SEMUA"

            st.rerun()


    with info_col:

        st.success(
            f"Kecamatan aktif: **{selected_kecamatan}**"
        )


# ============================================================
# MAP SUMMARY
# ============================================================

map_summary = (

    df.groupby(
        "KECAMATAN"
    )

    .agg(

        PENERIMA=(
            "KECAMATAN",
            "size"
        ),

        KK=(
            "NO_KK",
            lambda x:
                x.replace(
                    "",
                    pd.NA
                ).nunique()
        ),

        KELURAHAN=(
            "KELURAHAN",
            "nunique"
        )
    )

    .reset_index()
)


# ============================================================
# MERGE GEOJSON + DATA
# ============================================================

map_data = gdf.merge(

    map_summary,

    on="KECAMATAN",

    how="left"
)


map_data["PENERIMA"] = (
    map_data["PENERIMA"]
    .fillna(0)
    .astype(int)
)


map_data["KK"] = (
    map_data["KK"]
    .fillna(0)
    .astype(int)
)


map_data["KELURAHAN"] = (
    map_data["KELURAHAN"]
    .fillna(0)
    .astype(int)
)


# ============================================================
# CITY TOTAL
# ============================================================

city_total = len(df)


# ============================================================
# KELURAHAN DETAIL
# ============================================================

def get_kelurahan_detail(
    kecamatan
):

    temp = df[
        df["KECAMATAN"]
        == kecamatan
    ]


    if temp.empty:

        return "Tidak ada data"


    detail = (

        temp.groupby(
            "KELURAHAN"
        )

        .size()

        .sort_values(
            ascending=False
        )
    )


    result = []


    for kelurahan, jumlah in detail.items():

        result.append(
            f"{kelurahan}: {jumlah:,}"
        )


    return "<br>".join(
        result
    )


map_data["PERSENTASE"] = (

    map_data["PENERIMA"]
    / city_total
    * 100

    if city_total > 0

    else 0
)


map_data["HOVER_DETAIL"] = (

    map_data["KECAMATAN"]
    .apply(
        get_kelurahan_detail
    )
)


map_data["HOVER_PENERIMA"] = (
    map_data["PENERIMA"]
)


map_data["HOVER_KK"] = (
    map_data["KK"]
)


map_data["HOVER_KELURAHAN"] = (
    map_data["KELURAHAN"]
)


map_data["HOVER_PERSENTASE"] = (
    map_data["PERSENTASE"]
)


# ============================================================
# MAP CENTER
# ============================================================

minx, miny, maxx, maxy = (
    gdf.total_bounds
)


center_lat = (
    miny + maxy
) / 2


center_lon = (
    minx + maxx
) / 2


# ============================================================
# MAP
# ============================================================

st.subheader(
    "Distribusi Penerima per Kecamatan"
)

st.caption(
    "Peta digunakan sebagai filter wilayah. "
    "Arahkan kursor ke kecamatan untuk melihat detail."
)


fig_map = px.choropleth_map(

    map_data,

    geojson=map_data.__geo_interface__,

    locations="KECAMATAN",

    featureidkey=(
        "properties.KECAMATAN"
    ),

    color="HOVER_PENERIMA",

    color_continuous_scale="Blues",

    map_style="dark",

    zoom=10.5,

    center={
        "lat": center_lat,
        "lon": center_lon
    },

    opacity=0.85
)


# ============================================================
# MAP HOVER
# ============================================================

fig_map.update_traces(

    customdata=map_data[
        [
            "KECAMATAN",
            "HOVER_PENERIMA",
            "HOVER_KK",
            "HOVER_KELURAHAN",
            "HOVER_PERSENTASE",
            "HOVER_DETAIL"
        ]
    ].values,

    hovertemplate=(

        "<b>%{customdata[0]}</b>"

        "<br><br>"

        "Penerima: "
        "%{customdata[1]:,}"

        "<br>"

        "KK: "
        "%{customdata[2]:,}"

        "<br>"

        "Kelurahan: "
        "%{customdata[3]}"

        "<br>"

        "Persentase Kota: "
        "%{customdata[4]:.1f}%"

        "<br><br>"

        "<b>Kelurahan:</b>"

        "<br>"

        "%{customdata[5]}"

        "<extra></extra>"
    )
)


# ============================================================
# MAP BORDER
# ============================================================

fig_map.update_traces(

    marker_line_width=2,

    marker_line_color="white"
)


# ============================================================
# MAP LAYOUT
# ============================================================

fig_map.update_layout(

    height=650,

    margin=dict(
        l=0,
        r=0,
        t=0,
        b=0
    ),

    map_center={
        "lat": center_lat,
        "lon": center_lon
    },

    map_zoom=10.5,

    paper_bgcolor="rgba(0,0,0,0)",

    plot_bgcolor="rgba(0,0,0,0)",

    uirevision="tanjungpinang",

    coloraxis_colorbar=dict(
        title="Penerima"
    )
)


# ============================================================
# DISPLAY MAP
# ============================================================

map_event = st.plotly_chart(

    fig_map,

    use_container_width=True,

    on_select="rerun",

    selection_mode="points",

    key="kecamatan_map"
)


# ============================================================
# MAP CLICK EVENT
# ============================================================

if map_event is not None:

    if (
        map_event.selection
        and map_event.selection.point_indices
    ):

        selected_index = (
            map_event
            .selection
            .point_indices[0]
        )


        clicked_kecamatan = (

            map_data

            .iloc[
                selected_index
            ]

            ["KECAMATAN"]
        )


        if (
            clicked_kecamatan
            != st.session_state[
                "selected_kecamatan"
            ]
        ):

            st.session_state[
                "selected_kecamatan"
            ] = clicked_kecamatan

            st.rerun()


# ============================================================
# ANALISIS WILAYAH
# ============================================================

st.divider()

st.subheader(
    "Analisis Wilayah"
)


# ============================================================
# DISTRIBUSI KECAMATAN
# ============================================================

kecamatan_distribution = (

    filtered_df

    .groupby(
        "KECAMATAN"
    )

    .size()

    .reset_index(
        name="PENERIMA"
    )

    .sort_values(
        "PENERIMA",
        ascending=False
    )
)


fig_kecamatan = px.bar(

    kecamatan_distribution,

    x="KECAMATAN",

    y="PENERIMA",

    text="PENERIMA",

    title=(
        "Distribusi Penerima "
        "per Kecamatan"
    ),

    labels={
        "KECAMATAN": "Kecamatan",
        "PENERIMA": "Jumlah Penerima"
    }
)


fig_kecamatan.update_traces(
    textposition="outside"
)


fig_kecamatan.update_layout(

    height=450,

    xaxis_title="Kecamatan",

    yaxis_title="Jumlah Penerima"
)


st.plotly_chart(
    fig_kecamatan,
    use_container_width=True
)


# ============================================================
# DISTRIBUSI KELURAHAN
# ============================================================

st.subheader(
    "Distribusi Penerima per Kelurahan"
)


kelurahan_distribution = (

    filtered_df

    .groupby(
        [
            "KECAMATAN",
            "KELURAHAN"
        ]
    )

    .size()

    .reset_index(
        name="PENERIMA"
    )

    .sort_values(
        "PENERIMA",
        ascending=False
    )
)


fig_kelurahan = px.bar(

    kelurahan_distribution,

    x="PENERIMA",

    y="KELURAHAN",

    color="KECAMATAN",

    orientation="h",

    title=(
        "Jumlah Penerima "
        "per Kelurahan"
    ),

    labels={
        "PENERIMA": "Jumlah Penerima",
        "KELURAHAN": "Kelurahan"
    }
)


fig_kelurahan.update_layout(

    height=max(
        450,
        len(
            kelurahan_distribution
        ) * 35
    ),

    yaxis={
        "categoryorder":
            "total ascending"
    }
)


st.plotly_chart(
    fig_kelurahan,
    use_container_width=True
)


# ============================================================
# DESIL + GENDER
# ============================================================

col_left, col_right = (
    st.columns(2)
)


# ============================================================
# DESIL
# ============================================================

with col_left:

    st.subheader(
        "Distribusi Desil Nasional"
    )


    desil_distribution = (

        filtered_df[
            "DESIL_NASIONAL"
        ]

        .value_counts()

        .sort_index()

        .reset_index()
    )


    desil_distribution.columns = [
        "DESIL",
        "PENERIMA"
    ]


    fig_desil = px.bar(

        desil_distribution,

        x="DESIL",

        y="PENERIMA",

        text="PENERIMA",

        title=(
            "Penerima "
            "Berdasarkan Desil"
        ),

        labels={
            "DESIL":
                "Desil Nasional",

            "PENERIMA":
                "Jumlah Penerima"
        }
    )


    fig_desil.update_traces(
        textposition="outside"
    )


    fig_desil.update_layout(
        height=450
    )


    st.plotly_chart(
        fig_desil,
        use_container_width=True
    )


# ============================================================
# GENDER
# ============================================================

with col_right:

    st.subheader(
        "Distribusi Jenis Kelamin"
    )


    gender_distribution = (

        filtered_df[
            "JENIS_KELAMIN"
        ]

        .value_counts()

        .reset_index()
    )


    gender_distribution.columns = [
        "JENIS_KELAMIN",
        "PENERIMA"
    ]


    fig_gender = px.pie(

        gender_distribution,

        names="JENIS_KELAMIN",

        values="PENERIMA",

        hole=0.45,

        title=(
            "Distribusi Penerima "
            "Berdasarkan Jenis Kelamin"
        )
    )


    fig_gender.update_layout(
        height=450
    )


    st.plotly_chart(
        fig_gender,
        use_container_width=True
    )


# ============================================================
# TOP 5 KELURAHAN
# ============================================================

st.subheader(
    "Top 5 Kelurahan dengan Penerima Terbanyak"
)


top5_kelurahan = (

    filtered_df

    .groupby(
        [
            "KECAMATAN",
            "KELURAHAN"
        ]
    )

    .size()

    .reset_index(
        name="PENERIMA"
    )

    .sort_values(
        "PENERIMA",
        ascending=False
    )

    .head(5)
)


fig_top5 = px.bar(

    top5_kelurahan,

    x="PENERIMA",

    y="KELURAHAN",

    color="KECAMATAN",

    orientation="h",

    text="PENERIMA",

    labels={
        "PENERIMA": "Jumlah Penerima",
        "KELURAHAN": "Kelurahan"
    }
)


fig_top5.update_traces(
    textposition="outside"
)


fig_top5.update_layout(

    height=350,

    yaxis={
        "categoryorder":
            "total ascending"
    }
)


st.plotly_chart(
    fig_top5,
    use_container_width=True
)


# ============================================================
# SUMMARY TABLE
# ============================================================

st.subheader(
    "Ringkasan Wilayah"
)


summary_table = (

    filtered_df

    .groupby(
        "KECAMATAN"
    )

    .agg(

        Penerima=(
            "KECAMATAN",
            "size"
        ),

        KK=(
            "NO_KK",
            lambda x:
                x.replace(
                    "",
                    pd.NA
                ).nunique()
        ),

        Kelurahan=(
            "KELURAHAN",
            "nunique"
        )
    )

    .reset_index()

    .sort_values(
        "Penerima",
        ascending=False
    )
)


st.dataframe(

    summary_table,

    use_container_width=True,

    hide_index=True
)


# ============================================================
# DATA EXPLORER
# ============================================================

st.divider()

st.subheader(
    "Data Explorer"
)

st.caption(
    "Data personal seperti NIK, nomor KK, nama, dan alamat "
    "tidak ditampilkan pada tabel publik."
)


public_columns = [
    "KECAMATAN",
    "KELURAHAN",
    "RW",
    "RT",
    "DESIL_NASIONAL",
    "JENIS_KELAMIN"
]


public_data = filtered_df[
    public_columns
].copy()


st.dataframe(

    public_data,

    use_container_width=True,

    hide_index=True,

    height=500
)


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "DPS — Dashboard Penyaluran Sembako | "
    "Data Monitoring & Analitik"
)