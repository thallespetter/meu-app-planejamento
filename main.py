import streamlit as st
import pandas as pd
import pdfplumber
import re
import unicodedata
from datetime import datetime, timedelta

st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# --- MEMÓRIA DO APP ---
if 'db_pd' not in st.session_state: st.session_state['db_pd'] = pd.DataFrame()
if 'arquivos_processados' not in st.session_state: st.session_state['arquivos_processados'] = []
if 'folgas' not in st.session_state: st.session_state['folgas'] = []

# --- EQUIPE E NORMALIZAÇÃO ---
EQUIPE_AUTOMACAO = ["ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"]

def remover_acentos(txt):
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(txt).upper()) if unicodedata.category(c) != 'Mn')

def identificar_colaborador(texto_celula):
    """Busca por palavras-chave dentro da célula para não perder nomes com sobrenome ou quebra de linha"""
    texto = remover_acentos(texto_celula)
    if "GERALDO" in texto: return "JOSÉ GERALDO"
    if "EDILON" in texto: return "EDILON"
    if "ALESSANDRO" in texto: return "ALESSANDRO"
    if "ANDRE" in texto: return "ANDRÉ P"
    if "DIENIFER" in texto: return "DIENIFER"
    if "ELCIO" in texto: return "ELCIO"
    if "GILMAR" in texto: return "GILMAR"
    if "SAMUELL" in texto: return "SAMUELL"
    return None

def limpar_colunas(lista_colunas):
    """Resolve o erro 'Duplicate columns' manualmente"""
    nova_lista = []
    counts = {}
    for col in lista_colunas:
        col = col if col else "Coluna_Vazia"
        if col in counts:
            counts[col] += 1
            nova_lista.append(f"{col}_{counts[col]}")
        else:
            counts[col] = 0
            nova_lista.append(col)
    return nova_lista

# --- INTERFACE ---
st.sidebar.header("📁 Dados e Folgas")
uploaded_files = st.sidebar.file_uploader("Suba os PDFs", type="pdf", accept_multiple_files=True)
jornada_disp = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

# Lançar Folga
with st.sidebar.expander("🏖️ Lançar Folga"):
    c_folga = st.selectbox("Colaborador", EQUIPE_AUTOMACAO)
    d_ini = st.date_input("Início")
    d_fim = st.date_input("Fim")
    if st.button("Registrar Folga"):
        dias = (d_fim - d_ini).days + 1
        for i in range(dias):
            dia = d_ini + timedelta(days=i)
            st.session_state['folgas'].append({"Colaborador": c_folga, "Data": dia, "Mês": dia.strftime('%m - %B'), "HH_Folga": jornada_disp})
        st.success("Registrado!")

if st.sidebar.button("Limpar Tudo"):
    st.session_state['db_pd'] = pd.DataFrame()
    st.session_state['arquivos_processados'] = []
    st.session_state['folgas'] = []
    st.rerun()

