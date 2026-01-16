import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import unicodedata
from datetime import datetime, timedelta

# 1. CONFIGURAÇÃO BÁSICA
st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# Inicialização da memória para evitar perda de dados ao navegar
if 'db_pd' not in st.session_state: st.session_state['db_pd'] = pd.DataFrame()
if 'arquivos_lidos' not in st.session_state: st.session_state['arquivos_lidos'] = []
if 'folgas' not in st.session_state: st.session_state['folgas'] = pd.DataFrame(columns=['Colaborador', 'Data'])

st.title("📊 Gestão de Planejamento - Automação")

EQUIPE = ["ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"]

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(txt).upper()) if unicodedata.category(c) != 'Mn').strip()

def identificar_colab(texto):
    t = normalizar(texto)
    if not t: return None
    if "GERALDO" in t: return "JOSÉ GERALDO"
    if "EDILON" in t: return "EDILON"
    for nome in EQUIPE:
        if normalizar(nome) in t: return nome
    return None

def extrair_dados_pdf_estavel(file_obj):
    """
    Motor de extração focado no 19.01.pdf e SEM04. 
    Lê o texto bruto para evitar erros de rede com tabelas pesadas.
    """
    try:
        file_bytes = file_obj.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        
        # Pega a data de referência no início do texto
        texto_inicio = doc[0].get_text()
        dt_match = re.search(r'(\d{2}/\d{2}/\d{2})', texto_inicio)
        data_ref = datetime.strptime(dt_match.group(1), '%d/%m/%y').date() if dt_match else datetime.now().date()
        
        registros = []
        for page in doc:
            # Extrai blocos de texto para manter a relação entre nome e duração
            blocos = page.get_text("blocks")
            for b in blocos:
                texto_bloco = b[4].replace('\n', ' ')
                
                # Só processa se for da Automação
                if "AUTOMAÇÃO" in texto_bloco.upper() or "ΑΥΤΌΠΙΣΕΔΟ" in texto_bloco:
                    # Busca duração (HH)
                    minutos = re.findall(r'(\d+)\s*min', texto_bloco)
                    hh = int(minutos[0])/60 if minutos else 0
                    
                    # Identifica colaborador
                    for nome in EQUIPE:
                        if normalizar(nome) in normalizar(texto_bloco):
                            registros.append({
                                'Colaborador': nome, 'HH': hh, 'Data': data_ref,
                                'Mês': data_ref.strftime('%m - %B')
                            })
        doc.close()
        return pd.DataFrame(registros).drop_duplicates()
    except Exception as e:
        st.error(f"Erro ao ler {file_obj.name}: {e}")
        return pd.DataFrame()

# --- BARRA LATERAL ---
st.sidebar.header("📁 Banco de Dados")
files = st.sidebar.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)
jornada_h = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

if files:
    for f in files:
        if f.name not in st.session_state.arquivos_lidos:
            res = extrair_dados_pdf_estavel(f)
            if not res.empty:
                st.session_state.db_pd = pd.concat([st.session_state.db_pd, res], ignore_index=True)
                st.session_state.arquivos_lidos.append(f.name)
    st.rerun()

# Lançamento de Folgas
with st.sidebar.expander("🏖️ Registrar Folga"):
    c_f = st.selectbox("Colaborador", EQUIPE)
    d_i = st.date_input("Início")
    d_f = st.date_input("Fim")
    if st.button("Salvar Período"):
        curr = d_i
        novas = []
        while curr <= d_f:
            novas.append({'Colaborador': c_f, 'Data': curr})
            curr += timedelta(days=1)
        st.session_state.folgas = pd.concat([st.session_state.folgas, pd.DataFrame(novas)]).drop_duplicates()
        st.success("Folga registrada!")

if st.sidebar.button("🗑️ Resetar Tudo"):
    st.session_state.db_pd = pd.DataFrame()
    st.session_state.arquivos_lidos = []
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])
    st.rerun()

# --- DASHBOARDS E INDICADORES ---
if not st.session_state.db_pd.empty:
    df = st.session_state.db_pd
    folgas = st.session_state.folgas
    dias_u = sorted(df['Data'].unique())
    n_dias = len(dias_u)
    
    st.subheader("📈 Indicadores Consolidados")
    
    # Cálculos solicitados
    total_prog = df['HH'].sum()
    resumo_geral = []
    total_disp_global = 0
    
    for p in EQUIPE:
        hh_p = df[df['Colaborador'] == p]['HH'].sum()
        dias_f = folgas[(folgas['Colaborador'] == p) & (folgas['Data'].isin(dias_u))].shape[0]
        hh_d = (n_dias - dias_f) * jornada_h
        total_disp_global += hh_d
        carga = (hh_p / hh_d * 100) if hh_d > 0 else 0
        
        resumo_geral.append({
            "Colaborador": p, "Dias Computados": n_dias - dias_f,
            "HH Disponível": round(hh_d, 1), "HH Programado": round(hh_p, 1),
            "Saldo HH": round(hh_d - hh_p, 1), "% de Carga": f"{carga:.1f}%"
        })

    # KPIs de Topo
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nº de Dias Computados", n_dias)
    c2.metric("Total HH Disponível", f"{total_disp_global:.1f}h")
    c3.metric("Total HH Programado", f"{total_prog:.1f}h")
    cg = (total_prog / total_disp_global * 100) if total_disp_global > 0 else 0
    c4.metric("% Carga Global", f"{cg:.1f}%")
    
    st.table(pd.DataFrame(resumo_geral))

    # Detalhamento
    t1, t2 = st.tabs(["📅 Detalhe Diário", "🏖️ Folgas Concedidas"])
    with t1:
        for d in sorted(dias_u, reverse=True):
            with st.expander(f"Data: {d.strftime('%d/%m/%Y')}"):
                st.dataframe(df[df['Data'] == d].groupby('Colaborador')['HH'].sum().reset_index(), use_container_width=True)
    with t2:
        st.dataframe(folgas, use_container_width=True)
else:
    st.info("Aguardando upload de arquivos para gerar os indicadores.")
