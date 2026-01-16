import streamlit as st
import pandas as pd
import pdfplumber
import re
import unicodedata
from datetime import datetime, timedelta

st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# --- INICIALIZAÇÃO DA MEMÓRIA (PERSISTÊNCIA) ---
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
    # Prioridade para nomes que costumam vir parciais ou com sobrenomes
    if "GERALDO" in t: return "JOSÉ GERALDO"
    if "EDILON" in t: return "EDILON"
    for nome in EQUIPE:
        if normalizar(nome) in t: return nome
    return None

def extrair_dados_pdf(file):
    try:
        with pdfplumber.open(file) as pdf:
            dados = []
            for page in pdf.pages:
                table = page.extract_table()
                if table: dados.extend(table)
            
            if not dados: return pd.DataFrame()
            
            df_raw = pd.DataFrame(dados)
            # Localizar linha do cabeçalho
            h_idx = None
            for i, row in df_raw.iterrows():
                row_str = " ".join([str(x) for x in row if x]).lower()
                if "supervisão" in row_str or "recursos" in row_str:
                    h_idx = i
                    break
            
            if h_idx is None: return pd.DataFrame()
            
            headers = [str(c).lower().replace('\n', ' ') for c in df_raw.iloc[h_idx]]
            df = df_raw.drop(range(h_idx + 1)).reset_index(drop=True)
            
            # Identificação de colunas por palavra-chave (mais seguro)
            idx_sup = next(i for i, h in enumerate(headers) if 'superv' in h)
            idx_rec = next(i for i, h in enumerate(headers) if 'recursos' in h or 'nomes' in h)
            idx_dur = next(i for i, h in enumerate(headers) if 'dura' in h)
            idx_dat = next(i for i, h in enumerate(headers) if any(x in h for x in ['início', 'data', 'começo']))

            # Filtro Automação
            df = df[df[idx_sup].astype(str).str.contains('Automação', case=False, na=False)].copy()
            
            # Extrair Data (importante para o 19.01.pdf)
            primeira_data_celula = str(df[idx_dat].iloc[0]).replace('\n', ' ')
            dt_match = re.search(r'\d{2}/\d{2}/\d{2}', primeira_data_celula)
            data_ref = datetime.strptime(dt_match.group(), '%d/%m/%y').date() if dt_match else datetime.now().date()
            
            # Tratamento de HH e Nomes (Limpando quebras de linha do PDF)
            def limpar_hh(val):
                nums = re.findall(r'\d+', str(val).replace('\n', ''))
                return int(nums[0])/60 if nums else 0

            df['HH'] = df[idx_dur].apply(limpar_hh)
            df['Nomes_Limpos'] = df[idx_rec].fillna("").astype(str).str.replace('\n', ' ').str.split(';')
            
            # Explodir nomes e identificar
            df = df.explode('Nomes_Limpos')
            df['Colaborador'] = df['Nomes_Limpos'].apply(identificar_colab)
            df = df.dropna(subset=['Colaborador'])
            
            return pd.DataFrame({
                'Colaborador': df['Colaborador'],
                'HH': df['HH'],
                'Data': data_ref,
                'Mês': data_ref.strftime('%m - %B')
            })
    except Exception as e:
        st.error(f"Erro ao processar {file.name}: {e}")
        return pd.DataFrame()

# --- SIDEBAR ---
st.sidebar.header("📁 Entrada de Dados")
uploaded_files = st.sidebar.file_uploader("Carregar PDFs (19.01, SEM04, etc)", type="pdf", accept_multiple_files=True)
jornada_h = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

with st.sidebar.expander("🏖️ Lançar Intervalo de Folga"):
    colab_f = st.selectbox("Colaborador", EQUIPE)
    data_ini = st.date_input("Início")
    data_fim = st.date_input("Fim")
    if st.button("Salvar Período de Folga"):
        novas = []
        curr = data_ini
        while curr <= data_fim:
            novas.append({'Colaborador': colab_f, 'Data': curr})
            curr += timedelta(days=1)
        st.session_state.folgas = pd.concat([st.session_state.folgas, pd.DataFrame(novas)]).drop_duplicates()
        st.success("Folgas registradas!")

if st.sidebar.button("🗑️ Limpar Tudo (Reset)"):
    st.session_state.db_pd = pd.DataFrame()
    st.session_state.arquivos_lidos = []
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])
    st.rerun()

# --- PROCESSAMENTO ---
if uploaded_files:
    for f in uploaded_files:
        if f.name not in st.session_state.arquivos_lidos:
            res = extrair_dados_pdf(f)
            if not res.empty:
                st.session_state.db_pd = pd.concat([st.session_state.db_pd, res], ignore_index=True)
                st.session_state.arquivos_lidos.append(f.name)

# --- DASHBOARD DE INDICADORES ---
if not st.session_state.db_pd.empty:
    hist = st.session_state.db_pd
    folgas = st.session_state.folgas
    
    # 1. INDICADORES GERAIS (ANO/PERÍODO)
    st.subheader("📈 Indicadores Consolidados")
    dias_unicos = hist['Data'].unique()
    n_dias_computados = len(dias_unicos)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nº de Dias Computados", n_dias_computados)
    
    resumo_anual = []
    for p in EQUIPE:
        hh_prog = hist[hist['Colaborador'] == p]['HH'].sum()
        # Dias de folga que caem dentro dos dias que temos PDF
        dias_f = folgas[(folgas['Colaborador'] == p) & (folgas['Data'].isin(dias_unicos))].shape[0]
        
        hh_disp = (n_dias_computados - dias_f) * jornada_h
        saldo = hh_disp - hh_prog
        carga = (hh_prog / hh_disp * 100) if hh_disp > 0 else 0
        
        resumo_anual.append({
            "Colaborador": p,
            "Dias Úteis": n_dias_computados - dias_f,
            "HH Disponível": round(hh_disp, 1),
            "HH Programado": round(hh_prog, 1),
            "Saldo HH": round(saldo, 1),
            "% de Carga": f"{carga:.1f}%"
        })
    
    st.table(pd.DataFrame(resumo_anual))

    # 2. ABAS DE DETALHAMENTO
    tab1, tab2 = st.tabs(["📅 Detalhe Diário", "🏖️ Folgas Concedidas"])
    
    with tab1:
        for d in sorted(dias_unicos, reverse=True):
            with st.expander(f"Programação do dia {d.strftime('%d/%m/%Y')}"):
                dia_df = hist[hist['Data'] == d]
                st.dataframe(dia_df.groupby('Colaborador')['HH'].sum().reset_index(), use_container_width=True)

    with tab2:
        if not folgas.empty:
            st.write("Lista de folgas registradas no sistema:")
            st.dataframe(folgas.sort_values(by='Data', ascending=False), use_container_width=True)
        else:
            st.info("Nenhuma folga registrada até o momento.")

else:
    st.info("Por favor, carregue os arquivos PDF na barra lateral para gerar os indicadores.")
