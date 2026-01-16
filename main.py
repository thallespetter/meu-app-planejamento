import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# --- MEMÓRIA DO APLICATIVO ---
if 'db_pd' not in st.session_state:
    st.session_state['db_pd'] = pd.DataFrame()
if 'arquivos_processados' not in st.session_state:
    st.session_state['arquivos_processados'] = []
if 'folgas' not in st.session_state:
    st.session_state['folgas'] = []

st.title("📊 Gestão de Planejamento - Automação")

# --- LISTA OFICIAL ---
EQUIPE_AUTOMACAO = [
    "ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", 
    "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"
]

def normalizar_nome(nome):
    if not nome: return None
    # Remove acentos e padroniza para maiúsculo
    nome_limpo = str(nome).upper().strip()
    import unicodedata
    nome_limpo = "".join(c for c in unicodedata.normalize('NFD', nome_limpo) if unicodedata.category(c) != 'Mn')
    
    for ref in EQUIPE_AUTOMACAO:
        ref_limpa = "".join(c for c in unicodedata.normalize('NFD', ref) if unicodedata.category(c) != 'Mn')
        if ref_limpa in nome_limpo: 
            return ref
    return None

def deduplicar_colunas(colunas):
    nova_lista = []
    contagem = {}
    for col in colunas:
        if col in contagem:
            contagem[col] += 1
            nova_lista.append(f"{col}_{contagem[col]}")
        else:
            contagem[col] = 0
            nova_lista.append(col)
    return nova_lista

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
        headers = [str(c).replace('\n', ' ').strip() for c in df_raw.iloc[header_idx]]
        df.columns = deduplicar_colunas(headers)
        return df

# --- SIDEBAR ---
st.sidebar.header("📁 Upload de Dados")
uploaded_files = st.sidebar.file_uploader("Adicionar PDFs", type="pdf", accept_multiple_files=True)
jornada_disp = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

st.sidebar.markdown("---")
st.sidebar.header("🏖️ Registrar Folga/Ausência")
colab_folga = st.sidebar.selectbox("Colaborador", EQUIPE_AUTOMACAO)
data_inicio = st.sidebar.date_input("Início")
data_fim = st.sidebar.date_input("Fim")

if st.sidebar.button("Registrar Folga"):
    delta = (data_fim - data_inicio).days + 1
    for i in range(delta):
        dia = data_inicio + timedelta(days=i)
        st.session_state['folgas'].append({
            "Colaborador": colab_folga,
            "Data": dia,
            "Mês": dia.strftime('%m - %B'),
            "HH_Folga": jornada_disp
        })
    st.sidebar.success("Folga registrada!")

if st.sidebar.button("Limpar Tudo"):
    st.session_state['db_pd'] = pd.DataFrame()
    st.session_state['arquivos_processados'] = []
    st.session_state['folgas'] = []
    st.rerun()

