# =========================
# main.py – APLICATIVO COMPLETO E ESTÁVEL
# =========================

import streamlit as st
import pandas as pd
import os
import json
import datetime as dt
import smtplib
from email.message import EmailMessage

# =========================
# CONFIGURAÇÕES GERAIS
# =========================
st.set_page_config(page_title="Planejamento de HH", layout="wide")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = f"{DATA_DIR}/programacao.parquet"
FOLGAS_FILE = f"{DATA_DIR}/ausencias.parquet"
ARQS_FILE = f"{DATA_DIR}/arquivos.json"

TIPOS_AUSENCIA = ["BANCO DE HORAS", "FOLGA", "FÉRIAS", "AFASTAMENTO"]

# =========================
# FUNÇÕES DE PERSISTÊNCIA
# =========================
def carregar_df(path, cols=None):
    if os.path.exists(path):
        return pd.read_parquet(path)
    return pd.DataFrame(columns=cols if cols else [])

def salvar_df(df, path):
    df.to_parquet(path, index=False)

def carregar_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

def salvar_json(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f)

# =========================
# CARGA INICIAL
# =========================
if "db" not in st.session_state:
    st.session_state.db = carregar_df(DB_FILE)

if "ausencias" not in st.session_state:
    st.session_state.ausencias = carregar_df(
        FOLGAS_FILE, ["Colaborador", "Data", "Tipo"]
    )

if "arquivos" not in st.session_state:
    st.session_state.arquivos = carregar_json(ARQS_FILE)

# =========================
# SIDEBAR – JORNADA
# =========================
st.sidebar.header("Configuração de Jornada")
jornada_h = st.sidebar.number_input(
    "Jornada diária efetiva (h)",
    min_value=1.0,
    max_value=12.0,
    value=8.0,
    step=0.5
)

# =========================
# SIDEBAR – UPLOAD DE ARQUIVOS
# =========================
st.sidebar.header("Arquivos PDF")

uploaded = st.sidebar.file_uploader(
    "Carregar PDFs", type=["pdf"], accept_multiple_files=True
)

if uploaded:
    novos = []
    for f in uploaded:
        if f.name not in st.session_state.arquivos:
            novos.append(f.name)
    if novos:
        st.session_state.arquivos.extend(novos)
        salvar_json(st.session_state.arquivos, ARQS_FILE)
        st.sidebar.success("Arquivos adicionados")

if st.session_state.arquivos:
    arq_del = st.sidebar.selectbox(
        "Excluir arquivo carregado",
        [""] + st.session_state.arquivos
    )
    if arq_del and st.sidebar.button("Excluir arquivo"):
        st.session_state.arquivos.remove(arq_del)
        salvar_json(st.session_state.arquivos, ARQS_FILE)
        st.sidebar.warning("Arquivo removido")

if st.sidebar.button("Limpar todo cache do sistema"):
    st.session_state.db = pd.DataFrame()
    st.session_state.ausencias = pd.DataFrame(
        columns=["Colaborador", "Data", "Tipo"]
    )
    st.session_state.arquivos = []
    for f in [DB_FILE, FOLGAS_FILE, ARQS_FILE]:
        if os.path.exists(f):
            os.remove(f)
    st.rerun()

# =========================
# SIDEBAR – FILTROS
# =========================
st.sidebar.header("Filtros")

def multiselect_or_all(label, options):
    sel = st.sidebar.multiselect(label, options)
    return sel if sel else options

if not st.session_state.db.empty:
    st.session_state.db["Data"] = pd.to_datetime(st.session_state.db["Data"])

anos = sorted(st.session_state.db["Data"].dt.year.unique()) if not st.session_state.db.empty else []
meses = list(range(1, 13))
colabs = sorted(st.session_state.db["Colaborador"].unique()) if not st.session_state.db.empty else []

f_anos = multiselect_or_all("Ano", anos)
f_meses = multiselect_or_all("Mês", meses)
f_colabs = multiselect_or_all("Colaborador", colabs)

# =========================
# BASE FILTRADA
# =========================
df = st.session_state.db.copy()

if not df.empty:
    df = df[
        (df["Data"].dt.year.isin(f_anos)) &
        (df["Data"].dt.month.isin(f_meses)) &
        (df["Colaborador"].isin(f_colabs))
    ]

# =========================
# ABA – LANÇAMENTO DE AUSÊNCIA
# =========================
st.header("Lançamento de Ausências")

with st.expander("Lançar nova ausência"):
    c = st.selectbox("Colaborador", colabs)
    t = st.selectbox("Tipo", TIPOS_AUSENCIA)
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
        salvar_df(st.session_state.ausencias, FOLGAS_FILE)
        st.success("Ausência registrada")

with st.expander("Excluir ausência"):
    if not st.session_state.ausencias.empty:
        idx = st.selectbox(
            "Selecione o registro",
            st.session_state.ausencias.index,
            format_func=lambda i: (
                f"{st.session_state.ausencias.loc[i,'Colaborador']} | "
                f"{st.session_state.ausencias.loc[i,'Tipo']} | "
                f"{st.session_state.ausencias.loc[i,'Data'].date()}"
            )
        )
        if st.button("Excluir ausência selecionada"):
            st.session_state.ausencias = st.session_state.ausencias.drop(idx)
            salvar_df(st.session_state.ausencias, FOLGAS_FILE)
            st.warning("Ausência removida")

