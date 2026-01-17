import streamlit as st
import pandas as pd
import fitz
import re
import unicodedata
import os
import json
from datetime import datetime, timedelta

# ======================================================
# CONFIGURAÇÃO
# ======================================================
st.set_page_config(page_title="Gestão HH Automação", layout="wide")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = f"{DATA_DIR}/db_programacao.parquet"
AUS_FILE = f"{DATA_DIR}/ausencias.parquet"
ARQS_FILE = f"{DATA_DIR}/arquivos_lidos.json"

EQUIPE = [
    "ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO",
    "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"
]

TIPOS_AUSENCIA = [
    "FOLGA", "FÉRIAS", "AFASTAMENTO", "BANCO DE HORAS EXTRAS"
]

TIPOS_DESCONTA = ["FOLGA", "FÉRIAS", "AFASTAMENTO"]

# ======================================================
# PERSISTÊNCIA
# ======================================================
def load_parquet(path, cols=None):
    if os.path.exists(path):
        return pd.read_parquet(path)
    return pd.DataFrame(columns=cols or [])

def save_parquet(df, path):
    df.to_parquet(path, index=False)

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

def save_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f)

# ======================================================
# SESSION STATE
# ======================================================
if "db" not in st.session_state:
    st.session_state.db = load_parquet(DB_FILE)

if "aus" not in st.session_state:
    st.session_state.aus = load_parquet(
        AUS_FILE, ["Colaborador", "Data", "Tipo"]
    )

if "arquivos" not in st.session_state:
    st.session_state.arquivos = load_json(ARQS_FILE)

# ======================================================
# FUNÇÕES AUX
# ======================================================
def normalizar(txt):
    return "".join(
        c for c in unicodedata.normalize("NFD", str(txt).upper())
        if unicodedata.category(c) != "Mn"
    )

def identificar_colab(txt):
    t = normalizar(txt)
    if "GERALDO" in t:
        return "JOSÉ GERALDO"
    for n in EQUIPE:
        if normalizar(n) in t:
            return n
    return None

def extrair_pdf(file):
    doc = fitz.open(stream=file.getvalue(), filetype="pdf")
    dados = []

    data_ref = datetime.now().date()
    txt = doc[0].get_text()
    dt = re.search(r"\d{2}/\d{2}/\d{2}", txt)
    if dt:
        data_ref = datetime.strptime(dt.group(), "%d/%m/%y").date()

    for p in doc:
        for t in p.find_tables():
            df = t.to_pandas()
            df.columns = df.columns.str.lower()

            sup = next((c for c in df.columns if "superv" in c), None)
            rec = next((c for c in df.columns if "recursos" in c), None)
            dur = next((c for c in df.columns if "dura" in c), None)

            if sup and rec and dur:
                df = df[df[sup].astype(str).str.contains("Automação", case=False)]
                for _, r in df.iterrows():
                    nums = re.findall(r"\d+", str(r[dur]))
                    if not nums:
                        continue
                    hh = int(nums[0]) / 60
                    for nome in str(r[rec]).split(";"):
                        col = identificar_colab(nome)
                        if col:
                            dados.append({
                                "Colaborador": col,
                                "HH": hh,
                                "Data": data_ref,
                                "Ano": data_ref.year,
                                "Mês": data_ref.strftime("%m - %B")
                            })

    return pd.DataFrame(dados)

# ======================================================
# SIDEBAR – PDFs
# ======================================================
st.sidebar.header("📁 PDFs")
files = st.sidebar.file_uploader(
    "Carregar PDFs", type="pdf", accept_multiple_files=True
)

if files:
    for f in files:
        if f.name not in st.session_state.arquivos:
            df = extrair_pdf(f)
            if not df.empty:
                st.session_state.db = pd.concat(
                    [st.session_state.db, df]
                ).drop_duplicates()
                st.session_state.arquivos.append(f.name)
                save_parquet(st.session_state.db, DB_FILE)
                save_json(st.session_state.arquivos, ARQS_FILE)
                st.rerun()

# ======================================================
# SIDEBAR – AUSÊNCIAS
# ======================================================
st.sidebar.header("🏖️ Ausências")

col = st.sidebar.selectbox("Colaborador", EQUIPE)
tipo = st.sidebar.selectbox("Tipo", TIPOS_AUSENCIA)
di = st.sidebar.date_input("Início")
dfim = st.sidebar.date_input("Fim")

if st.sidebar.button("Salvar Ausência"):
    registros = [{
        "Colaborador": col,
        "Data": d.date(),
        "Tipo": tipo
    } for d in pd.date_range(di, dfim)]

    st.session_state.aus = pd.concat(
        [st.session_state.aus, pd.DataFrame(registros)]
    ).drop_duplicates()

    save_parquet(st.session_state.aus, AUS_FILE)
    st.success("Ausência registrada")