# --- PROCESSAMENTO ---
if uploaded_files:
    for file in uploaded_files:
        if file.name not in st.session_state['arquivos_processados']:
            df = processar_pdf(file)
            if not df.empty:
                col_sup = [c for c in df.columns if 'Supervisão' in c][0]
                col_rec = [c for c in df.columns if 'recursos' in c.lower()][0]
                col_dur = [c for c in df.columns if 'Duração' in c][0]
                col_data = [c for c in df.columns if 'Início' in c or 'Data' in c][0]

                df_aut = df[df[col_sup].str.contains('Automação', case=False, na=False)].copy()
                data_obj = datetime.now()
                try:
                    data_str = re.search(r'\d{2}/\d{2}/\d{2}', str(df_aut[col_data].iloc[0])).group()
                    data_obj = datetime.strptime(data_str, '%d/%m/%y')
                except: pass

                df_aut['HH_Prog'] = df_aut[col_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
                df_aut['Execs'] = df_aut[col_rec].str.split(';')
                df_exp = df_aut.explode('Execs')
                df_exp['Colaborador'] = df_exp['Execs'].apply(normalizar_nome)
                df_exp = df_exp.dropna(subset=['Colaborador'])
                
                df_exp['Data'] = data_obj.date()
                df_exp['Mês'] = data_obj.strftime('%m - %B')
                df_exp['Arquivo'] = file.name
                
                st.session_state['db_pd'] = pd.concat([st.session_state['db_pd'], df_exp], ignore_index=True)
                st.session_state['arquivos_processados'].append(file.name)

# --- EXIBIÇÃO ---
if not st.session_state['db_pd'].empty or st.session_state['folgas']:
    df_m = st.session_state['db_pd']
    df_f_raw = pd.DataFrame(st.session_state['folgas'])
    
    meses_totais = sorted(list(set(df_m['Mês'].unique() if not df_m.empty else []) | set(df_f_raw['Mês'].unique() if not df_f_raw.empty else [])))
    
    st.write("### 🔍 Filtros")
    c1, c2 = st.columns(2)
    mes_sel = c1.multiselect("Filtrar Meses", meses_totais, default=meses_totais)
    colab_sel = c2.multiselect("Filtrar Equipe", EQUIPE_AUTOMACAO, default=EQUIPE_AUTOMACAO)
    
    t1, t2, t3 = st.tabs(["🌎 Geral Acumulado", "📅 Visão Diária", "🏖️ Folgas e Ausências"])

    with t1:
        if not df_m.empty:
            df_geral = df_m[(df_m['Mês'].isin(mes_sel)) & (df_m['Colaborador'].isin(colab_sel))]
            res_g = df_geral.groupby('Colaborador').agg({'Data': 'nunique', 'HH_Prog': 'sum'}).reset_index()
            res_g.columns = ['Colaborador', 'N° de dias computadados', 'HH Programado']
            res_g['HH Disponível'] = res_g['N° de dias computadados'] * jornada_disp
            res_g['Saldo HH'] = res_g['HH Disponível'] - res_g['HH Programado']
            res_g['% Carga'] = (res_g['HH Programado'] / res_g['HH Disponível'] * 100).round(1)
            
            st.metric("Total HH Disponível Equipe", f"{res_g['HH Disponível'].sum():.1f}h")
            st.dataframe(res_g[['Colaborador', 'N° de dias computadados', 'HH Disponível', 'HH Programado', 'Saldo HH', '% Carga']], use_container_width=True)

    with t2:
        if not df_m.empty:
            df_dia_f = df_m[(df_m['Mês'].isin(mes_sel)) & (df_m['Colaborador'].isin(colab_sel))]
            for d in sorted(df_dia_f['Data'].unique(), reverse=True):
                st.write(f"📅 **Data: {d.strftime('%d/%m/%Y')}**")
                df_d = df_dia_f[df_dia_f['Data'] == d]
                res_d = df_d.groupby('Colaborador')['HH_Prog'].sum().reset_index()
                res_d['HH Disponível'] = jornada_disp
                res_d['Saldo HH'] = jornada_disp - res_d['HH_Prog']
                res_d['% Carga'] = (res_d['HH_Prog'] / jornada_disp * 100).round(1)
                st.table(res_d[['Colaborador', 'HH Disponível', 'HH_Prog', 'Saldo HH', '% Carga']])

    with t3:
        if not df_f_raw.empty:
            df_folga_f = df_f_raw[(df_f_raw['Mês'].isin(mes_sel)) & (df_f_raw['Colaborador'].isin(colab_sel))]
            st.write("#### Relatório de Ausências no Período Selecionado")
            res_f = df_folga_f.groupby('Colaborador').agg({'Data': 'count', 'HH_Folga': 'sum'}).reset_index()
            res_f.columns = ['Colaborador', 'Dias de Folga', 'HH Total Folga']
            
            # Referência de 176h/mês para o cálculo de impacto anual/mensal
            res_f['% Impacto'] = (res_f['HH Total Folga'] / (len(mes_sel)*176) * 100).round(1)
            st.dataframe(res_f, use_container_width=True)
            st.write("---")
            st.write("📜 **Lista de Datas de Folga:**")
            st.write(df_folga_f[['Colaborador', 'Data', 'Mês']])
                
