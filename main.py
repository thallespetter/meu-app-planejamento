# ============================================================
# main.py — PLANEJAMENTO DE HH (VERSÃO ESTÁVEL + EXTRAÇÃO DE PDF)
# ============================================================

import streamlit as st
import pandas as pd
import os
import json
import fitz  # PyMuPDF
import re
from email.message import EmailMessage
import smtplib

# ============================================================
# CONFIGURAÇÃO STREAMLIT
# ============================================================
st.set_page_config(page_title="Planejamento de HH", layout="wide")

# ============================================================
# PATHS E CONSTANTES
# ============================================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = os.path.join(DATA_DIR, "programacao.parquet")
AUS_FILE = os.path.join(DATA_DIR, "ausencias.parquet")
ARQ_FILE = os.path.join(DATA_DIR, "arquivos.json")

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
# EXTRAÇÃO DE DADOS DO PDF
# Espera linhas no formato:
# COLABORADOR | DD/MM/YYYY | HH
# Ex: João Silva | 12/01/2026 | 8
# ============================================================
def extrair_dados_pdf(pdf_bytes):
    registros = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    padrao = re.compile(
        r"(?P<col>.+?)\s+\|\s+(?P<data>\d{2}/\d{2}/\d{4})\s+\|\s+(?P<hh>\d+(?:\.\d+)?)"
    )

    for page in doc:
        texto = page.get_text()
        for linha in texto.splitlines():
            m = padrao.search(linha)
            if m:
                registros.append({
                    "Colaborador": m.group("col").strip(),
                    "Data": pd.to_datetime(m.group("data"), dayfirst=True),
                    "HH": float(m.group("hh"))
                })

    return pd.DataFrame(registros)

# ============================================================
# SESSION STATE
# ============================================================
if "db" not in st.session_state:
    st.session_state.db = load_df(DB_FILE, ["Colaborador", "Data", "HH"])

if "ausencias" not in st.session_state:
    st.session_state.ausencias = load_df(AUS_FILE, ["Colaborador", "Data", "Tipo"])

if "arquivos" not in st.session_state:
    st.session_state.arquivos = load_json(ARQ_FILE)

# ============================================================
# SIDEBAR — JORNADA
# ============================================================
st.sidebar.header("Configuração de Jornada")
jornada_h = st.sidebar.number_input(
    "Jornada diária efetiva (h)", 1.0, 12.0, 8.0, 0.5
)

# ============================================================
# SIDEBAR — UPLOAD DE PDFs
# ============================================================
st.sidebar.header("Arquivos PDF")

pdfs = st.sidebar.file_uploader(
    "Carregar PDFs", type=["pdf"], accept_multiple_files=True
)

if pdfs:
    novos_registros = []
    for f in pdfs:
        if f.name not in st.session_state.arquivos:
            df_pdf = extrair_dados_pdf(f.read())
            if not df_pdf.empty:
                novos_registros.append(df_pdf)
            st.session_state.arquivos.append(f.name)

    if novos_registros:
        st.session_state.db = pd.concat(
            [st.session_state.db] + novos_registros,
            ignore_index=True
        ).drop_duplicates()

        save_df(st.session_state.db, DB_FILE)
        save_json(st.session_state.arquivos, ARQ_FILE)

if st.session_state.arquivos:
    arq_excluir = st.sidebar.selectbox(
        "Excluir arquivo carregado", [""] + st.session_state.arquivos
    )
    if arq_excluir and st.sidebar.button("Excluir PDF"):
        st.session_state.arquivos.remove(arq_excluir)
        save_json(st.session_state.arquivos, ARQ_FILE)
        st.sidebar.warning("Arquivo removido (dados permanecem)")

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
        df["Data"].dt.year.isin(f_anos)
        & df["Data"].dt.month.isin(f_meses)
        & df["Colaborador"].isin(f_colabs)
    ]

# ============================================================
# AUSÊNCIAS
# ============================================================
st.header("Ausências")

with st.expander("➕ Lançar / 🗑️ Excluir Ausência", expanded=False):
    if colabs:
        col = st.selectbox("Colaborador", colabs)
        tipo = st.selectbox("Tipo de Ausência", TIPOS_AUSENCIA)
        d_ini = st.date_input("Data inicial")
        d_fim = st.date_input("Data final")

        if st.button("Registrar ausência"):
            datas = pd.date_range(d_ini, d_fim)
            novos = pd.DataFrame({
                "Colaborador": col,
                "Data": datas,
                "Tipo": tipo
            })
            st.session_state.ausencias = pd.concat(
                [st.session_state.ausencias, novos]
            ).drop_duplicates()
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
        if st.button("Excluir registro"):
            st.session_state.ausencias = st.session_state.ausencias.drop(idx)
            save_df(st.session_state.ausencias, AUS_FILE)
            st.warning("Ausência removida")

