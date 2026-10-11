from pathlib import Path
import inspect
import io
import itertools
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# ============================================================
# DPS — Dashboard Penyaluran Sembako
# Satu file gabungan (data penyaluran 2025 + data penerima 2026).
# Filter di sidebar kiri: Tahun dan Kabupaten/Kota (tanpa filter Kecamatan).
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
# Mendukung Py/Dashboard.py maupun Dashboard.py di root proyek.
BASE_DIR = SCRIPT_DIR if (SCRIPT_DIR / "Geo").exists() else SCRIPT_DIR.parent
GEOJSON_PATH = BASE_DIR / "Geo" / "Map_Kecamatan_Kepri.geojson"

NO_DATA = "(Tidak dicatat)"
AGE_BINS = [-1, 17, 24, 34, 44, 54, 64, 74, 200]
AGE_LABELS = ["<18", "18–24", "25–34", "35–44", "45–54", "55–64", "65–74", "75+"]
GENDERS = ["Laki-laki", "Perempuan"]
GENDER_COLORS = {"Laki-laki": "#118AB2", "Perempuan": "#EF476F"}
YEAR_COLORS = {"2025": "#06D6A0", "2026": "#FFB703"}
KAB_COLORS = {"KARIMUN": "#00B4D8", "LINGGA": "#F77F00", "TANJUNGPINANG": "#8338EC",
              "BINTAN": "#EF476F", "BATAM": "#06D6A0", "NATUNA": "#FFD166", "KEPULAUAN ANAMBAS": "#118AB2"}
PALETTE = px.colors.qualitative.Bold
_PLOT_ID = itertools.count()

KELURAHAN_TO_KECAMATAN = {
    "TANJUNG PINANG KOTA": "TANJUNGPINANGKOTA",
    "TANJUNGPINANG KOTA": "TANJUNGPINANGKOTA",
    "KAMPUNG BUGIS": "TANJUNGPINANGKOTA",
    "SENGGARANG": "TANJUNGPINANGKOTA",
    "PENYENGAT": "TANJUNGPINANGKOTA",
    "TANJUNG PINANG BARAT": "TANJUNGPINANGBARAT",
    "TANJUNGPINANG BARAT": "TANJUNGPINANGBARAT",
    "KEMBOJA": "TANJUNGPINANGBARAT",
    "KAMPUNG BARU": "TANJUNGPINANGBARAT",
    "BUKIT CERMIN": "TANJUNGPINANGBARAT",
    "AIR RAJA": "TANJUNGPINANGTIMUR",
    "BATU IX": "TANJUNGPINANGTIMUR",
    "BATU 9": "TANJUNGPINANGTIMUR",
    "BATU SEMBILAN": "TANJUNGPINANGTIMUR",
    "KAMPUNG BULANG": "TANJUNGPINANGTIMUR",
    "MELAYU KOTA PIRING": "TANJUNGPINANGTIMUR",
    "PINANG KENCANA": "TANJUNGPINANGTIMUR",
    "DOMPAK": "BUKITBESTARI",
    "SEI JANG": "BUKITBESTARI",
    "SUNGAI JANG": "BUKITBESTARI",
    "TANJUNG AYUN SAKTI": "BUKITBESTARI",
    "TANJUNGAYUN SAKTI": "BUKITBESTARI",
    "TANJUNG UNGGAT": "BUKITBESTARI",
    # Kelurahan Tanjungpinang Timur berada di Kecamatan Bukit Bestari.
    "TANJUNG PINANG TIMUR": "BUKITBESTARI",
    "TANJUNGPINANG TIMUR": "BUKITBESTARI",
}
KEC_DISPLAY = {
    "TANJUNGPINANGKOTA": "TANJUNGPINANG KOTA",
    "TANJUNGPINANGBARAT": "TANJUNGPINANG BARAT",
    "TANJUNGPINANGTIMUR": "TANJUNGPINANG TIMUR",
    "BUKITBESTARI": "BUKIT BESTARI",
}


def norm(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip().upper())


def key(value):
    """Kunci wilayah ringkas untuk mencocokkan nama GeoJSON dan spreadsheet."""
    value = norm(value)
    value = re.sub(r"^(KABUPATEN|KAB\.?|KOTA)\s+", "", value)
    value = re.sub(r"[^A-Z0-9]", "", value)
    return {"BATUIX": "BATU9"}.get(value, value)


def normalize_kabupaten(value):
    k = key(value)
    aliases = {
        "KARIMUN": "KARIMUN",
        "BINTAN": "BINTAN",
        "NATUNA": "NATUNA",
        "LINGGA": "LINGGA",
        "KEPULAUANANAMBAS": "KEPULAUAN ANAMBAS",
        "BATAM": "BATAM",
        "TANJUNGPINANG": "TANJUNGPINANG",
    }
    return aliases.get(k, norm(value))


def infer_kabupaten(sheet_name):
    s = norm(sheet_name)
    for token, kab in [("KARIMUN", "KARIMUN"), ("TGPINANG", "TANJUNGPINANG"), ("TANJUNGPINANG", "TANJUNGPINANG"),
                       ("LINGGA", "LINGGA"), ("BINTAN", "BINTAN"), ("NATUNA", "NATUNA"),
                       ("ANAMBAS", "KEPULAUAN ANAMBAS"), ("BATAM", "BATAM")]:
        if token in s:
            return kab
    return ""


def fmt(n):
    return f"{int(round(n)):,}".replace(",", ".")


def pct(x, digits=1):
    if x is None or pd.isna(x):
        return "-"
    return f"{x:.{digits}f}".replace(".", ",") + "%"


def num(x, digits=1):
    if x is None or pd.isna(x):
        return "-"
    return f"{x:.{digits}f}".replace(".", ",")


def norm_gender(value):
    v = norm(value)
    if v in ("L", "LAKI-LAKI", "LAKI LAKI", "LAKI", "PRIA", "M", "MALE"):
        return "Laki-laki"
    if v in ("P", "PEREMPUAN", "WANITA", "F", "FEMALE"):
        return "Perempuan"
    return ""


def derive_from_nik(nik, valid, ref_year):
    """Jenis kelamin & usia dari struktur NIK (tgl lahir ddmmyy; perempuan = tanggal + 40).
    ref_year per baris, jadi usia 2025 dan 2026 dihitung terhadap tahunnya masing-masing."""
    d = pd.to_numeric(nik.str[6:8], errors="coerce")
    m = pd.to_numeric(nik.str[8:10], errors="coerce")
    y = pd.to_numeric(nik.str[10:12], errors="coerce")
    female = d > 40
    day = d.where(~female, d - 40)
    ok = valid & day.between(1, 31) & m.between(1, 12)
    gender = pd.Series(np.where(ok, np.where(female, "Perempuan", "Laki-laki"), ""), index=nik.index)
    birth = (2000 + y).where(y <= ref_year % 100, 1900 + y)
    age = (ref_year - birth).where(ok)
    return gender, age.where(age.between(0, 110))