# ======================================================
# FILTROS
# ======================================================
st.sidebar.markdown("---")
st.sidebar.header("🔍 Filtros")

if not st.session_state.db.empty:
    anos = sorted(st.session_state.db["Ano"].unique())
    meses = sorted(st.session_state.db["Mês"].unique())
    f_ano = st.sidebar.multiselect("Ano", anos, default=anos)
    f_mes = st.sidebar.multiselect("Mês", meses, default=meses)
    f_col = st.sidebar.multiselect("Colaborador", EQUIPE, default=EQUIPE)

    dbf = st.session_state.db[
        (st.session_state.db["Ano"].isin(f_ano)) &
        (st.session_state.db["Mês"].isin(f_mes)) &
        (st.session_state.db["Colaborador"].isin(f_col))
    ]
else:
    dbf = pd.DataFrame()

# ======================================================
# DASHBOARD
# ======================================================
st.title("📊 Gestão HH Automação")
jornada = st.number_input("Jornada Diária (h)", value=8.0)

if not dbf.empty:
    dias = sorted(dbf["Data"].unique())
    n_dias = len(dias)

    # ================= RELATÓRIO GERAL =================
    st.subheader("📈 Relatório Geral")

    resumo = []
    for p in f_col:
        hh_prog = dbf[dbf["Colaborador"] == p]["HH"].sum()

        dias_aus = st.session_state.aus[
            (st.session_state.aus["Colaborador"] == p) &
            (st.session_state.aus["Data"].isin(dias)) &
            (st.session_state.aus["Tipo"].isin(TIPOS_DESCONTA))
        ].shape[0]

        hh_disp = (n_dias - dias_aus) * jornada
        carga = (hh_prog / hh_disp * 100) if hh_disp > 0 else 0

        resumo.append({
            "Colaborador": p,
            "HH Disponível": hh_disp,
            "HH Programado": hh_prog,
            "HH Não Programado": hh_disp - hh_prog,
            "% Carga": round(carga, 1)
        })

    st.dataframe(pd.DataFrame(resumo), use_container_width=True)

    # ================= DETALHE DIÁRIO =================
    st.subheader("📅 Detalhe Diário")
    for d in dias:
        with st.expander(d.strftime("%d/%m/%Y")):
            linhas = []
            for p in f_col:
                hh_prog = dbf[
                    (dbf["Colaborador"] == p) &
                    (dbf["Data"] == d)
                ]["HH"].sum()

                aus = st.session_state.aus[
                    (st.session_state.aus["Colaborador"] == p) &
                    (st.session_state.aus["Data"] == d) &
                    (st.session_state.aus["Tipo"].isin(TIPOS_DESCONTA))
                ].shape[0]

                hh_disp = jornada - (aus * jornada)
                carga = (hh_prog / hh_disp * 100) if hh_disp > 0 else 0

                linhas.append({
                    "Colaborador": p,
                    "HH Disponível": hh_disp,
                    "HH Programado": hh_prog,
                    "HH Não Programado": hh_disp - hh_prog,
                    "% Carga": round(carga, 1)
                })

            st.dataframe(pd.DataFrame(linhas), use_container_width=True)

    # ================= RESUMO AUSÊNCIAS =================
    st.subheader("📊 Resumo de Ausências")

    aus = st.session_state.aus[
        st.session_state.aus["Colaborador"].isin(f_col)
    ]

    if not aus.empty:
        res = aus.groupby(
            ["Colaborador", "Tipo"]
        ).size().reset_index(name="Dias")

        res["Horas"] = res["Dias"] * jornada

        tabela = res.pivot_table(
            index="Colaborador",
            columns="Tipo",
            values="Horas",
            fill_value=0
        ).reset_index()

        tabela["Total Horas Ausência"] = tabela[
            [c for c in tabela.columns if c in TIPOS_AUSENCIA]
        ].sum(axis=1)

        prog = dbf.groupby("Colaborador")["HH"].sum()
        disp = (n_dias * jornada)

        tabela["% Ausência vs Programado"] = tabela["Colaborador"].map(
            lambda c: (tabela.loc[tabela["Colaborador"] == c, "Total Horas Ausência"].values[0] / prog.get(c, 1)) * 100
        )

        tabela["% Ausência vs Disponível"] = tabela["Total Horas Ausência"] / disp * 100

        st.dataframe(tabela, use_container_width=True)
else:
    st.info("Carregue PDFs para visualizar os dados.")
