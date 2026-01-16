import streamlit as st
import pandas as pd
import pdfplumber
import re
import unicodedata
from datetime import datetime

st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# --- MEMÓRIA DO APLICATIVO ---
# Usamos session_state para garantir que os dados não sumam ao navegar
if 'historico' not in st.session_state:
    st.session_state.historico = pd.DataFrame()
if 'arquivos_lidos' not in st.session_state:
    st.session_state.arquivos_lidos = []
if 'folgas' not in st.session_state:
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])

st.title("📊 Gestão de Planejamento - Automação")

EQUIPE = ["ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"]

def normalizar(txt):
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(txt).upper()) if unicodedata.category(c) != 'Mn').strip()

def identificar_colab(texto):
    t = normalizar(texto)
    if "GERALDO" in t: return "JOSÉ GERALDO"
    if "EDILON" in t: return "EDILON"
    for nome in EQUIPE:
        if normalizar(nome) in t: return nome
    return None

def extrair_dados_pdf(file):
    with pdfplumber.open(file) as pdf:
        dados = []
        for page in pdf.pages:
            table = page.extract_table()
            if table: dados.extend(table)
        
        if not dados: return pd.DataFrame()
        
        df_raw = pd.DataFrame(dados)
        
        # 1. Localizar linha do cabeçalho
        h_idx = 0
        for i, row in df_raw.iterrows():
            row_str = " ".join(map(str, row)).lower()
            if "supervisão" in row_str or "recursos" in row_str:
                h_idx = i
                break
        
        # 2. Definir DataFrame e colunas
        headers = [str(c).lower() for c in df_raw.iloc[h_idx]]
        df = df_raw.drop(range(h_idx + 1)).reset_index(drop=True)
        
        # 3. Identificar índices das colunas (MUITO MAIS SEGURO)
        try:
            idx_sup = [i for i, h in enumerate(headers) if 'superv' in h][0]
            idx_rec = [i for i, h in enumerate(headers) if 'recursos' in h or 'nomes' in h][0]
            idx_dur = [i for i, h in enumerate(headers) if 'dura' in h][0]
            idx_dat = [i for i, h in enumerate(headers) if 'início' in h or 'data' in h or 'começo' in h][0]
        except IndexError:
            st.error(f"Não foi possível encontrar as colunas necessárias no arquivo {file.name}")
            return pd.DataFrame()

        # 4. Filtrar apenas Automação
        df = df[df[idx_sup].str.contains('Automação', case=False, na=False)].copy()
        
        if df.empty: return pd.DataFrame()

        # 5. Extrair Data de referência do arquivo
        dt_match = re.search(r'\d{2}/\d{2}/\d{2}', str(df[idx_dat].iloc[0]))
        data_ref = datetime.strptime(dt_match.group(), '%d/%m/%y').date() if dt_match else datetime.now().date()
        
        # 6. Criar colunas padronizadas
        df['HH_Final'] = df[idx_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
        df['Colaborador'] = df[idx_rec].str.split('\n').apply(lambda x: [identificar_colab(n) for n in x if identificar_colab(n)])
        
        # Explodir e limpar
        df = df.explode('Colaborador').dropna(subset=['Colaborador'])
        
        # Retornar apenas o necessário com nomes fixos
        return pd.DataFrame({
            'Colaborador': df['Colaborador'],
            'HH': df['HH_Final'],
            'Data': data_ref,
            'Mês': data_ref.strftime('%m - %B')
        })

# --- BARRA LATERAL ---
st.sidebar.header("📁 Upload e Filtros")
uploaded_files = st.sidebar.file_uploader("Arraste os PDFs aqui", type="pdf", accept_multiple_files=True)
jornada_h = st.sidebar.number_input("Jornada Diária", value=8.0)

if st.sidebar.button("🗑️ Limpar tudo"):
    st.session_state.historico = pd.DataFrame()
    st.session_state.arquivos_lidos = []
    st.rerun()

# --- PROCESSAMENTO ---
if uploaded_files:
    for f in uploaded_files:
        if f.name not in st.session_state.arquivos_lidos:
            res = extrair_dados_pdf(f)
            if not res.empty:
                st.session_state.historico = pd.concat([st.session_state.historico, res], ignore_index=True)
                st.session_state.arquivos_lidos.append(f.name)
    st.success("Arquivos processados com sucesso!")

# --- VISUALIZAÇÃO ---
if not st.session_state.historico.empty:
    hist = st.session_state.historico
    
    t1, t2 = st.tabs(["🌎 Resumo Geral", "📅 Detalhe por Dia"])
    
    with t1:
        dias_total = hist['Data'].nunique()
        st.metric("Total de Dias Carregados", dias_total)
        
        resumo = hist.groupby('Colaborador')['HH'].sum().reset_index()
        resumo['HH Disponível'] = dias_total * jornada_h
        resumo['Saldo'] = resumo['HH Disponível'] - resumo['HH']
        resumo['% Carga'] = (resumo['HH'] / resumo['HH Disponível'] * 100).round(1)
        
        st.dataframe(resumo, use_container_width=True)

    with t2:
        meses = sorted(hist['Mês'].unique())
        sel_mes = st.selectbox("Selecione o Mês", meses)
        df_mes = hist[hist['Mês'] == sel_mes]
        
        for d in sorted(df_mes['Data'].unique(), reverse=True):
            with st.expander(f"Data: {d.strftime('%d/%m/%Y')}"):
                st.table(df_mes[df_mes['Data'] == d][['Colaborador', 'HH']])