def color_map(values):
    """Warna konsisten per kabupaten/kota; sisanya diambil dari palet."""
    cmap, extra = {}, itertools.cycle(PALETTE)
    for v in sorted(set(values)):
        cmap[v] = KAB_COLORS.get(v) or next(extra)
    return cmap


def show(fig, height=None):
    fig.update_layout(margin=dict(l=10, r=10, t=55, b=10), font=dict(size=13))
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(fig, use_container_width=True, key=f"p{next(_PLOT_ID)}")


def note(text):
    if text:
        st.caption("💡 " + text)


def parse_rw_rt(address):
    text = norm(address)
    rw = re.search(r"\bRW\s*[-./:]?\s*(\d+)", text)
    rt = re.search(r"\bRT\s*[-./:]?\s*(\d+)", text)
    return (rw.group(1) if rw else "", rt.group(1) if rt else "")


# ============================================================
# Pembacaan data
# ============================================================
COLUMN_ALIASES = {
    "KELURAHAN": "DESA_KELURAHAN", "DESA": "DESA_KELURAHAN", "DESA/KELURAHAN": "DESA_KELURAHAN",
    "KABUPATEN/KOTA": "KABUPATEN", "KABUPATEN_KOTA": "KABUPATEN",
    "KECAMATAN_ASAL": "KECAMATAN",
    "TAHUN_PENYALURAN": "TAHUN",
    "KET_PENYALURAN": "KETERANGAN", "KET": "KETERANGAN",
    "DESIL": "DESIL_NASIONAL",
}


def standardize_sheet(raw, sheet_name):
    """Ubah satu sheet (format gabungan maupun sheet mentah) ke kolom standar dashboard."""
    df = raw.copy()
    df.columns = [norm(c).replace(" ", "_") for c in df.columns]
    df = df.rename(columns={k: v for k, v in COLUMN_ALIASES.items() if k in df.columns and v not in df.columns})
    df = df.dropna(how="all").reset_index(drop=True)

    def col(name):
        if name in df.columns:
            return df[name].fillna("").astype(str).str.strip()
        return pd.Series("", index=df.index)

    out = pd.DataFrame(index=df.index)
    out["NIK"] = col("NIK").str.replace(r"\.0+$", "", regex=True)
    out["NAMA"] = col("NAMA")
    out["ALAMAT"] = col("ALAMAT")
    out["NO_KK"] = col("NO_KK")
    out["DESIL_NASIONAL"] = col("DESIL_NASIONAL").str.replace(r"\.0+$", "", regex=True)
    out["JENIS_KELAMIN"] = col("JENIS_KELAMIN")

    sumber = col("SUMBER_SHEET")
    out["SUMBER_SHEET"] = sumber.where(sumber != "", sheet_name)

    kab = col("KABUPATEN")
    kab = kab.where(kab != "", out["SUMBER_SHEET"].map(infer_kabupaten))
    out["KABUPATEN_KOTA"] = kab.map(normalize_kabupaten)

    out["KELURAHAN"] = col("DESA_KELURAHAN").map(norm)
    kec = col("KECAMATAN").map(norm)
    # Tanjungpinang: isi kecamatan dari nama kelurahan bila kosong.
    fallback = out["KELURAHAN"].map(KELURAHAN_TO_KECAMATAN).fillna("")
    use_fallback = (kec == "") & (out["KABUPATEN_KOTA"].map(key) == "TANJUNGPINANG")
    kec = kec.where(~use_fallback, fallback)
    out["KECAMATAN"] = kec.replace(KEC_DISPLAY)

    out["KETERANGAN"] = col("KETERANGAN").map(norm)
    tahun = col("TAHUN").str.extract(r"(\d{4})", expand=False).fillna("2025")
    out["TAHUN"] = tahun

    jenis = col("JENIS_DATA").map(norm)
    out["JENIS_DATA"] = jenis.where(jenis != "", "PENYALURAN")

    out["RW"] = col("RW")
    out["RT"] = col("RT")
    parsed = out["ALAMAT"].map(parse_rw_rt)
    out["RW"] = out["RW"].where(out["RW"] != "", parsed.map(lambda x: x[0]))
    out["RT"] = out["RT"].where(out["RT"] != "", parsed.map(lambda x: x[1]))

    out["NIK_VALID_16_DIGIT"] = out["NIK"].str.fullmatch(r"\d{16}", na=False)
    out["KAB_KEY"] = out["KABUPATEN_KOTA"].map(key)
    out["KEC_KEY"] = out["KECAMATAN"].map(key)

    # Jenis kelamin (data asli, atau estimasi dari NIK), usia, dan desil numerik.
    g_nik, age = derive_from_nik(out["NIK"], out["NIK_VALID_16_DIGIT"], pd.to_numeric(out["TAHUN"]))
    g_data = out["JENIS_KELAMIN"].map(norm_gender)
    out["GENDER"] = g_data.where(g_data != "", g_nik)
    out["SUMBER_GENDER"] = np.where(g_data != "", "Data", np.where(g_nik != "", "Estimasi NIK", "Tidak diketahui"))
    out["USIA"] = age
    out["KELOMPOK_USIA"] = pd.cut(age, AGE_BINS, labels=AGE_LABELS).astype(object).fillna("")
    out["DESIL_NUM"] = pd.to_numeric(out["DESIL_NASIONAL"].str.extract(r"(\d+)", expand=False), errors="coerce")
    out["DESIL"] = np.where(out["DESIL_NUM"].notna(), "Desil " + out["DESIL_NUM"].fillna(0).astype(int).astype(str), "")
    return out


def load_uploaded_workbook(file_bytes):
    sheets = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, dtype=str)
    frames = [standardize_sheet(sheet, name) for name, sheet in sheets.items()]
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise ValueError("Workbook tidak memiliki sheet berisi data.")
    df = pd.concat(frames, ignore_index=True)
    # NIK ganda = NIK sama >1x pada tahun yang sama; NIK yang muncul di beda tahun bukan ganda.
    df["NIK_GANDA"] = (df["NIK"] != "") & df.duplicated(["NIK", "TAHUN"], keep=False)
    df["KEC_L"] = df["KECAMATAN"].where(df["KECAMATAN"] != "", NO_DATA)
    df["KEL_L"] = df["KELURAHAN"].where(df["KELURAHAN"] != "", NO_DATA)
    df["KET_L"] = df["KETERANGAN"].where(df["KETERANGAN"] != "", NO_DATA)
    return df, list(sheets.keys())


