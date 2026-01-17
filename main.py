# ============================================================
# main.py — APLICATIVO DE PLANEJAMENTO DE HH (VERSÃO ESTÁVEL)
# ============================================================

import streamlit as st
import pandas as pd
import os
import json
import smtplib
from email.message import EmailMessage

st.set_page_config(page_title="Planejamento de HH", layout="wide")

# ============================================================
# CONFIGURAÇÕES E ARQUIVOS
# ============================================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = f"{DATA_DIR}/programacao.parquet"
AUS_FILE = f"{DATA_DIR}/ausencias.parquet"
ARQ_FILE = f"{DATA_DIR}/arquivos.json"

TIPOS_AUSENCIA = ["BANCO DE HORAS", "FOLGA", "FÉRIAS", "AFASTAMENTO"]

# ============================================================
# FUNÇÕES DE PERSISTÊNCIA
# ============================================================
def load_df(path, cols):
    if os.path.exists(path):
        return pd.read_parquet(path)
    return pd.DataFrame(columns=cols)

def save_df(df, path):
    df.to_parquet(path, index=False)

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

def save_json(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f)

# ============================================================
# SESSION STATE
# ============================================================
if "db" not in st.session_state:
    st.session_state.db = load_df(DB_FILE, ["Colaborador", "Data", "HH"])

if "ausencias" not in st.session_state:
    st.session_state.ausencias = load_df(
        AUS_FILE, ["Colaborador", "Data", "Tipo"]
    )

if "arquivos" not in st.session_state:
    st.session_state.arquivos = load_json(ARQ_FILE)

# ============================================================
# SIDEBAR — JORNADA
# ============================================================
st.sidebar.header("Configuração de Jornada")
jornada_h = st.sidebar.number_input(
    "Jornada diária efetiva (h)",
    min_value=1.0,
    max_value=12.0,
    value=8.0,
    step=0.5
)

# ============================================================
# SIDEBAR — ARQUIVOS PDF
# ============================================================
st.sidebar.header("Arquivos PDF")

uploaded = st.sidebar.file_uploader(
    "Carregar PDFs", type=["pdf"], accept_multiple_files=True
)

if uploaded:
    for f in uploaded:
        if f.name not in st.session_state.arquivos:
            st.session_state.arquivos.append(f.name)
    save_json(st.session_state.arquivos, ARQ_FILE)

if st.session_state.arquivos:
    arq_del = st.sidebar.selectbox(
        "Excluir arquivo carregado",
        [""] + st.session_state.arquivos
    )
    if arq_del and st.sidebar.button("Excluir PDF"):
        st.session_state.arquivos.remove(arq_del)
        save_json(st.session_state.arquivos, ARQ_FILE)
        st.sidebar.success("Arquivo removido")

if st.sidebar.button("Limpar todo cache do sistema"):
    for f in [DB_FILE, AUS_FILE, ARQ_FILE]:
        if os.path.exists(f):
            os.remove(f)
    st.session_state.clear()
    st.rerun()

# ============================================================
# FILTROS
# ============================================================
st.sidebar.header("Filtros")

if not st.session_state.db.empty:
    st.session_state.db["Data"] = pd.to_datetime(st.session_state.db["Data"])

anos = sorted(st.session_state.db["Data"].dt.year.unique()) if not st.session_state.db.empty else []
meses = list(range(1, 13))
colabs = sorted(st.session_state.db["Colaborador"].unique()) if not st.session_state.db.empty else []

f_anos = st.sidebar.multiselect("Ano", anos, default=anos)
f_meses = st.sidebar.multiselect("Mês", meses, default=meses)
f_colabs = st.sidebar.multiselect("Colaborador", colabs, default=colabs)

# ============================================================
# BASE FILTRADA
# ============================================================
df = st.session_state.db.copy()
if not df.empty:
    df = df[
        (df["Data"].dt.year.isin(f_anos)) &
        (df["Data"].dt.month.isin(f_meses)) &
        (df["Colaborador"].isin(f_colabs))
    ]

# ============================================================
# AUSÊNCIAS — EXPANDER
# ============================================================
st.header("Ausências")

with st.expander("➕ Lançar / 🗑️ Excluir Ausência", expanded=False):
    c = st.selectbox("Colaborador", colabs)
    t = st.selectbox("Tipo de Ausência", TIPOS_AUSENCIA)
    d_ini = st.date_input("Data inicial")
    d_fim = st.date_input("Data final")

    if st.button("Registrar ausência"):
        datas = pd.date_range(d_ini, d_fim, freq="D")
        novos = pd.DataFrame({
            "Colaborador": c,
            "Data": datas,
            "Tipo": t
        })
        st.session_state.ausencias = (
            pd.concat([st.session_state.ausencias, novos])
            .drop_duplicates()
        )
        save_df(st.session_state.ausencias, AUS_FILE)
        st.success("Ausência registrada")

    if not st.session_state.ausencias.empty:
        idx = st.selectbox(
            "Excluir ausência",
            st.session_state.ausencias.index,
            format_func=lambda i: (
                f"{st.session_state.ausencias.loc[i,'Colaborador']} | "
                f"{st.session_state.ausencias.loc[i,'Tipo']} | "
                f"{pd.to_datetime(st.session_state.ausencias.loc[i,'Data']).date()}"
            )
        )
        if st.button("Excluir registro selecionado"):
            st.session_state.ausencias = st.session_state.ausencias.drop(idx)
            save_df(st.session_state.ausencias, AUS_FILE)
            st.warning("Ausência removida")

# ============================================================
# BASE DIÁRIA (SEMPRE EXISTE)
# ============================================================
base =
