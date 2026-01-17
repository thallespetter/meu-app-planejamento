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
FOLGAS_FILE = f"{DATA_DIR}/ausencias.parquet"
ARQS_FILE = f"{DATA_DIR}/arquivos_lidos.json"

EQUIPE = [
    "ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO",
    "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"
]

TIPOS_AUSENCIA = [
    "FOLGA",
    "FÉRIAS",
    "AFASTAMENTO",
    "BANCO DE HORAS EXTRAS"
]

TIPOS_DESCONTA_HH = ["FOLGA", "FÉRIAS", "AFASTAMENTO"]

# ======================================================
# PERSISTÊNCIA
# ======================================================
def carregar_parquet(path, cols=None):
    if os.path.exists(path):
        return pd.read_parquet(path)
    return pd.DataFrame(columns=cols if cols else [])

def salvar_parquet(df, path):
    df.to_parquet(path, index=False)

def carregar_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

def salvar_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f)

# ======================================================
# SESSION STATE
# ======================================================
if "db" not in st.session_state:
    st.session_state.db = carregar_parquet(DB_FILE)

if "ausencias" not in st.session_state:
    st.session_state.ausencias = carregar_parquet(
        FOLGAS_FILE, ["Colaborador", "Data", "Tipo"]
    )

if "arquivos" not in st.session_state:
    st.session_state.arquivos = carregar_json(ARQS_FILE)

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
                    hh = int(re.findall(r"\d+", str(r[dur]))[0]) / 60
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
# SIDEBAR – UPLOAD / DELETE ARQUIVOS
# ======================================================
st.sidebar.header("📁 PDFs")

files = st.sidebar.file_uploader("Carregar PDFs", type="pdf", accept_multiple_files=True)

if files:
    for f in files:
        if f.name not in st.session_state.arquivos:
            df = extrair_pdf(f)
            st.session_state.db = pd.concat([st.session_state.db, df]).drop_duplicates()
            st.session_state.arquivos.append(f.name)
            salvar_parquet(st.session_state.db, DB_FILE)
            salvar_json(st.session_state.arquivos, ARQS_FILE)
            st.rerun()

st.sidebar.markdown("### 🗑️ Remover PDF")
arq_del = st.sidebar.selectbox("Arquivo", [""] + st.session_state.arquivos)
if st.sidebar.button("Excluir PDF") and arq_del:
    st.session_state.db = st.session_state.db[
        st.session_state.db["Data"] != st.session_state.db[
            st.session_state.db["Data"].index
        ]
    ]
    st.session_state.arquivos.remove(arq_del)
    salvar_parquet(st.session_state.db, DB_FILE)
    salvar_json(st.session_state.arquivos, ARQS_FILE)
    st.rerun()

# ======================================================
# AUSÊNCIAS – CADASTRAR / EXCLUIR
# ======================================================
st.sidebar.header("🏖️ Ausências")

col = st.sidebar.selectbox("Colaborador", EQUIPE)
tipo = st.sidebar.selectbox("Tipo", TIPOS_AUSENCIA)
di = st.sidebar.date_input("Início")
df = st.sidebar.date_input("Fim")

if st.sidebar.button("Salvar Ausência"):
    datas = [{"Colaborador": col, "Data": d, "Tipo": tipo}
             for d in pd.date_range(di, df)]
    st.session_state.ausencias = pd.concat(
        [st.session_state.ausencias, pd.DataFrame(datas)]
    ).drop_duplicates()
    salvar_parquet(st.session_state.ausencias, FOLGAS_FILE)
    st.success("Salvo!")

st.sidebar.markdown("### 🗑️ Excluir Ausência")
if not st.session_state.ausencias.empty:
    idx = st.sidebar.selectbox(
        "Registro",
        st.session_state.ausencias.index,
        format_func=lambda i: f"{st.session_state.ausencias.loc[i].to_dict()}"
    )
    if st.sidebar.button("Excluir Registro"):
        st.session_state.ausencias = st.session_state.ausencias.drop(idx)
        salvar_parquet(st.session_state.ausencias, FOLGAS_FILE)
        st.rerun()

# ======================================================
# DASHBOARD
# ======================================================
st.title("📊 Gestão HH Automação")

jornada = st.number_input("Jornada Diária (h)", value=8.0)

if not st.session_state.db.empty:
    dias = sorted(st.session_state.db["Data"].unique())

    st.subheader("📅 Detalhe Diário")
    for d in dias:
        with st.expander(d.strftime("%d/%m/%Y")):
            linhas = []
            for p in EQUIPE:
                hh_prog = st.session_state.db[
                    (st.session_state.db["Colaborador"] == p) &
                    (st.session_state.db["Data"] == d)
                ]["HH"].sum()

                aus = st.session_state.ausencias[
                    (st.session_state.ausencias["Colaborador"] == p) &
                    (st.session_state.ausencias["Data"] == d) &
                    (st.session_state.ausencias["Tipo"].isin(TIPOS_DESCONTA_HH))
                ].shape[0]

                hh_disp = jornada - (aus * jornada)
                carga = (hh_prog / hh_disp * 100) if hh_disp > 0 else 0

                linhas.append({
                    "Colaborador": p,
                    "HH Disponível": round(hh_disp, 1),
                    "HH Programado": round(hh_prog, 1),
                    "HH Não Programado": round(hh_disp - hh_prog, 1),
                    "% Carga": f"{carga:.1f}%"
                })

            st.dataframe(pd.DataFrame(linhas), use_container_width=True)

    st.subheader("📊 Resumo de Ausências")
    resumo = st.session_state.ausencias.groupby(
        ["Colaborador", "Tipo"]
    ).size().reset_index(name="Dias")

    resumo["Horas"] = resumo["Dias"] * jornada

    tabela = resumo.pivot_table(
        index="Colaborador",
        columns="Tipo",
        values="Horas",
        fill_value=0
    ).reset_index()

    prog = st.session_state.db.groupby("Colaborador")["HH"].sum()
    disp = len(dias) * jornada

    tabela["% Ausência vs Programado"] = tabela[EQUIPE].sum(axis=1) / prog * 100
    tabela["% Ausência vs Disponível"] = tabela[EQUIPE].sum(axis=1) / disp * 100

    st.dataframe(tabela, use_container_width=True)