@st.cache_data(show_spinner=False)
def load_map(path_string, modified_time):
    gdf = gpd.read_file(path_string)
    if "KECAMATAN" not in gdf.columns:
        if "NAME_3" not in gdf.columns:
            raise ValueError("Kolom NAME_3/KECAMATAN tidak ditemukan dalam GeoJSON.")
        gdf["KECAMATAN"] = gdf["NAME_3"]
    if "KABUPATEN_KOTA" not in gdf.columns:
        if "NAME_2" not in gdf.columns:
            raise ValueError("Kolom NAME_2/KABUPATEN_KOTA tidak ditemukan dalam GeoJSON.")
        gdf["KABUPATEN_KOTA"] = gdf["NAME_2"]
    gdf["KABUPATEN_KOTA"] = gdf["KABUPATEN_KOTA"].map(normalize_kabupaten)
    gdf["KECAMATAN"] = gdf["KECAMATAN"].map(norm)
    gdf["KAB_KEY"] = gdf["KABUPATEN_KOTA"].map(key)
    gdf["KEC_KEY"] = gdf["KECAMATAN"].map(key)
    gdf["MAP_ID"] = gdf["KAB_KEY"] + "__" + gdf["KEC_KEY"]
    # Peta level kabupaten/kota: gabungkan semua kecamatan per kabupaten.
    kab = gdf[["KAB_KEY", "KABUPATEN_KOTA", "geometry"]].dissolve(by="KAB_KEY", aggfunc="first").reset_index()
    kab["MAP_ID"] = kab["KAB_KEY"]
    return gdf, kab


def region_ids(df, gdf):
    """MAP_ID kecamatan tiap baris. Cocok persis KABUPATEN__KECAMATAN; bila gagal, cocokkan lewat
    nama kecamatan saja asalkan namanya unik di GeoJSON. Baris tanpa kecocokan bernilai NaN."""
    exact = df["KAB_KEY"] + "__" + df["KEC_KEY"]
    uniq = gdf.groupby("KEC_KEY")["MAP_ID"].agg(list)
    uniq = {k: v[0] for k, v in uniq.items() if len(v) == 1}
    out = exact.where(exact.isin(set(gdf["MAP_ID"])), df["KEC_KEY"].map(uniq))
    return out.where(df["KEC_KEY"] != "")


_PLOTLY_CAN_SELECT = "on_select" in inspect.signature(st.plotly_chart).parameters


def on_map_select(chart_key):
    """Dipanggil saat wilayah di peta diklik: set filter Kabupaten/Kota di sidebar."""
    try:
        points = st.session_state[chart_key]["selection"]["points"]
    except Exception:
        return
    if not points:
        return
    p = points[0]
    loc = p.get("location")
    if loc is None:
        idx = p.get("point_index", p.get("point_number"))
        ids = st.session_state.get("_map_ids", {}).get(chart_key, [])
        loc = ids[idx] if idx is not None and idx < len(ids) else None
    if loc is None:
        return
    name = st.session_state.get("_kab_names", {}).get(str(loc).split("__")[0])
    if name and name in st.session_state.get("_kab_options", []):
        st.session_state["f_kab"] = name


# ============================================================
# Visualisasi per tab
# ============================================================
def render_overview(df):
    known = df[df["GENDER"] != ""]
    est = (df["SUMBER_GENDER"] == "Estimasi NIK").any()
    c = st.columns(5)
    c[0].metric("Perempuan" + (" (estimasi)" if est else ""), pct((known["GENDER"] == "Perempuan").mean() * 100) if len(known) else "-")
    c[1].metric("Usia median", f"{num(df['USIA'].median(), 0)} th" if df["USIA"].notna().any() else "-")
    c[2].metric("Usia 60+", pct((df.loc[df["USIA"].notna(), "USIA"] >= 60).mean() * 100) if df["USIA"].notna().any() else "-")
    if df["DESIL_NUM"].notna().any():
        c[3].metric("Desil 1–2", pct((df.loc[df["DESIL_NUM"].notna(), "DESIL_NUM"] <= 2).mean() * 100))
    else:
        c[3].metric("Tahap tercatat", pct((df["KETERANGAN"] != "").mean() * 100))
    c[4].metric("Baris NIK ganda", fmt(df["NIK_GANDA"].sum()))

    cmap = color_map(df["KABUPATEN_KOTA"])
    left, right = st.columns([3, 2])
    with left:
        tree = df[df["KABUPATEN_KOTA"] != ""].groupby(["KABUPATEN_KOTA", "KEC_L", "KEL_L"]).size().reset_index(name="JUMLAH")
        fig = px.treemap(tree, path=[px.Constant("Kepri"), "KABUPATEN_KOTA", "KEC_L", "KEL_L"], values="JUMLAH",
                         color="KABUPATEN_KOTA", color_discrete_map={"(?)": "#2b2d42", **cmap},
                         title="Peta pohon: Kabupaten/Kota › Kecamatan › Kelurahan")
        fig.update_traces(hovertemplate="<b>%{label}</b><br>Jumlah: %{value:,}<extra></extra>")
        show(fig, 460)
    with right:
        kab = df.groupby("KABUPATEN_KOTA").size().reset_index(name="JUMLAH")
        fig = px.pie(kab, names="KABUPATEN_KOTA", values="JUMLAH", hole=0.55, color="KABUPATEN_KOTA",
                     color_discrete_map=cmap, title="Komposisi per kabupaten/kota")
        fig.update_traces(textinfo="label+percent", textfont_size=14)
        show(fig, 460)
    top = df.groupby("KABUPATEN_KOTA").size().sort_values(ascending=False)
    if len(top):
        note(f"{top.index[0]} memiliki data terbanyak ({fmt(top.iloc[0])} baris, {pct(top.iloc[0] / top.sum() * 100)} dari total). "
             "Klik kotak pada peta pohon untuk melihat rincian sampai tingkat kelurahan.")

    kel = df.groupby(["KABUPATEN_KOTA", "KEL_L"]).size().reset_index(name="JUMLAH").sort_values("JUMLAH", ascending=False)
    kel["KUM"] = kel["JUMLAH"].cumsum() / kel["JUMLAH"].sum() * 100
    topn = min(len(kel), st.slider("Jumlah kelurahan/desa pada grafik Pareto", 5, max(5, min(50, len(kel))), min(15, len(kel)), key="sl_pareto")) if len(kel) > 5 else len(kel)
    sub = kel.head(topn)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=sub["KEL_L"], y=sub["JUMLAH"], name="Jumlah data", marker_color=[cmap.get(k, "#888") for k in sub["KABUPATEN_KOTA"]],
                         customdata=sub["KABUPATEN_KOTA"], hovertemplate="%{x} (%{customdata})<br>%{y:,}<extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=sub["KEL_L"], y=sub["KUM"], name="Kumulatif (%)", mode="lines+markers", line=dict(color="#EF476F", width=3)), secondary_y=True)
    fig.update_yaxes(title_text="Jumlah data", secondary_y=False)
    fig.update_yaxes(title_text="Kumulatif (%)", range=[0, 105], secondary_y=True)
    fig.update_layout(title=f"Pareto {topn} kelurahan/desa teratas (warna = kabupaten/kota)", xaxis_tickangle=-40, legend=dict(orientation="h", y=1.12))
    show(fig, 460)
    note(f"{topn} kelurahan/desa teratas mencakup {pct(sub['KUM'].iloc[-1])} seluruh data. Garis yang cepat menanjak berarti data terkonsentrasi di sedikit wilayah.")


