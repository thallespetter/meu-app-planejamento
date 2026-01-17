import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import unicodedata
import os
import json
from datetime import datetime, timedelta

# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================
st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# =========================================================
# PERSISTÊNCIA DE DADOS
# =========================================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = f"{DATA_DIR}/db_programacao.parquet"
FOLGAS_FILE = f"{DATA_DIR}/folgas.parquet"
ARQS_FILE = f"{DATA_DIR}/arquivos_lidos.json"


def carregar_db():
    return pd.read_parquet(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame()


def salvar_db(df):
    df.to_parquet(DB_FILE, index=False)


def carregar_folgas():
    if os.path.exists(FOLGAS_FILE):
        df = pd.read_parquet(FOLGAS_FILE)
        if not df.empty and "Data" in df.columns:
            df["Data"] = pd.to_datetime(df["Data"]).dt.date
        return df
    return pd.DataFrame(columns=["Colaborador", "Data", "Tipo"])


def salvar_folgas(df):
    df.to_parquet(FOLGAS_FILE, index=False)


def carregar_arquivos():
    if os.path.exists(ARQS_FILE):
        with open(ARQS_FILE, "r") as f:
            return json.load(f)
    return []


def salvar_arquivos(lista):
    with open(ARQS_FILE, "w") as f:
        json.dump(lista, f)


# =========================================================
# INICIALIZAÇÃO DE SESSÃO
# =========================================================
if "db_pd" not in st.session_state:
    st.session_state.db_pd = carregar_db()

if "folgas" not in st.session_state:
    st.session_state.folgas = carregar_folgas()

if "arquivos_lidos" not in st.session_state:
    st.session_state.arquivos_lidos = carregar_arquivos()

# =========================================================
# DADOS FIXOS
# =========================================================
st.title("📊 Gestão de Planejamento - Automação")

EQUIPE = [
    "ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO",
    "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"
]

TIPOS_FOLGA = ["FOLGA", "FÉRIAS", "AFASTAMENTO"]


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================
def normalizar(txt):
    if not txt or pd.isna(txt):
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(txt).upper())
        if unicodedata.category(c) != "Mn"
    ).strip()


def identificar_colab(texto):
    t = normalizar(texto)
    if not t:
        return None
    if "GERALDO" in t:
        return "JOSÉ GERALDO"
    for nome in EQUIPE:
        if normalizar(nome) in t:
            return nome
    return None


def extrair_dados_pdf_seguro(file_obj):
    try:
        file_bytes = file_obj.getvalue()
        if not file_bytes:
            return pd.DataFrame()

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        dados_lista = []
        data_ref = datetime.now().date()

        primeira_pag_texto = doc[0].get_text()
        dt_match = re.search(r"\d{2}/\d{2}/\d{2}", primeira_pag_texto)
        if dt_match:
            try:
                data_ref = datetime.strptime(dt_match.group(), "%d/%m/%y").date()
            except:
                pass

        for page in doc:
            tabs = page.find_tables()
            for tab in tabs:
                df = tab.to_pandas()
                df.columns = [str(c).lower().replace("\n", " ") for c in df.columns]

                idx_sup = next((c for c in df.columns if "superv" in c), None)
                idx_rec = next((c for c in df.columns if "recursos" in c or "nomes" in c), None)
                idx_dur = next((c for c in df.columns if "dura" in c), None)

                if idx_sup and idx_rec and idx_dur:
                    df_aut = df[df[idx_sup].astype(str).str.contains("Automação", case=False, na=False)]
                    for _, row in df_aut.iterrows():
                        nums = re.findall(r"\d+", str(row[idx_dur]))
                        hh_val = int(nums[0]) / 60 if nums else 0
                        nomes = str(row[idx_rec]).replace("\n", " ").split(";")
                        for n in nomes:
                            colab = identificar_colab(n)
                            if colab:
                                dados_lista.append({
                                    "Colaborador": colab,
                                    "HH": hh_val,
                                    "Data": data_ref,
                                    "Ano": data_ref.year,
                                    "Mês": data_ref.strftime("%m - %B"),
                                    "Arquivo": file_obj.name
                                })

        doc.close()
        return pd.DataFrame(dados_lista)

    except Exception as e:
        st.error(f"Erro ao processar PDF: {e}")
        return pd.DataFrame()