# ============================================================
# BASE DIÁRIA
# ============================================================
base = pd.DataFrame(
    columns=["Colaborador", "Data", "HH_Programado", "HH_Disponivel", "Tipo"]
)

if not df.empty:
    prog = (
        df.groupby(["Colaborador", "Data"], as_index=False)
        .agg(HH_Programado=("HH", "sum"))
    )
    prog["HH_Disponivel"] = jornada_h

    aus = st.session_state.ausencias.copy()
    if not aus.empty:
        aus["Data"] = pd.to_datetime(aus["Data"])

    base = prog.merge(aus, on=["Colaborador", "Data"], how="left")

    base.loc[
        base["Tipo"].isin(["FÉRIAS", "AFASTAMENTO", "BANCO DE HORAS"]),
        "HH_Disponivel"
    ] = 0

# ============================================================
# ABAS
# ============================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "Resumo Geral",
    "Relatório Diário",
    "Resumo dos Afastamentos",
    "Resumo Geral de Afastamentos"
])

# ============================================================
# RESUMO GERAL
# ============================================================
with tab1:
    if not base.empty:
        resumo = base.groupby("Colaborador", as_index=False).agg(
            Dias=("Data", "count"),
            HH_Disponivel=("HH_Disponivel", "sum"),
            HH_Programado=("HH_Programado", "sum")
        )
        resumo["%Carga"] = resumo.apply(
            lambda r: r["HH_Programado"] / r["HH_Disponivel"]
            if r["HH_Disponivel"] > 0 else 0,
            axis=1
        )
        st.dataframe(resumo, use_container_width=True)

# ============================================================
# RELATÓRIO DIÁRIO
# ============================================================
with tab2:
    if not base.empty:
        diario = base.copy()
        diario["%Carga Dia"] = diario.apply(
            lambda r: r["HH_Programado"] / r["HH_Disponivel"]
            if r["HH_Disponivel"] > 0 else 0,
            axis=1
        )
        st.dataframe(diario, use_container_width=True)

# ============================================================
# RESUMO DOS AFASTAMENTOS
# ============================================================
with tab3:
    st.dataframe(st.session_state.ausencias, use_container_width=True)

# ============================================================
# RESUMO GERAL DE AFASTAMENTOS
# ============================================================
with tab4:
    if not base.empty:
        aus_calc = base[base["Tipo"].isin(["FOLGA", "AFASTAMENTO"])]
        dias = (
            aus_calc.groupby(["Colaborador", "Tipo"], as_index=False)
            .size()
            .rename(columns={"size": "Dias"})
        )

        tabela = dias.pivot_table(
            index="Colaborador",
            columns="Tipo",
            values="Dias",
            fill_value=0
        ).reset_index()

        totais = base.groupby("Colaborador", as_index=False).agg(
            HH_Prog=("HH_Programado", "sum"),
            HH_Disp=("HH_Disponivel", "sum")
        )

        tabela = tabela.merge(totais, on="Colaborador", how="left")

        tabela["% Ausência vs Programado"] = (
            (tabela.get("FOLGA", 0) + tabela.get("AFASTAMENTO", 0)) * jornada_h
        ) / tabela["HH_Prog"].replace(0, pd.NA)

        tabela["% Ausência vs Disponível"] = (
            (tabela.get("FOLGA", 0) + tabela.get("AFASTAMENTO", 0)) * jornada_h
        ) / tabela["HH_Disp"].replace(0, pd.NA)

        st.dataframe(tabela.fillna(0), use_container_width=True)

# ============================================================
# EMAIL
# ============================================================
st.header("Enviar relatório por e-mail")

emails = st.text_input("E-mails (separados por vírgula)")

if st.button("Enviar relatório"):
    msg = EmailMessage()
    msg["Subject"] = "Relatório Planejamento de HH"
    msg["From"] = "seu_email@empresa.com"
    msg["To"] = emails
    msg.set_content("Relatório gerado automaticamente pelo sistema.")

    try:
        with smtplib.SMTP("smtp.empresa.com", 25) as smtp:
            smtp.send_message(msg)
        st.success("E-mail enviado com sucesso")
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")