def render_region(df):
    cmap = color_map(df["KABUPATEN_KOTA"])
    left, right = st.columns(2)
    with left:
        if df["TAHUN"].nunique() > 1:
            t = df.groupby(["KABUPATEN_KOTA", "TAHUN"]).size().reset_index(name="JUMLAH")
            fig = px.bar(t, x="KABUPATEN_KOTA", y="JUMLAH", color="TAHUN", barmode="group", text="JUMLAH", color_discrete_map=YEAR_COLORS,
                         title="Jumlah data per kabupaten/kota dan tahun", labels={"KABUPATEN_KOTA": "Kabupaten/Kota", "JUMLAH": "Jumlah"})
        else:
            t = df.groupby("KABUPATEN_KOTA").size().reset_index(name="JUMLAH")
            fig = px.bar(t, x="KABUPATEN_KOTA", y="JUMLAH", color="KABUPATEN_KOTA", text="JUMLAH", color_discrete_map=cmap,
                         title="Jumlah data per kabupaten/kota", labels={"KABUPATEN_KOTA": "Kabupaten/Kota", "JUMLAH": "Jumlah"})
            fig.update_layout(showlegend=False)
        fig.update_traces(textposition="outside")
        show(fig, 420)
    with right:
        s = df.groupby(["KABUPATEN_KOTA", "SUMBER_SHEET"]).size().reset_index(name="JUMLAH")
        fig = px.sunburst(s, path=["KABUPATEN_KOTA", "SUMBER_SHEET"], values="JUMLAH", color="KABUPATEN_KOTA", color_discrete_map={"(?)": "#2b2d42", **cmap},
                          title="Kabupaten/Kota › sheet sumber")
        fig.update_traces(hovertemplate="<b>%{label}</b><br>%{value:,}<extra></extra>")
        show(fig, 420)

    kec = df.groupby(["KABUPATEN_KOTA", "KEC_L"]).size().reset_index(name="JUMLAH").sort_values("JUMLAH")
    fig = px.bar(kec, x="JUMLAH", y="KEC_L", color="KABUPATEN_KOTA", orientation="h", text="JUMLAH", color_discrete_map=cmap,
                 labels={"JUMLAH": "Jumlah data", "KEC_L": "Kecamatan", "KABUPATEN_KOTA": "Kabupaten/Kota"}, title="Jumlah data per kecamatan")
    fig.update_traces(textposition="outside", cliponaxis=False)
    show(fig, max(380, min(1000, len(kec) * 30)))
    if (df["KECAMATAN"] == "").any():
        note(f"{pct((df['KECAMATAN'] == '').mean() * 100)} baris tidak memiliki nama kecamatan (ditampilkan sebagai \"{NO_DATA}\").")

    kel = df.groupby(["KABUPATEN_KOTA", "KEL_L"]).size().reset_index(name="JUMLAH").sort_values("JUMLAH", ascending=False)
    c1, c2 = st.columns(2)
    with c1:
        n = min(len(kel), st.slider("Kelurahan/desa teratas", 5, max(5, min(40, len(kel))), min(15, len(kel)), key="sl_kel")) if len(kel) > 5 else len(kel)
        sub = kel.head(n).sort_values("JUMLAH")
        fig = px.bar(sub, x="JUMLAH", y="KEL_L", color="KABUPATEN_KOTA", orientation="h", text="JUMLAH", color_discrete_map=cmap,
                     labels={"JUMLAH": "Jumlah data", "KEL_L": "Kelurahan/Desa", "KABUPATEN_KOTA": "Kabupaten/Kota"}, title=f"{n} kelurahan/desa teratas")
        fig.update_traces(textposition="outside", cliponaxis=False)
        show(fig, max(380, n * 26))
    with c2:
        fig = px.histogram(kel, x="JUMLAH", nbins=20, color="KABUPATEN_KOTA", marginal="box", color_discrete_map=cmap,
                           labels={"JUMLAH": "Jumlah data per kelurahan/desa"}, title="Sebaran ukuran kelurahan/desa")
        show(fig, max(380, n * 26))
    note(f"Median {fmt(kel['JUMLAH'].median())} baris per kelurahan/desa (rentang {fmt(kel['JUMLAH'].min())}–{fmt(kel['JUMLAH'].max())}). "
         "Titik di luar kotak pada boxplot adalah wilayah dengan beban menonjol.")

    rw = df.assign(RW_N=pd.to_numeric(df["RW"], errors="coerce"), RT_N=pd.to_numeric(df["RT"], errors="coerce")).dropna(subset=["RW_N", "RT_N"])
    if not rw.empty:
        opts = rw.groupby("KEL_L").size().sort_values(ascending=False).index.tolist()
        pick = st.selectbox("Kelurahan/desa untuk heatmap RW × RT", opts, key="rwrt_pick")
        pv = rw[rw["KEL_L"] == pick].groupby(["RW_N", "RT_N"]).size().unstack(fill_value=0)
        pv.index, pv.columns = pv.index.astype(int), pv.columns.astype(int)
        fig = px.imshow(pv.sort_index().sort_index(axis=1), text_auto=True, aspect="auto", color_continuous_scale="Sunsetdark",
                        labels=dict(x="RT", y="RW", color="Jumlah"), title=f"Sebaran RW × RT di {pick}")
        show(fig, 420)
        note(f"RW/RT terbaca pada {pct(len(rw) / len(df) * 100)} baris aktif.")