# =========================================================
# SIDEBAR – ENTRADA DE DADOS
# =========================================================
st.sidebar.header("📁 Entrada de Dados")
uploaded_files = st.sidebar.file_uploader(
    "Carregar PDFs", type="pdf", accept_multiple_files=True
)

jornada_h = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

if uploaded_files:
    for f in uploaded_files:
        if f.name not in st.session_state.arquivos_lidos:
            with st.spinner(f"Lendo {f.name}..."):
                res = extrair_dados_pdf_seguro(f)
                if not res.empty:
                    st.session_state.db_pd = (
                        pd.concat([st.session_state.db_pd, res], ignore_index=True)
                        .drop_duplicates()
                    )
                    st.session_state.arquivos_lidos.append(f.name)
                    salvar_db(st.session_state.db_pd)
                    salvar_arquivos(st.session_state.arquivos_lidos)
                    st.rerun()

# --- NOVO: EXCLUIR PDF CARREGADO ---
if st.session_state.arquivos_lidos:
    with st.sidebar.expander("🗑️ Excluir PDF Carregado"):
        arq_para_excluir = st.selectbox("Selecionar Arquivo", st.session_state.arquivos_lidos)
        if st.button("Confirmar Exclusão Arquivo"):
            st.session_state.arquivos_lidos.remove(arq_para_excluir)
            if not st.session_state.db_pd.empty:
                st.session_state.db_pd = st.session_state.db_pd[st.session_state.db_pd["Arquivo"] != arq_para_excluir]
            salvar_db(st.session_state.db_pd)
            salvar_arquivos(st.session_state.arquivos_lidos)
            st.success("Arquivo removido!")
            st.rerun()

# =========================================================
# FILTROS
# =========================================================
st.sidebar.markdown("---")
st.sidebar.header("🔍 Filtros")

if not st.session_state.db_pd.empty:
    db = st.session_state.db_pd
    anos = sorted(db["Ano"].unique())
    meses = sorted(db["Mês"].unique(), key=lambda x: x.split(" - ")[0])

    f_ano = st.sidebar.multiselect("Ano", anos, default=anos)
    f_mes = st.sidebar.multiselect("Mês", meses, default=meses)
    f_colab = st.sidebar.multiselect("Colaborador", EQUIPE, default=EQUIPE)

    df_filtrado = db[
        (db["Ano"].isin(f_ano)) &
        (db["Mês"].isin(f_mes)) &
        (db["Colaborador"].isin(f_colab))
    ]
else:
    df_filtrado = pd.DataFrame()

# =========================================================
# LANÇAMENTO DE FOLGAS
# =========================================================
with st.sidebar.expander("🏖️ Lançar Ausência"):
    c_f = st.selectbox("Colaborador ", EQUIPE)
    tipo_f = st.selectbox("Tipo", TIPOS_FOLGA)
    d_i = st.date_input("Início")
    d_f = st.date_input("Fim")

    if st.button("Salvar Ausência"):
        datas = []
        curr = d_i
        while curr <= d_f:
            datas.append({
                "Colaborador": c_f,
                "Data": curr,
                "Tipo": tipo_f
            })
            curr += timedelta(days=1)

        st.session_state.folgas = (
            pd.concat([st.session_state.folgas, pd.DataFrame(datas)])
            .drop_duplicates(subset=["Colaborador", "Data"])
        )

        salvar_folgas(st.session_state.folgas)
        st.success("Registro salvo!")

# --- NOVO: EXCLUIR AUSÊNCIA ---
if not st.session_state.folgas.empty:
    with st.sidebar.expander("🗑️ Excluir Ausência"):
        folgas_view = st.session_state.folgas.copy()
        folgas_view["label"] = folgas_view["Colaborador"] + " - " + folgas_view["Data"].astype(str)
        selecionado = st.selectbox("Selecionar Registro", folgas_view["label"].unique())
        if st.button("Confirmar Exclusão Ausência"):
            col_sel, data_sel = selecionado.split(" - ")
            st.session_state.folgas = st.session_state.folgas[
                ~((st.session_state.folgas["Colaborador"] == col_sel) & 
                  (st.session_state.folgas["Data"].astype(str) == data_sel))
            ]
            salvar_folgas(st.session_state.folgas)
            st.success("Ausência removida!")
            st.rerun()