# =========================
# PREPARAÇÃO DE BASE DIÁRIA
# =========================
if not df.empty:
    base = (
        df.groupby(["Colaborador", "Data"])
        .agg(HH_Programado=("HH", "sum"))
        .reset_index()
    )

    base["HH_Disponivel_Base"] = jornada_h

    aus = st.session_state.ausencias.copy()
    aus["Data"] = pd.to_datetime(aus["Data"])

    base = base.merge(
        aus,
        on=["Colaborador", "Data"],
        how="left"
    )

    base["Ausente"] = base["Tipo"].isin(
        ["FÉRIAS", "AFASTAMENTO", "BANCO DE HORAS"]
    )

    base["HH_Disponivel"] = base.apply(
        lambda r: 0 if r["Ausente"] else r["HH_Disponivel_Base"],
        axis=1
    )

    base["HH_Nao_Programado"] = (
        base["HH_Disponivel"] - base["HH_Programado"]
    ).clip(lower=0)

    base["%Carga"] = base.apply(
        lambda r: (r["HH_Programado"] / r["HH_Disponivel"])
        if r["HH_Disponivel"] > 0 else 0,
        axis=1
    )

# =========================
# ABAS DE RELATÓRIO
# =========================
tab1, tab2, tab3, tab4 = st.tabs([
    "Resumo Geral",
    "Relatório Diário",
    "Resumo dos Afastamentos",
    "Resumo Geral de Afastamentos"
])

# =========================
# RESUMO GERAL
# =========================
with tab1:
    if not df.empty:
        resumo = (
            base.groupby("Colaborador")
            .agg(
                Dias=("Data", "count"),
                HH_Disponivel=("HH_Disponivel", "sum"),
                HH_Programado=("HH_Programado", "sum")
            )
            .reset_index()
        )

        resumo["%Carga"] = resumo.apply(
            lambda r: r["HH_Programado"] / r["HH_Disponivel"]
            if r["HH_Disponivel"] > 0 else 0,
            axis=1
        )

        st.subheader("Resumo por colaborador")
        st.dataframe(resumo, use_container_width=True)

        st.subheader("Resumo da equipe")
        st.metric("Dias totais", resumo["Dias"].sum())
        st.metric("HH Total Disponível", resumo["HH_Disponivel"].sum())
        st.metric("HH Total Programado", resumo["HH_Programado"].sum())
        st.metric(
            "% Carga Total",
            resumo["HH_Programado"].sum() /
            resumo["HH_Disponivel"].sum()
            if resumo["HH_Disponivel"].sum() > 0 else 0
        )

# =========================
# RELATÓRIO DIÁRIO
# =========================
with tab2:
    if not df.empty:
        diario = base.copy()
        diario["%Carga Dia"] = diario["%Carga"]
        st.dataframe(diario, use_container_width=True)

# =========================
# RESUMO DOS AFASTAMENTOS (DETALHE)
# =========================
with tab3:
    if not st.session_state.ausencias.empty:
        st.dataframe(
            st.session_state.ausencias.sort_values(
                ["Colaborador", "Data"]
            ),
            use_container_width=True
        )

# =========================
# RESUMO GERAL DE AFASTAMENTOS
# =========================
with tab4:
    if not base.empty:
        aus_hh = (
            base[base["Tipo"].isin(["FOLGA", "AFASTAMENTO"])]
            .groupby(["Colaborador", "Tipo"])
            .agg(HH=("HH_Disponivel_Base", "sum"))
            .reset_index()
        )

        tabela = aus_hh.pivot_table(
            index="Colaborador",
            columns="Tipo",
            values="HH",
            fill_value=0
        ).reset_index()

        tot = (
            base.groupby("Colaborador")
            .agg(
                HH_Prog=("HH_Programado", "sum"),
                HH_Disp=("HH_Disponivel", "sum")
            )
            .reset_index()
        )

        tabela = tabela.merge(tot, on="Colaborador", how="left")

        tabela["% Ausência vs Programado"] = (
            (tabela.get("FOLGA", 0) + tabela.get("AFASTAMENTO", 0))
            / tabela["HH_Prog"]
        ).fillna(0)

        tabela["% Ausência vs Disponível"] = (
            (tabela.get("FOLGA", 0) + tabela.get("AFASTAMENTO", 0))
            / tabela["HH_Disp"]
        ).fillna(0)

        st.dataframe(tabela, use_container_width=True)

# =========================
# ENVIO POR EMAIL
# =========================
st.header("Enviar relatório por e-mail")

emails = st.text_input(
    "E-mails (separados por vírgula)"
)

if st.button("Enviar relatório"):
    msg = EmailMessage()
    msg["Subject"] = "Relatório de Planejamento de HH"
    msg["From"] = "seu_email@empresa.com"
    msg["To"] = emails

    msg.set_content(
        "Relatório gerado pelo sistema de Planejamento de HH.\n\n"
        "Resumo Geral, Relatório Diário e Ausências conforme filtros."
    )

    try:
        with smtplib.SMTP("smtp.empresa.com", 25) as s:
            s.send_message(msg)
        st.success("E-mail enviado")
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")