def render_stage(df):
    pen = df[df["JENIS_DATA"] == "PENYALURAN"]
    if pen.empty:
        st.info("Tidak ada data penyaluran pada filter aktif.")
        return
    cmap = color_map(pen["KABUPATEN_KOTA"])
    left, right = st.columns(2)
    with left:
        mode = st.radio("Tampilan", ["Jumlah", "Persentase"], horizontal=True, key="stage_mode")
        t = pen.groupby(["KABUPATEN_KOTA", "KET_L"]).size().reset_index(name="JUMLAH")
        t["PERSEN"] = t["JUMLAH"] / t.groupby("KABUPATEN_KOTA")["JUMLAH"].transform("sum") * 100
        ycol = "PERSEN" if mode == "Persentase" else "JUMLAH"
        fig = px.bar(t, x="KABUPATEN_KOTA", y=ycol, color="KET_L", text_auto=".0f" if mode == "Persentase" else True,
                     color_discrete_sequence=PALETTE, labels={"KABUPATEN_KOTA": "Kabupaten/Kota", "KET_L": "Tahap", "JUMLAH": "Jumlah", "PERSEN": "% per kabupaten/kota"},
                     title="Tahap penyaluran per kabupaten/kota")
        show(fig, 430)
    with right:
        s = pen.groupby(["SUMBER_SHEET", "KET_L"]).size().reset_index(name="JUMLAH")
        fig = px.sunburst(s, path=["SUMBER_SHEET", "KET_L"], values="JUMLAH", color_discrete_sequence=PALETTE, title="Sheet sumber › tahap")
        fig.update_traces(hovertemplate="<b>%{label}</b><br>%{value:,}<extra></extra>")
        show(fig, 430)
    rec = pen[pen["KETERANGAN"] != ""]
    if len(rec) < len(pen):
        note(f"Tahap tercatat pada {pct(len(rec) / len(pen) * 100)} baris penyaluran; wilayah tanpa catatan tahap tidak ikut tampil pada grafik tahap yang spesifik.")
    c1, c2 = st.columns(2)
    with c1:
        h = rec[rec["KECAMATAN"] != ""].groupby(["KECAMATAN", "KETERANGAN"]).size().unstack(fill_value=0)
        if not h.empty:
            fig = px.imshow(h, text_auto=True, aspect="auto", color_continuous_scale="Turbo", labels=dict(x="Tahap", y="Kecamatan", color="Jumlah"),
                            title="Heatmap kecamatan × tahap")
            show(fig, max(360, len(h) * 40))
    with c2:
        stg = rec[rec["NIK_VALID_16_DIGIT"]].groupby("NIK")["KETERANGAN"].nunique()
        if len(stg):
            both = int((stg >= 2).sum())
            fig = go.Figure(go.Pie(labels=["Satu tahap", "Dua tahap atau lebih"], values=[len(stg) - both, both], hole=0.55,
                                   marker=dict(colors=["#06D6A0", "#EF476F"])))
            fig.update_layout(title="Penerima yang tercatat di lebih dari satu tahap")
            show(fig, 360)
            note(f"{fmt(both)} dari {fmt(len(stg))} NIK ({pct(both / len(stg) * 100)}) tercatat di ≥2 tahap.")
    inv = int((~pen["NIK_VALID_16_DIGIT"]).sum())
    st.caption(f"Pemeriksaan format NIK: {inv:,} baris penyaluran tidak terdeteksi 16 digit. Baris tetap dipertahankan; ini bukan penetapan data tidak sah.")


def render_demography(df):
    known = df[df["GENDER"].isin(GENDERS)]
    if (df["SUMBER_GENDER"] == "Estimasi NIK").any():
        st.caption("Jenis kelamin dan usia diestimasi dari struktur NIK bila kolom aslinya kosong (data 2025). "
                   "Usia dihitung terhadap tahun masing-masing data. Hasilnya berupa perkiraan.")
    c1, c2 = st.columns(2)
    with c1:
        if known.empty:
            st.info("Data jenis kelamin tidak tersedia.")
        else:
            g = known.groupby("GENDER").size().reset_index(name="JUMLAH")
            fig = px.pie(g, names="GENDER", values="JUMLAH", hole=0.55, color="GENDER", color_discrete_map=GENDER_COLORS, title="Komposisi jenis kelamin")
            fig.update_traces(textinfo="label+percent", textfont_size=14)
            show(fig, 400)
    with c2:
        ages = df[df["USIA"].notna()]
        if ages.empty:
            st.info("Usia tidak dapat dihitung.")
        else:
            fig = px.histogram(ages, x="USIA", nbins=30, color="GENDER", barmode="overlay", opacity=0.75, marginal="box",
                               color_discrete_map=GENDER_COLORS, labels={"USIA": "Usia (tahun)"}, title="Sebaran usia")
            show(fig, 400)
            note(f"Usia rata-rata {num(ages['USIA'].mean())} tahun, median {num(ages['USIA'].median(), 0)}; "
                 f"{pct((ages['USIA'] >= 60).mean() * 100)} berusia 60+ dan {pct((ages['USIA'] < 18).mean() * 100)} di bawah 18 tahun.")

    pyr = known[known["KELOMPOK_USIA"] != ""].groupby(["KELOMPOK_USIA", "GENDER"]).size().unstack(fill_value=0).reindex(index=AGE_LABELS, columns=GENDERS, fill_value=0)
    c1, c2 = st.columns(2)
    with c1:
        if pyr.to_numpy().sum() > 0:
            mx = pyr.to_numpy().max()
            fig = go.Figure()
            fig.add_trace(go.Bar(y=pyr.index, x=-pyr["Laki-laki"], orientation="h", name="Laki-laki", marker_color=GENDER_COLORS["Laki-laki"],
                                 customdata=pyr["Laki-laki"], hovertemplate="%{y}: %{customdata:,}<extra>Laki-laki</extra>"))
            fig.add_trace(go.Bar(y=pyr.index, x=pyr["Perempuan"], orientation="h", name="Perempuan", marker_color=GENDER_COLORS["Perempuan"],
                                 hovertemplate="%{y}: %{x:,}<extra>Perempuan</extra>"))
            ticks = np.linspace(-mx, mx, 5)
            fig.update_layout(barmode="relative", title="Piramida usia × jenis kelamin", yaxis_title="Kelompok usia",
                              xaxis=dict(tickvals=ticks, ticktext=[fmt(abs(t)) for t in ticks], title="Jumlah"), legend=dict(orientation="h", y=1.1))
            show(fig, 430)
            peak = pyr.sum(axis=1).idxmax()
            note(f"Kelompok usia terbesar: {peak} ({pct(pyr.sum(axis=1).max() / pyr.to_numpy().sum() * 100)}).")
    with c2:
        ag = df[df["KELOMPOK_USIA"] != ""]
        if not ag.empty:
            t = ag.groupby(["KELOMPOK_USIA", "TAHUN"]).size().reset_index(name="JUMLAH")
            t["PERSEN"] = t["JUMLAH"] / t.groupby("TAHUN")["JUMLAH"].transform("sum") * 100
            fig = px.bar(t, x="KELOMPOK_USIA", y="PERSEN", color="TAHUN", barmode="group", color_discrete_map=YEAR_COLORS,
                         category_orders={"KELOMPOK_USIA": AGE_LABELS}, labels={"KELOMPOK_USIA": "Kelompok usia", "PERSEN": "% dari tahun tsb"},
                         title="Komposisi kelompok usia (% per tahun)")
            show(fig, 430)

    ages = df[df["USIA"].notna() & (df["KABUPATEN_KOTA"] != "")]
    c1, c2 = st.columns(2)
    if ages["KABUPATEN_KOTA"].nunique() > 0:
        with c1:
            fig = px.violin(ages, x="KABUPATEN_KOTA", y="USIA", color="KABUPATEN_KOTA", box=True, points=False, color_discrete_map=color_map(ages["KABUPATEN_KOTA"]),
                            labels={"USIA": "Usia (tahun)", "KABUPATEN_KOTA": "Kabupaten/Kota"}, title="Sebaran usia per kabupaten/kota")
            fig.update_layout(showlegend=False)
            show(fig, 400)
        with c2:
            gk = known[known["KABUPATEN_KOTA"] != ""].groupby(["KABUPATEN_KOTA", "GENDER"]).size().reset_index(name="JUMLAH")
            gk["PERSEN"] = gk["JUMLAH"] / gk.groupby("KABUPATEN_KOTA")["JUMLAH"].transform("sum") * 100
            fig = px.bar(gk, x="KABUPATEN_KOTA", y="PERSEN", color="GENDER", text_auto=".0f", color_discrete_map=GENDER_COLORS,
                         labels={"KABUPATEN_KOTA": "Kabupaten/Kota", "PERSEN": "% penerima"}, title="Komposisi jenis kelamin per kabupaten/kota (%)")
            show(fig, 400)


