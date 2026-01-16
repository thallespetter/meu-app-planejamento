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

# --- LISTA OFICIAL (Normalizada para busca) ---
EQUIPE_AUTOMACAO = [
    "ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", 
    "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"
]

def normalizar_nome(nome):
    if not nome: return None
    nome_limpo = str(nome).upper()
    # Remove acentos básicos para comparação
    nome_limpo = nome_limpo.replace("É", "E").replace("Ó", "O")
    
    for ref in EQUIPE_AUTOMACAO:
        ref_limpa = ref.replace("É", "E").replace("Ó", "O")
        if ref_limpa in nome_limpo: 
            return ref
    return None

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
        
        # TRATAMENTO DE COLUNAS DUPLICADAS (Evita o erro ValueError)
        df.columns = pd.io.common.dedup_names(headers, is_unicode=True)
        return df

# --- SIDEBAR: FOLGAS E UPLOAD ---
st.sidebar.header("📁 Upload de Dados")
uploaded_files = st.sidebar.file_uploader("Adicionar PDFs", type="pdf", accept_multiple_files=True)
jornada_disp = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

st.sidebar.markdown("---")
st.sidebar.header("🏖️ Lançar Folga")
colab_folga = st.sidebar.selectbox("Colaborador", EQUIPE_AUTOMACAO)
data_inicio = st.sidebar.date_input("Início da Folga")
data_fim = st.sidebar.date_input("Fim da Folga")

if st.sidebar.button("Registrar Folga"):
    delta = (data_fim - data_inicio).days + 1
    for i in range(delta):
        dia = data_inicio + timedelta(days=i)
        st.session_state['folgas'].append({
            "Colaborador": colab_folga,
            "Data": dia,
            "HH_Folga": jornada_disp,
            "Mês": dia.strftime('%m - %B')
        })
    st.sidebar.success(f"Folga de {colab_folga} registrada!")

if st.sidebar.button("Limpar Todos os Dados"):
    st.session_state['db_pd'] = pd.DataFrame()
    st.session_state['arquivos_processados'] = []
    st.session_state['folgas'] = []
    st.rerun()

# --- PROCESSAMENTO DOS PDFs ---
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
                
                sample_date = str(df_aut[col_data].iloc[0]) if not df_aut.empty else ""
                data_obj = datetime.now()
                try:
                    data_str = re.search(r'\d{2}/\d{2}/\d{2}', sample_date).group()
                    data_obj = datetime.strptime(data_str, '%d/%m/%y')
                except: pass

                df_aut['HH_Prog'] = df_aut[col_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
                df_aut['Executantes'] = df_aut[col_rec].str.split(';')
                df_exploded = df_aut.explode('Executantes')
                
                df_exploded['Colaborador'] = df_exploded['Executantes'].apply(normalizar_nome)
                df_exploded = df_exploded.dropna(subset=['Colaborador'])
                
                df_exploded['Data'] = data_obj.date()
                df_exploded['Mês'] = data_obj.strftime('%m - %B')
                df_exploded['Arquivo'] = file.name
                novos_dados.append(df_exploded)
                st.session_state['arquivos_processados'].append(file.name)
    
    if novos_dados:
        st.session_state['db_pd'] = pd.concat([st.session_state['db_pd'], pd.concat(novos_dados)], ignore_index=True)

# --- EXIBIÇÃO ---
if not st.session_state['db_pd'].empty or st.session_state['folgas']:
    df_m = st.session_state['db_pd']
    df_folgas = pd.DataFrame(st.session_state['folgas'])
    
    st.write("### 🔍 Filtros")
    c1, c2, c3 = st.columns(3)
    meses_disp = sorted(df_m['Mês'].unique()) if not df_m.empty else sorted(df_folgas['Mês'].unique())
    mes_sel = c1.multiselect("Mês", meses_disp, default=meses_disp)
    colab_sel = c3.multiselect("Colaborador", EQUIPE_AUTOMACAO, default=EQUIPE_AUTOMACAO)
    
    t1, t2, t3 = st.tabs(["🌎 Relatório Geral", "📅 Visão Diária", "🏖️ Controle de Folgas"])

    with t1:
        if not df_m.empty:
            df_f = df_m[(df_m['Mês'].isin(mes_sel)) & (df_m['Colaborador'].isin(colab_sel))]
            
            # Cálculo de dias úteis excluindo folgas
            res_g = df_f.groupby('Colaborador').agg({'Data': 'nunique', 'HH_Prog': 'sum'}).reset_index()
            res_g.columns = ['Colaborador', 'Dias Programados', 'HH Programado']
            
            # HH Disponível Total (8h por dia computado no PDF)
            res_g['HH Disponível'] = res_g['Dias Programados'] * jornada_disp
            res_g['% Carga'] = (res_g['HH Programado'] / res_g['HH Disponível'] * 100).round(1)
            
            st.write("#### Acumulado Anual (Programado em PDF)")
            st.dataframe(res_g[['Colaborador', 'Dias Programados', 'HH Disponível', 'HH Programado', '% Carga']], use_container_width=True)
            
            # Métricas Totais
            st.metric("HH Total Disponível Equipe", f"{res_g['HH Disponível'].sum():.1f}h")

    with t2:
        if not df_m.empty:
            df_f = df_m[(df_m['Mês'].isin(mes_sel)) & (df_m['Colaborador'].isin(colab_sel))]
            for d in sorted(df_f['Data'].unique(), reverse=True):
                st.write(f"📅 **Data: {d.strftime('%d/%m/%Y')}**")
                df_d = df_f[df_f['Data'] == d]
                res_d = df_d.groupby('Colaborador')['HH_Prog'].sum().reset_index()
                res_d['HH Disponível'] = jornada_disp
                res_d['% Carga'] = (res_d['HH_Prog'] / jornada_disp * 100).round(1)
                st.table(res_d)

    with t3:
        if not df_folgas.empty:
            df_f_filt = df_folgas[(df_folgas['Mês'].isin(mes_sel)) & (df_folgas['Colaborador'].isin(colab_sel))]
            st.write("#### Resumo de Ausências/Folgas")
            res_folga = df_f_filt.groupby('Colaborador').agg({'Data': 'count', 'HH_Folga': 'sum'}).reset_index()
            res_folga.columns = ['Colaborador', 'Dias de Folga', 'Total HH Folga']
            
            # Cálculo de % em relação ao período (considerando 22 dias úteis/mês como base ou total de dias no app)
            total_periodo_hh = 176.0 # Exemplo base mensal
            res_folga['% do Período'] = (res_folga['Total HH Folga'] / total_periodo_hh * 100).round(1)
            
            st.dataframe(res_folga, use_container_width=True)
            st.write("*(Cálculo baseado em 176h mensais de referência)*")
        else:
            st.info("Nenhuma folga registrada para os filtros selecionados.")
