import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import unicodedata
import io
from datetime import datetime, timedelta

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# 2. INICIALIZAÇÃO DA MEMÓRIA (PERSISTÊNCIA)
if 'db_pd' not in st.session_state: st.session_state['db_pd'] = pd.DataFrame()
if 'arquivos_lidos' not in st.session_state: st.session_state['arquivos_lidos'] = []
if 'folgas' not in st.session_state: st.session_state['folgas'] = pd.DataFrame(columns=['Colaborador', 'Data'])

st.title("📊 Gestão de Planejamento - Automação")

EQUIPE = ["ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"]

# 3. FUNÇÕES AUXILIARES
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

def extrair_dados_pdf_definitivo(file_obj):
    """
    Extração robusta para lidar com quebras de linha complexas como no 19.01.pdf.
    """
    try:
        file_bytes = file_obj.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        dados_lista = []
        
        # Pega a data da primeira página
        texto_pag1 = doc[0].get_text()
        dt_match = re.search(r'(\d{2}/\d{2}/\d{2})', texto_pag1)
        data_ref = datetime.strptime(dt_match.group(1), '%d/%m/%y').date() if dt_match else datetime.now().date()

        for page in doc:
            texto = page.get_text("text")
            # [span_1](start_span)Limpa caracteres que confundem a leitura[span_1](end_span)
            texto_limpo = texto.replace('\xa0', ' ').replace('\r', '')
            
            # [span_2](start_span)Divide o texto em blocos baseados na supervisão 'Automação'[span_2](end_span)
            blocos = re.split(r'(?i)automação', texto_limpo)
            
            for bloco in blocos[1:]: 
                # [span_3](start_span)Busca HH (ex: 480 mins)[span_3](end_span)
                minutos = re.findall(r'(\d+)\s*mins?', bloco)
                hh_val = int(minutos[0])/60 if minutos else 0
                
                # [span_4](start_span)Identifica colaboradores da equipe no bloco de texto[span_4](end_span)
                for colab in EQUIPE:
                    if normalizar(colab) in normalizar(bloco):
                        dados_lista.append({
                            'Colaborador': colab, 
                            'HH': hh_val, 
                            'Data': data_ref,
                            'Mês': data_ref.strftime('%m - %B'),
                            'Ano': data_ref.year
                        })
        doc.close()
        return pd.DataFrame(dados_lista).drop_duplicates()
    except Exception as e:
        st.error(f"Erro no arquivo {file_obj.name}: {e}")
        return pd.DataFrame()

# 4. BARRA LATERAL (ENTRADA)
st.sidebar.header("📁 Banco de Dados")
uploaded_files = st.sidebar.file_uploader("Adicionar novos PDFs", type="pdf", accept_multiple_files=True)
jornada_h = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

# Processamento
if uploaded_files:
    for f in uploaded_files:
        if f.name not in st.session_state.arquivos_lidos:
            res = extrair_dados_pdf_definitivo(f)
            if not res.empty:
                st.session_state.db_pd = pd.concat([st.session_state.db_pd, res], ignore_index=True)
                st.session_state.arquivos_lidos.append(f.name)
    st.rerun()

# 5. FILTROS E GESTÃO DE FOLGAS
if not st.session_state.db_pd.empty:
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filtros")
    db = st.session_state.db_pd
    f_mes = st.sidebar.multiselect("Filtrar Mês", sorted(db['Mês'].unique()), default=db['Mês'].unique())
    f_col = st.sidebar.multiselect("Filtrar Equipe", EQUIPE, default=EQUIPE)
    df_f = db[(db['Mês'].isin(f_mes)) & (db['Colaborador'].isin(f_col))]
else:
    df_f = pd.DataFrame()

with st.sidebar.expander("🏖️ Registrar Folga"):
    c_f = st.selectbox("Colaborador", EQUIPE)
    d_i = st.date_input("Início")
    d_f = st.date_input("Fim")
    if st.button("Salvar Folga"):
        curr = d_i
        novas = []
        while curr <= d_f:
            novas.append({'Colaborador': c_f, 'Data': curr})
            curr += timedelta(days=1)
        st.session_state.folgas = pd.concat([st.session_state.folgas, pd.DataFrame(novas)]).drop_duplicates()
        st.success("Folga registrada!")

if st.sidebar.button("🗑️ RESET TOTAL"):
    st.session_state.db_pd = pd.DataFrame()
    st.session_state.arquivos_lidos = []
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])
    st.rerun()

# 6. DASHBOARD (INDICADORES SOLICITADOS)
if not df_f.empty:
    st.subheader("📈 Indicadores Consolidados")
    dias_u = sorted(df_f['Data'].unique())
    n_dias = len(dias_u)
    
    total_prog = df_f['HH'].sum()
    total_disp = 0
    resumo_kpi = []
    
    for p in f_col:
        hh_p = df_f[df_f['Colaborador'] == p]['HH'].sum()
        # Desconta folgas do HH Disponível
        dias_f = st.session_state.folgas[(st.session_state.folgas['Colaborador'] == p) & (st.session_state.folgas['Data'].isin(dias_u))].shape[0]
        hh_d = (n_dias - dias_f) * jornada_h
        total_disp += hh_d
        carga = (hh_p / hh_d * 100) if hh_d > 0 else 0
        
        resumo_kpi.append({
            "Colaborador": p, 
            "Dias Computados": n_dias - dias_f,
            "HH Disponível": round(hh_d, 1), 
            "HH Programado": round(hh_p, 1),
            "Saldo HH": round(hh_d - hh_p, 1), 
            "% de Carga": f"{carga:.1f}%"
        })

    # KPIs de Topo
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nº de Dias Computados", n_dias)
    c2.metric("Total HH Disponível", f"{total_disp:.1f}h")
    c3.metric("Total HH Programado", f"{total_prog:.1f}h")
    carga_g = (total_prog / total_disp * 100) if total_disp > 0 else 0
    c4.metric("% Carga Global", f"{carga_g:.1f}%")

    st.table(pd.DataFrame(resumo_kpi))

    # Detalhamento Diário
    t1, t2 = st.tabs(["📅 Detalhe Diário", "🏖️ Folgas Concedidas"])
    with t1:
        for d in sorted(dias_u, reverse=True):
            with st.expander(f"Data: {d.strftime('%d/%m/%Y')}"):
                st.dataframe(df_f[df_f['Data'] == d].groupby('Colaborador')['HH'].sum().reset_index(), use_container_width=True)
    with t2:
        st.dataframe(st.session_state.folgas, use_container_width=True)
else:
    st.info("Aguardando upload de PDFs para processamento.")