def render_desil(df):
    d = df[df["DESIL_NUM"].notna()]
    if d.empty:
        st.info("Data desil tidak tersedia pada filter aktif (desil hanya ada pada data penerima).")
        return
    st.caption(f"Desil tercatat pada {fmt(len(d))} dari {fmt(len(df))} baris aktif ({pct(len(d) / len(df) * 100)}).")
    order = sorted(d["DESIL"].unique(), key=lambda x: int(x.split()[-1]))
    c1, c2 = st.columns(2)
    with c1:
        cnt = d.groupby("DESIL").size().reindex(order).reset_index(name="JUMLAH")
        fig = px.bar(cnt, x="DESIL", y="JUMLAH", text="JUMLAH", color="DESIL", color_discrete_sequence=px.colors.sequential.Plasma_r,
                     labels={"DESIL": "Desil"}, title="Distribusi desil nasional")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        show(fig, 400)
        low = (d["DESIL_NUM"] <= 2).mean() * 100
        note(f"{pct(low)} berada pada desil 1–2 (kelompok paling rentan).")
    with c2:
        g = d[d["GENDER"].isin(GENDERS)].groupby(["DESIL", "GENDER"]).size().reset_index(name="JUMLAH")
        fig = px.bar(g, x="DESIL", y="JUMLAH", color="GENDER", barmode="group", text="JUMLAH", color_discrete_map=GENDER_COLORS,
                     category_orders={"DESIL": order}, labels={"DESIL": "Desil"}, title="Desil × jenis kelamin")
        show(fig, 400)

    c1, c2 = st.columns(2)
    with c1:
        a = d[d["USIA"].notna()]
        if not a.empty:
            fig = px.box(a, x="DESIL", y="USIA", color="DESIL", category_orders={"DESIL": order}, points="outliers",
                         color_discrete_sequence=px.colors.sequential.Plasma_r, labels={"USIA": "Usia (tahun)", "DESIL": "Desil"}, title="Usia menurut desil")
            fig.update_layout(showlegend=False)
            show(fig, 400)
    with c2:
        k = d[d["KELURAHAN"] != ""]
        m = k.groupby(["KECAMATAN", "KELURAHAN"]).agg(JUMLAH=("DESIL_NUM", "size"), PCT=("DESIL_NUM", lambda x: (x <= 2).mean() * 100)).reset_index()
        m = m[m["JUMLAH"] >= 5]
        if not m.empty:
            m["KECAMATAN"] = m["KECAMATAN"].where(m["KECAMATAN"] != "", NO_DATA)
            fig = px.scatter(m, x="JUMLAH", y="PCT", size="JUMLAH", color="KECAMATAN", hover_name="KELURAHAN", color_discrete_sequence=PALETTE,
                             labels={"JUMLAH": "Jumlah penerima", "PCT": "% desil 1–2"}, title="Kelurahan: jumlah penerima vs % desil 1–2")
            fig.add_hline(y=low, line_dash="dash", line_color="gray", annotation_text="rata-rata")
            show(fig, 400)
            note("Kanan-atas = kelurahan besar dengan proporsi rentan tinggi (prioritas); kiri-atas = kecil namun sangat rentan.")

    k = d[d["KELURAHAN"] != ""]
    if not k.empty:
        pv = k.groupby(["KELURAHAN", "DESIL"]).size().unstack(fill_value=0).reindex(columns=order, fill_value=0)
        share = pv.div(pv.sum(axis=1), axis=0) * 100
        share = share.assign(_o=share[[c for c in order if int(c.split()[-1]) <= 2]].sum(axis=1)).sort_values("_o").drop(columns="_o")
        fig = px.imshow(share.round(0), text_auto=".0f", aspect="auto", color_continuous_scale="YlOrRd",
                        labels=dict(x="Desil", y="Kelurahan", color="% penerima"), title="Komposisi desil per kelurahan (% penerima), diurutkan dari desil 1–2 terendah ke tertinggi")
        show(fig, max(420, len(share) * 26))


