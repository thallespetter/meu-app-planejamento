import streamlit as st
import pandas as pd
import pdfplumber
import re
import unicodedata
import os
from datetime import datetime, timedelta

# Configuração da página
st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# --- LISTA OFICIAL DA SUPERVISÃO ---
EQUIPE = ["ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"]

def normalizar(txt):
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(txt).upper()) if unicodedata.category(c) != 'Mn').strip()

def identificar_colab(texto):
    t = normalizar(texto)
    # Mapeamento para garantir que José Geraldo e Edilon sejam pegos mesmo com nomes parciais
    if "GERALDO" in t: return "JOSÉ GERALDO"
    if "EDILON" in t: return "EDILON"
    for nome in EQUIPE:
        if normalizar(nome) in t: return nome
    return None

# --- PROCESSAMENTO DO PDF ---
def extrair_dados_pdf(file):
    with pdfplumber.open(file) as pdf:
        dados = []
        for page in pdf.pages:
            table = page.extract_table()
            if table: dados.extend(table)
        
        df_raw = pd.DataFrame(dados)
        # Localiza o cabeçalho dinamicamente
        h_idx = 0
        for i, row in df_raw.iterrows():
            if "supervisão" in " ".join(map(str, row)).lower():
                h_idx = i
                break
        
        df = df_raw.drop(range(h_idx + 1)).reset_index(drop=True)
        headers = [str(c).replace('\n', ' ').strip() for c in df_raw.iloc[h_idx]]
        
        # Deduplicação manual de colunas
        new_cols = []
        for i, v in enumerate(headers):
            new_cols.append(f"{v}_{i}" if headers.count(v) > 1 else v)
        df.columns = new_cols
        
        # Filtro de Automação
        col_sup = [c for c in df.columns if 'Supervisão' in c][0]
        df = df[df[col_sup].str.contains('Automação', case=False, na=False)].copy()
        
        # Identifica colunas de interesse
        col_rec = [c for c in df.columns if 'recursos' in c.lower() or 'Nomes' in c][0]
        col_dur = [c for c in df.columns if 'Duração' in c][0]
        col_dat = [c for c in df.columns if any(x in c for x in ['Início', 'Data'])][0]
        
        # Extração de Data
        dt_str = re.search(r'\d{2}/\d{2}/\d{2}', str(df[col_dat].iloc[0])).group()
        data_ref = datetime.strptime(dt_str, '%d/%m/%y').date()
        
        # Processamento de HH e Colaboradores
        df['HH'] = df[col_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
        df['Lista_Rec'] = df[col_rec].str.split('\n') # PDF 19.01 usa quebra de linha
        df = df.explode('Lista_Rec')
        df['Colaborador'] = df['Lista_Rec'].apply(identificar_colab)
        
        return df.dropna(subset=['Colaborador'])[['Colaborador', 'HH', 'Data']].assign(Mês=data_ref.strftime('%m - %B'), Data=data_ref)

# --- PERSISTÊNCIA ---
if 'historico' not in st.session_state:
    st.session_state.historico = pd.DataFrame()
if 'folgas' not in st.session_state:
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])

st.sidebar.header("⚙️ Configurações")
files = st.sidebar.file_uploader("Carregar Programação (PDF)", accept_multiple_files=True)
jornada = st.sidebar.number_input("Jornada Diária HH", value=8.0)

if files:
    for f in files:
        # Evita duplicar o mesmo arquivo na memória
        if f.name not in st.session_state.get('arquivos_lidos', []):
            novo_df = extrair_dados_pdf(f)
            st.session_state.historico = pd.concat([st.session_state.historico, novo_df]).drop_duplicates()
            if 'arquivos_lidos' not in st.session_state: st.session_state.arquivos_lidos = []
            st.session_state.arquivos_lidos.append(f.name)

# --- LÓGICA DE FOLGAS ---
with st.sidebar.expander("🏖️ Lançar Folgas"):
    c_folga = st.selectbox("Colaborador", EQUIPE)
    d_folga = st.date_input("Data da Folga")
    if st.button("Registrar"):
        nova_folga = pd.DataFrame([{'Colaborador': c_folga, 'Data': d_folga}])
        st.session_state.folgas = pd.concat([st.session_state.folgas, nova_folga]).drop_duplicates()

# --- EXIBIÇÃO ---
if not st.session_state.historico.empty:
    df = st.session_state.historico
    dias_totais = df['Data'].nunique()
    
    st.subheader("📊 Relatório de Carga Anual/Período")
    
    # Cálculo de disponibilidade real (Dias totais - Folgas)
    res = []
    for nome in EQUIPE:
        hh_prog = df[df['Colaborador'] == nome]['HH'].sum()
        folgas_colab = len(st.session_state.folgas[(st.session_state.folgas['Colaborador'] == nome)])
        dias_uteis = dias_totais - folgas_colab
        hh_disp = dias_uteis * jornada
        
        res.append({
            "Colaborador": nome,
            "Dias Computados": dias_uteis,
            "HH Disponível": hh_disp,
            "HH Programado": hh_prog,
            "HH Sem Apropriação": hh_disp - hh_prog,
            "% Carga": round((hh_prog / hh_disp * 100), 1) if hh_disp > 0 else 0
        })
    
    st.table(pd.DataFrame(res))

    st.subheader("📅 Visão por Dia")
    col1, col2 = st.columns(2)
    f_mes = col1.multiselect("Filtrar Mês", df['Mês'].unique(), default=df['Mês'].unique())
    f_col = col2.multiselect("Filtrar Colaborador", EQUIPE, default=EQUIPE)
    
    view_dia = df[(df['Mês'].isin(f_mes)) & (df['Colaborador'].isin(f_col))]
    st.dataframe(view_dia, use_container_width=True)