# --- PROCESSAMENTO ---
if uploaded_files:
    for file in uploaded_files:
        if file.name not in st.session_state['arquivos_processados']:
            with pdfplumber.open(file) as pdf:
                rows = []
                for p in pdf.pages:
                    table = p.extract_table()
                    if table: rows.extend(table)
                
                if rows:
                    df_raw = pd.DataFrame(rows)
                    # Acha cabeçalho
                    h_idx = 0
                    for i, r in df_raw.iterrows():
                        if "supervisão" in " ".join(map(str, r)).lower():
                            h_idx = i; break
                    
                    df = df_raw.drop(range(h_idx + 1)).reset_index(drop=True)
                    df.columns = limpar_colunas([str(c).replace('\n', ' ').strip() for c in df_raw.iloc[h_idx]])
                    
                    # Identificar colunas cruciais
                    col_sup = [c for c in df.columns if 'Supervisão' in c][0]
                    col_rec = [c for c in df.columns if 'recursos' in c.lower()][0]
                    col_dur = [c for c in df.columns if 'Duração' in c][0]
                    col_dat = [c for c in df.columns if any(x in c for x in ['Início', 'Data', 'Termino'])][0]

                    # Filtro de Automação
                    df_aut = df[df[col_sup].str.contains('Automação', case=False, na=False)].copy()
                    
                    # Extrair Data
                    dt_obj = datetime.now()
                    try: 
                        dt_s = re.search(r'\d{2}/\d{2}/\d{2}', str(df_aut[col_dat].iloc[0])).group()
                        dt_obj = datetime.strptime(dt_s, '%d/%m/%y')
                    except: pass

                    # Processar HH e Nomes
                    df_aut['HH'] = df_aut[col_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
                    df_aut['Rec_Lista'] = df_aut[col_rec].str.split(';')
                    df_exp = df_aut.explode('Rec_Lista')
                    
                    # LOGICA DE BUSCA MELHORADA (Identificar José Geraldo e Edilon)
                    df_exp['Colaborador'] = df_exp['Rec_Lista'].apply(identificar_colaborador)
                    df_exp = df_exp.dropna(subset=['Colaborador'])
                    
                    df_exp['Data'] = dt_obj.date()
                    df_exp['Mês'] = dt_obj.strftime('%m - %B')
                    df_exp['Arquivo'] = file.name
                    
                    st.session_state['db_pd'] = pd.concat([st.session_state['db_pd'], df_exp], ignore_index=True)
                    st.session_state['arquivos_processados'].append(file.name)

# --- DASHBOARD ---
if not st.session_state['db_pd'].empty or st.session_state['folgas']:
    df_m = st.session_state['db_pd']
    df_f = pd.DataFrame(st.session_state['folgas'])
    
    st.write("### 🔍 Filtros")
    c1, c2 = st.columns(2)
    m_list = sorted(list(set(df_m['Mês'].unique() if not df_m.empty else []) | set(df_f['Mês'].unique() if not df_f.empty else [])))
    sel_mes = c1.multiselect("Meses", m_list, default=m_list)
    sel_col = c2.multiselect("Equipe", EQUIPE_AUTOMACAO, default=EQUIPE_AUTOMACAO)
    
    tab1, tab2, tab3 = st.tabs(["🌎 Geral", "📅 Diário", "🏖️ Folgas"])

    with tab1:
        if not df_m.empty:
            df_g = df_m[(df_m['Mês'].isin(sel_mes)) & (df_m['Colaborador'].isin(sel_col))]
            res = df_g.groupby('Colaborador').agg({'Data': 'nunique', 'HH': 'sum'}).reset_index()
            res.columns = ['Colaborador', 'N° de dias computadados', 'HH Programado']
            res['HH Disponível'] = res['N° de dias computadados'] * jornada_disp
            res['Saldo HH'] = res['HH Disponível'] - res['HH Programado']
            res['% Carga'] = (res['HH Programado'] / res['HH Disponível'] * 100).round(1)
            
            # Métricas Gerais
            dias_totais = df_g['Data'].nunique()
            hh_equipe_disp = dias_totais * len(sel_col) * jornada_disp
            hh_equipe_prog = res['HH Programado'].sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Dias Computados", dias_totais)
            m2.metric("HH Total Disponível", f"{hh_equipe_disp:.1f}h")
            m3.metric("HH Sem Apropriação", f"{hh_equipe_disp - hh_equipe_prog:.1f}h")

            st.dataframe(res[['Colaborador', 'N° de dias computadados', 'HH Disponível', 'HH Programado', '% Carga']], use_container_width=True)

    with tab2:
        if not df_m.empty:
            df_d = df_m[(df_m['Mês'].isin(sel_mes)) & (df_m['Colaborador'].isin(sel_col))]
            for d in sorted(df_d['Data'].unique(), reverse=True):
                st.write(f"📅 **{d.strftime('%d/%m/%Y')}**")
                res_d = df_d[df_d['Data'] == d].groupby('Colaborador')['HH'].sum().reset_index()
                res_d['HH Disponível'] = jornada_disp
                res_d['% Carga'] = (res_d['HH'] / jornada_disp * 100).round(1)
                st.table(res_d)

    with tab3:
        if not df_f.empty:
            df_f_filt = df_f[(df_f['Mês'].isin(sel_mes)) & (df_f['Colaborador'].isin(sel_col))]
            res_f = df_f_filt.groupby('Colaborador').agg({'Data': 'count', 'HH_Folga': 'sum'}).reset_index()
            res_f['% em relação ao período'] = (res_f['HH_Folga'] / (len(sel_mes)*176) * 100).round(1)
            st.dataframe(res_f)