def render_compare(df):
    years = sorted(df["TAHUN"].unique())
    if len(years) < 2:
        st.info("Perbandingan membutuhkan data minimal dua tahun.")
        return
    y0, y1 = years[0], years[-1]
    st.caption(f"Perbandingan {y0} dengan {y1}. Tab ini mengikuti filter Kabupaten/Kota, tetapi mengabaikan filter Tahun.")
    kab0, kab1 = set(df.loc[df["TAHUN"] == y0, "KABUPATEN_KOTA"]) - {""}, set(df.loc[df["TAHUN"] == y1, "KABUPATEN_KOTA"]) - {""}
    d = df
    if st.checkbox("Bandingkan hanya kabupaten/kota yang ada di kedua tahun", value=True, key="cmp_common"):
        common = kab0 & kab1
        if not common:
            st.info("Tidak ada kabupaten/kota yang muncul di kedua tahun pada filter aktif.")
            return
        d = df[df["KABUPATEN_KOTA"].isin(common)]
        if (kab0 | kab1) - common:
            st.caption("Tidak diikutkan (hanya ada di salah satu tahun): " + ", ".join(sorted((kab0 | kab1) - common)) + ".")
    a, b = d[d["TAHUN"] == y0], d[d["TAHUN"] == y1]
    nik_a, nik_b = set(a.loc[a["NIK_VALID_16_DIGIT"], "NIK"]), set(b.loc[b["NIK_VALID_16_DIGIT"], "NIK"])
    both = nik_a & nik_b
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure(go.Bar(x=[f"Hanya {y0}", "Kedua tahun", f"Hanya {y1}"], y=[len(nik_a - nik_b), len(both), len(nik_b - nik_a)],
                               marker_color=[YEAR_COLORS.get(y0, "#06D6A0"), "#8338EC", YEAR_COLORS.get(y1, "#FFB703")],
                               text=[fmt(len(nik_a - nik_b)), fmt(len(both)), fmt(len(nik_b - nik_a))], textposition="outside"))
        fig.update_layout(title="NIK unik: hanya satu tahun vs muncul di kedua tahun", yaxis_title="Jumlah NIK unik")
        show(fig, 420)
        if nik_b:
            note(f"{pct(len(both) / len(nik_b) * 100)} NIK tahun {y1} juga tercatat pada {y0}. Selisih jumlah antar-tahun belum tentu perubahan kinerja karena cakupan data bisa berbeda.")
    with c2:
        kc = d[d["KECAMATAN"] != ""].groupby(["KECAMATAN", "TAHUN"]).size().reset_index(name="JUMLAH")
        if not kc.empty:
            fig = px.bar(kc, x="KECAMATAN", y="JUMLAH", color="TAHUN", barmode="group", text="JUMLAH", color_discrete_map=YEAR_COLORS, title="Jumlah data per kecamatan")
            fig.update_xaxes(tickangle=-35)
            show(fig, 420)

    rows = []
    for y, g in d.groupby("TAHUN"):
        kn = g[g["GENDER"] != ""]
        rows += [(y, "% Perempuan", (kn["GENDER"] == "Perempuan").mean() * 100 if len(kn) else np.nan),
                 (y, "% usia 60+", (g.loc[g["USIA"].notna(), "USIA"] >= 60).mean() * 100 if g["USIA"].notna().any() else np.nan),
                 (y, "% desil 1–2", (g.loc[g["DESIL_NUM"].notna(), "DESIL_NUM"] <= 2).mean() * 100 if g["DESIL_NUM"].notna().any() else np.nan)]
    prof = pd.DataFrame(rows, columns=["TAHUN", "INDIKATOR", "NILAI"]).dropna()
    if not prof.empty:
        fig = px.bar(prof, x="INDIKATOR", y="NILAI", color="TAHUN", barmode="group", text_auto=".1f", color_discrete_map=YEAR_COLORS,
                     labels={"NILAI": "%", "INDIKATOR": ""}, title="Profil penerima per tahun")
        show(fig, 400)
        note("Indikator yang tidak tersedia pada salah satu tahun (mis. desil 2025) tidak ditampilkan untuk tahun tersebut.")


def render_data(df):
    st.caption("NIK, nama, dan alamat tidak ditampilkan pada tabel ini untuk mengurangi paparan data pribadi.")
    cols = ["TAHUN", "JENIS_DATA", "KABUPATEN_KOTA", "KECAMATAN", "KELURAHAN", "RW", "RT", "DESIL", "GENDER", "USIA", "SUMBER_SHEET", "KETERANGAN"]
    cols = [c for c in cols if c in df.columns and (df[c].astype(str) != "").any()]
    with st.expander("Lihat tabel data", expanded=False):
        st.dataframe(df[cols], use_container_width=True, hide_index=True, height=420)
    with st.expander("Ringkasan kelurahan/desa (tabel)", expanded=False):
        t = df.groupby(["TAHUN", "KABUPATEN_KOTA", "KEC_L", "KEL_L"]).size().reset_index(name="JUMLAH").sort_values("JUMLAH", ascending=False)
        st.dataframe(t, use_container_width=True, hide_index=True, height=360)
    st.download_button("Unduh data terfilter tanpa data pribadi (CSV)", df[cols].to_csv(index=False).encode("utf-8"), "Data_DPS_terfilter.csv", "text/csv")