# =========================================================
# RESET
# =========================================================
if st.sidebar.button("⚠️ Resetar Sistema Completo"):
    for f in [DB_FILE, FOLGAS_FILE, ARQS_FILE]:
        if os.path.exists(f):
            os.remove(f)
    st.session_state.clear()
    st.rerun()

# =========================================================
# DASHBOARD
# =========================================================
if not df_filtrado.empty:
    st.subheader("📈 Indicadores Consolidados")

    dias_u = sorted(df_filtrado["Data"].unique())
    n_dias = len(dias_u)
    total_prog = df_filtrado["HH"].sum()

    tabela = []
    total_disp = 0

    for p in f_colab:
        hh_p = df_filtrado[df_filtrado["Colaborador"] == p]["HH"].sum()
        dias_aus = st.session_state.folgas[
            (st.session_state.folgas["Colaborador"] == p) &
            (st.session_state.folgas["Data"].isin(dias_u))
        ].shape[0]

        hh_disp = (n_dias - dias_aus) * jornada_h
        total_disp += hh_disp
        carga = (hh_p / hh_disp * 100) if hh_disp > 0 else 0

        tabela.append({
            "Colaborador": p,
            "Dias Úteis": n_dias - dias_aus,
            "HH Disponível": round(hh_disp, 1),
            "HH Programado": round(hh_p, 1),
            "Saldo": round(hh_disp - hh_p, 1),
            "% Carga": f"{carga:.1f}%"
        })

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dias Computados", n_dias)
    c2.metric("HH Disponível", f"{total_disp:.1f}")
    c3.metric("HH Programado", f"{total_prog:.1f}")
    c4.metric("% Carga Total", f"{(total_prog / total_disp * 100) if total_disp > 0 else 0:.1f}%")

    st.table(pd.DataFrame(tabela))

    t1, t2, t3 = st.tabs(["📅 Detalhe Diário", "🏖️ Ausências", "📊 Resumo de Ausências"])

    with t1:
        for d in sorted(dias_u, reverse=True):
            with st.expander(f"Programação {d.strftime('%d/%m/%Y')}"):
                # Filtrar dados do dia
                df_dia = df_filtrado[df_filtrado["Data"] == d]
                
                # Criar base com todos da equipe filtrada para garantir que apareçam mesmo sem HH
                resumo_dia = []
                for p in f_colab:
                    hh_prog = df_dia[df_dia["Colaborador"] == p]["HH"].sum()
                    
                    # Verificar se está de folga no dia
                    is_folga = not st.session_state.folgas[
                        (st.session_state.folgas["Colaborador"] == p) & 
                        (st.session_state.folgas["Data"] == d)
                    ].empty
                    
                    hh_plan = 0.0 if is_folga else jornada_h
                    hh_n_prog = max(0.0, hh_plan - hh_prog)
                    perc = (hh_prog / hh_plan * 100) if hh_plan > 0 else 0.0
                    
                    resumo_dia.append({
                        "Colaborador": p,
                        "HH Planejado": hh_plan,
                        "HH Programado": round(hh_prog, 2),
                        "HH Não Programado": round(hh_n_prog, 2),
                        "% Programado": f"{perc:.1f}%"
                    })
                
                st.dataframe(pd.DataFrame(resumo_dia), use_container_width=True)

    with t2:
        st.dataframe(st.session_state.folgas, use_container_width=True)

    with t3:
        if not st.session_state.folgas.empty:
            resumo = (
                st.session_state.folgas
                .groupby(["Colaborador", "Tipo"])
                .size()
                .reset_index(name="Dias")
            )
            resumo["Horas"] = resumo["Dias"] * jornada_h

            tabela_resumo = resumo.pivot_table(
                index="Colaborador",
                columns="Tipo",
                values="Horas",
                aggfunc="sum",
                fill_value=0
            ).reset_index()

            st.dataframe(tabela_resumo, use_container_width=True)
        else:
            st.info("Nenhuma ausência registrada.")

else:
    st.info("Carregue PDFs para iniciar o painel.")
