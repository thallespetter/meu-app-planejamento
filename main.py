import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime

st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# --- MEMÓRIA DO APLICATIVO ---
if 'db_pd' not in st.session_state:
    st.session_state['db_pd'] = pd.DataFrame()
if 'arquivos_processados' not in st.session_state:
    st.session_state['arquivos_processados'] = []

st.title("📊 Gestão de Planejamento - Automação")

# --- LISTA OFICIAL DE COLABORADORES DA AUTOMAÇÃO ---
EQUIPE_AUTOMACAO = [
    "ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", 
    "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"
]

def normalizar_nome(nome):
    nome = str(nome).upper().strip()
    for ref in EQUIPE_AUTOMACAO:
        if ref in nome: return ref
    return None # Se não for da equipe, retorna None para filtrarmos depois

def processar_pdf(file):
    with pdfplumber.open(file) as pdf:
        all_rows = []
        for page in pdf.pages:
            table = page.extract_table()
            if table: all_rows.extend(table)
        if not all_rows: return pd.DataFrame()
        
        df_raw = pd.DataFrame(all_rows)
        header_idx = None
        for i, row in df_raw.iterrows():
            row_str = " ".join([str(x) for x in row.values if x]).lower()
            if "supervisão" in row_str or "recursos" in row_str:
                header_idx = i
                break
        if header_idx is None: return pd.DataFrame()
        
        df = df_raw.drop(range(header_idx + 1)).reset_index(drop=True)
        df.columns = [str(c).replace('\n', ' ').strip() for c in df_raw.iloc[header_idx]]
        return df

# --- SIDEBAR ---
st.sidebar.header("📁 Upload de Dados")
uploaded_files = st.sidebar.file_uploader("Adicionar PDFs", type="pdf", accept_multiple_files=True)
jornada_disp = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

if st.sidebar.button("Limpar Todos os Dados"):
    st.session_state['db_pd'] = pd.DataFrame()
    st.session_state['arquivos_processados'] = []
    st.rerun()

# --- PROCESSAMENTO ---
if uploaded_files:
    novos_dados = []
    for file in uploaded_files:
        if file.name not in st.session_state['arquivos_processados']:
            df = processar_pdf(file)
            if not df.empty:
                col_sup = [c for c in df.columns if 'Supervisão' in c][0]
                col_rec = [c for c in df.columns if 'recursos' in c.lower()][0]
                col_dur = [c for c in df.columns if 'Duração' in c][0]
                col_data = [c for c in df.columns if 'Início' in c or 'Data' in c][0]

                df_aut = df[df[col_sup].str.contains('Automação', case=False, na=False)].copy()
                
                # Extração de Data
                sample_date = str(df_aut[col_data].iloc[0]) if not df_aut.empty else ""
                data_obj = datetime.now()
                if "/" in sample_date:
                    try:
                        data_str = re.search(r'\d{2}/\d{2}/\d{2}', sample_date).group()
                        data_obj = datetime.strptime(data_str, '%d/%m/%y')
                    except: pass

                df_aut['HH_Prog'] = df_aut[col_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
                df_aut['Executantes'] = df_aut[col_rec].str.split(';')
                df_exploded = df_aut.explode('Executantes')
                
                # FILTRO CRUCIAL: Apenas nomes da EQUIPE_AUTOMACAO
                df_exploded['Colaborador'] = df_exploded['Executantes'].apply(normalizar_nome)
                df_exploded = df_exploded.dropna(subset=['Colaborador'])
                
                df_exploded['Data'] = data_obj.date()
                df_exploded['Mês'] = data_obj.strftime('%m - %B')
                df_exploded['Ano'] = data_obj.year
                df_exploded['Arquivo'] = file.name
                
                novos_dados.append(df_exploded)
                st.session_state['arquivos_processados'].append(file.name)
    
    if novos_dados:
        st.session_state['db_pd'] = pd.concat([st.session_state['db_pd'], pd.concat(novos_dados)], ignore_index=True)

# --- EXIBIÇÃO ---
if not st.session_state['db_pd'].empty:
    df_m = st.session_state['db_pd']
    
    # Filtros Globais
    st.write("### 🔍 Filtros de Visualização")
    c1, c2, c3 = st.columns(3)
    mes_sel = c1.multiselect("Mês", sorted(df_m['Mês'].unique()), default=sorted(df_m['Mês'].unique()))
    data_sel = c2.multiselect("Data Específica", sorted(df_m['Data'].unique()), default=sorted(df_m['Data'].unique()))
    colab_sel = c3.multiselect("Colaborador", EQUIPE_AUTOMACAO, default=EQUIPE_AUTOMACAO)
    
    df_f = df_m[(df_m['Mês'].isin(mes_sel)) & (df_m['Data'].isin(data_sel)) & (df_m['Colaborador'].isin(colab_sel))]

    t1, t2 = st.tabs(["🌎 Relatório Geral", "📅 Visão Diária"])

    with t1:
        # Métricas de Cabeçalho
        total_dias = df_f['Data'].nunique()
        hh_disponivel_total = total_dias * len(colab_sel) * jornada_disp
        hh_prog_total = df_f['HH_Prog'].sum()
        hh_sem_aprop = hh_disponivel_total - hh_prog_total

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Dias Computados", total_dias)
        m2.metric("HH Disp. no Período", f"{hh_disponivel_total:.1f}h")
        m3.metric("HH Prog. no Período", f"{hh_prog_total:.1f}h")
        m4.metric("HH Sem Apropriação", f"{hh_sem_aprop:.1f}h")

        # Tabela Geral
        res_g = df_f.groupby('Colaborador').agg({'Data': 'nunique', 'HH_Prog': 'sum'}).reset_index()
        res_g.columns = ['Colaborador', 'N° de dias computadados', 'HH Programado']
        res_g['HH Disponível'] = res_g['N° de dias computadados'] * jornada_disp
        res_g['% Carga'] = (res_g['HH Programado'] / res_g['HH Disponível'] * 100).round(1)
        
        # Ordem solicitada
        res_g = res_g[['Colaborador', 'N° de dias computadados', 'HH Disponível', 'HH Programado', '% Carga']]
        st.dataframe(res_g.style.format({'% Carga': '{:.1f}%'}), use_container_width=True)

    with t2:
        for d in sorted(df_f['Data'].unique(), reverse=True):
            st.write(f"#### 📅 Data: {d.strftime('%d/%m/%Y')}")
            df_d = df_f[df_f['Data'] == d]
            res_d = df_d.groupby('Colaborador')['HH_Prog'].sum().reset_index()
            res_d['HH Disponível'] = jornada_disp
            res_d['% Carga'] = (res_d['HH_Prog'] / jornada_disp * 100).round(1)
            
            st.table(res_d[['Colaborador', 'HH Disponível', 'HH_Prog', '% Carga']])
            st.write(f"**Total do Dia:** Programado: {res_d['HH_Prog'].sum():.1f}h | Disponível: {len(res_d)*jornada_disp:.1f}h")
            st.write("---")
else:
    st.info("Aguardando upload de arquivos para iniciar.")