# ============================================================
# Aplikasi
# ============================================================
def main():
    st.set_page_config(
        page_title="DPS - Dashboard Penyaluran Sembako",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown('<div style="font-size:34px;font-weight:700">Dashboard Penyaluran Sembako</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:16px;color:#666;margin-bottom:22px">Dashboard Monitoring dan Analitik Penyaluran Sembako Provinsi Kepulauan Riau</div>', unsafe_allow_html=True)

    # ---------------- Input ----------------
    st.subheader("Input Data")
    uploaded = st.file_uploader(
        "Upload file Excel gabungan (mis. DataDPS_Gabungan.xlsx)",
        type=["xlsx", "xls"], key="dps_file",
    )
    st.caption("Satu file berisi data 2025 dan 2026. Tahun diambil dari kolom TAHUN_PENYALURAN, jenis data dari kolom JENIS_DATA.")
    if uploaded is None:
        st.info("Upload file Excel untuk mulai melihat indikator, grafik, dan peta.")
        st.stop()

    try:
        df, sheet_names = load_uploaded_workbook(uploaded.getvalue())
    except Exception as exc:
        st.error(f"File tidak dapat diproses: {exc}")
        st.stop()
    if df.empty:
        st.warning("Tidak ada baris data yang dapat ditampilkan.")
        st.stop()

    try:
        if not GEOJSON_PATH.exists():
            st.error(f"GeoJSON tidak ditemukan: {GEOJSON_PATH}")
            st.stop()
        gdf, kab_gdf = load_map(str(GEOJSON_PATH), GEOJSON_PATH.stat().st_mtime)
    except Exception as exc:
        st.error(f"Peta tidak dapat dibaca: {exc}")
        st.stop()

    st.success(f"Data dimuat: {len(df):,} baris. Sheet terdeteksi: {len(sheet_names)}.")

    # ---------------- Filter (sidebar kiri, tanpa kecamatan) ----------------
    st.sidebar.header("Filter")
    years = sorted(df["TAHUN"].unique())
    selected_year = st.sidebar.selectbox("Tahun", ["SEMUA"] + years, key="f_tahun")
    year_df = df if selected_year == "SEMUA" else df[df["TAHUN"] == selected_year]

    kab_available = sorted(x for x in year_df["KABUPATEN_KOTA"].unique() if x)
    kab_options = ["SEMUA"] + kab_available
    if st.session_state.get("f_kab") not in kab_options:
        st.session_state["f_kab"] = "SEMUA"
    selected_kab = st.sidebar.selectbox("Kabupaten/Kota", kab_options, key="f_kab")
    st.session_state["_kab_options"] = kab_options
    st.session_state["_kab_names"] = {k: v for k, v in zip(df["KAB_KEY"], df["KABUPATEN_KOTA"]) if k}

    filtered = year_df if selected_kab == "SEMUA" else year_df[year_df["KABUPATEN_KOTA"] == selected_kab]
    st.sidebar.metric("Baris terpilih", f"{len(filtered):,} / {len(df):,}")

    if filtered.empty:
        st.warning("Tidak ada data pada filter aktif.")
        st.stop()

    # ---------------- KPI ----------------
    st.divider()
    st.subheader("Ringkasan Data")
    kk = filtered["NO_KK"].replace("", pd.NA).nunique()
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Baris Data", f"{len(filtered):,}")
    k2.metric("Nomor KK", f"{kk:,}" if kk else "Tidak tersedia")
    k3.metric("Kabupaten/Kota", f"{filtered['KABUPATEN_KOTA'].replace('', pd.NA).nunique():,}")
    k4.metric("Kecamatan", f"{filtered['KECAMATAN'].replace('', pd.NA).nunique():,}")
    k5.metric("Kelurahan/Desa", f"{filtered['KELURAHAN'].replace('', pd.NA).nunique():,}")

    # ---------------- Peta ----------------
    st.divider()
    st.subheader("Peta Sebaran")
    level = st.radio("Level peta", ["Kabupaten/Kota", "Kecamatan"], horizontal=True)
    # Peta memakai data per tahun (bukan per kabupaten) agar semua wilayah tetap bisa diklik.
    base = year_df
    if level == "Kabupaten/Kota":
        geo, name_col = kab_gdf, "KABUPATEN_KOTA"
        ids = base["KAB_KEY"].where(base["KAB_KEY"].isin(set(kab_gdf["MAP_ID"])))
    else:
        geo, name_col = gdf, "KECAMATAN"
        ids = region_ids(base, gdf)
    unmatched = base[ids.isna()]
    summary = ids.dropna().value_counts().rename_axis("MAP_ID").reset_index(name="JUMLAH_DATA")
    map_gdf = geo.merge(summary, on="MAP_ID", how="left").reset_index(drop=True)
    map_gdf["JUMLAH_DATA"] = map_gdf["JUMLAH_DATA"].fillna(0).astype(int)
    map_gdf["PERSENTASE"] = map_gdf["JUMLAH_DATA"] / max(len(base), 1) * 100

    st.caption("Klik wilayah di peta untuk memfilter Kabupaten/Kota. Pilih SEMUA di sidebar untuk membatalkan. "
               "Peta menampilkan seluruh kabupaten/kota pada tahun terpilih.")
    if len(unmatched):
        pesan = f"{len(unmatched):,} dari {len(base):,} baris tidak dapat diwarnai pada level {level.lower()}"
        if level == "Kecamatan":
            pesan += " karena nama kecamatan kosong atau tidak cocok dengan GeoJSON. Gunakan level Kabupaten/Kota untuk melihat semua baris."
        st.caption(pesan + ".")
        with st.expander("Rincian baris yang tidak terpetakan"):
            u = unmatched.assign(KECAMATAN=unmatched["KECAMATAN"].where(unmatched["KECAMATAN"] != "", NO_DATA))
            st.dataframe(u.groupby(["KABUPATEN_KOTA", "KECAMATAN"]).size().reset_index(name="JUMLAH_BARIS"),
                         use_container_width=True, hide_index=True)

    bounds = geo.total_bounds
    center = {"lat": (bounds[1] + bounds[3]) / 2, "lon": (bounds[0] + bounds[2]) / 2}
    fig_map = px.choropleth_map(
        map_gdf,
        geojson=map_gdf.__geo_interface__,
        locations="MAP_ID",
        featureidkey="properties.MAP_ID",
        color="JUMLAH_DATA",
        color_continuous_scale="Blues",
        map_style="carto-darkmatter",
        zoom=6.3,
        center=center,
        opacity=0.82,
        hover_name=name_col,
        hover_data={"KABUPATEN_KOTA": True, "JUMLAH_DATA": ":,", "PERSENTASE": ":.1f", "MAP_ID": False},
    )
    fig_map.update_traces(
        marker_line_width=1,
        marker_line_color="white",
        hovertemplate="<b>%{hovertext}</b><br>Kabupaten/Kota: %{customdata[0]}<br>Jumlah data: %{customdata[1]:,}<br>Persentase tahun terpilih: %{customdata[2]:.1f}%<extra></extra>",
    )
    if selected_kab != "SEMUA":  # sorot kabupaten yang sedang difilter
        sel_key = key(selected_kab)
        fig_map.update_traces(selectedpoints=[i for i, m in enumerate(map_gdf["MAP_ID"]) if m.split("__")[0] == sel_key])
    fig_map.update_layout(
        height=650,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        coloraxis_colorbar=dict(title="Jumlah Data"),
        uirevision="dps-kepri-map",
        clickmode="event+select",
    )
    chart_key = f"map_{level}_{selected_year}_{selected_kab}"
    st.session_state.setdefault("_map_ids", {})[chart_key] = list(map_gdf["MAP_ID"])
    if _PLOTLY_CAN_SELECT:
        st.plotly_chart(fig_map, use_container_width=True, key=chart_key, selection_mode="points",
                        on_select=lambda k=chart_key: on_map_select(k))
    else:
        st.plotly_chart(fig_map, use_container_width=True)
        st.caption("Versi Streamlit ini belum mendukung klik pada grafik. Update dengan: pip install -U streamlit. Sementara gunakan filter di sidebar.")

    # ---------------- Analisis (tab) ----------------
    st.divider()
    names = ["Ringkasan", "Wilayah", "Tahap & Sumber", "Demografi"]
    has_desil = filtered["DESIL_NUM"].notna().any()
    if has_desil:
        names.append("Desil")
    cmp_df = df if selected_kab == "SEMUA" else df[df["KABUPATEN_KOTA"] == selected_kab]
    multi_year = df["TAHUN"].nunique() > 1
    if multi_year:
        names.append("Antar-Tahun")
    names.append("Data")
    tabs = dict(zip(names, st.tabs(names)))
    with tabs["Ringkasan"]:
        render_overview(filtered)
    with tabs["Wilayah"]:
        render_region(filtered)
    with tabs["Tahap & Sumber"]:
        render_stage(filtered)
    with tabs["Demografi"]:
        render_demography(filtered)
    if has_desil:
        with tabs["Desil"]:
            render_desil(filtered)
    if multi_year:
        with tabs["Antar-Tahun"]:
            render_compare(cmp_df)
    with tabs["Data"]:
        render_data(filtered)

    st.divider()
    st.caption("DPS — Dashboard Penyaluran Sembako | Monitoring dan Analitik Data")


if __name__ == "__main__":
    main()