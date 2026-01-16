import streamlit as st
import pandas as pd
import pdfplumber
import re
import unicodedata
from datetime import datetime, timedelta

st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# --- PERSISTÊNCIA DE DADOS ---
if 'historico' not in st.session_state:
    st.session_state.historico = pd.DataFrame()
if 'arquivos_lidos' not in st.session_state:
    st.session_state.arquivos_lidos = []
if 'folgas' not in st.session_state:
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])

st.title("📊 Gestão de Planejamento - Automação")

EQUIPE = ["ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"]

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(txt).upper()) if unicodedata.category(c) != 'Mn').strip()

def identificar_colab(texto):
    t = normalizar(texto)
    if not t: return None
    # Prioridade para nomes que costumam vir parciais
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
        
        # Localizar linha do cabeçalho
        h_idx = None
        for i, row in df_raw.iterrows():
            row_str = " ".join([str(x) for x in row if x]).lower()
            if "supervisão" in row_str or "recursos" in row_str:
                h_idx = i
                break
        
        if h_idx is None: return pd.DataFrame()
        
        headers = [str(c).lower() for c in df_raw.iloc[h_idx]]
        df = df_raw.drop(range(h_idx + 1)).reset_index(drop=True)
        
        try:
            idx_sup = [i for i, h in enumerate(headers) if 'superv' in h][0]
            idx_rec = [i for i, h in enumerate(headers) if 'recursos' in h or 'nomes' in h][0]
            idx_dur = [i for i, h in enumerate(headers) if 'dura' in h][0]
            idx_dat = [i for i, h in enumerate(headers) if any(x in h for x in ['início', 'data', 'começo'])][0]
        except IndexError:
            return pd.DataFrame()

        # Filtro Automação
        df = df[df[idx_sup].astype(str).str.contains('Automação', case=False, na=False)].copy()
        if df.empty: return pd.DataFrame()

        # Data do arquivo
        dt_match = re.search(r'\d{2}/\d{2}/\d{2}', str(df[idx_dat].iloc[0]))
        data_ref = datetime.strptime(dt_match.group(), '%d/%m/%y').date() if dt_match else datetime.now().date()
        
        # Tratamento de HH (Pega números de strings como '480 mins')
        def extrair_hh(valor):
            nums = re.findall(r'\d+', str(valor))
            return int(nums[0])/60 if nums else 0

        df['HH'] = df[idx_dur].apply(extrair_hh)
        
        # CORREÇÃO DO ERRO TYPEERROR: Tratando valores nulos antes do split
        df['Colaborador'] = df[idx_rec].fillna("").astype(str).str.split('\n')
        df['Colaborador'] = df['Colaborador'].apply(lambda x: [identificar_colab(n) for n in x if identificar_colab(n)])
        
        df = df.explode('Colaborador').dropna(subset=['Colaborador'])
        
        return pd.DataFrame({
            'Colaborador': df['Colaborador'],
            'HH': df['HH'],
            'Data': data_ref,
            'Mês': data_ref.strftime('%m - %B')
        })

# --- BARRA LATERAL ---
st.sidebar.header("📁 Gestão de Dados")
uploaded_files = st.sidebar.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)
jornada_h = st.sidebar.number_input("Jornada Diária (Horas)", value=8.0)

# RESTAURADO: Intervalo de folgas
with st.sidebar.expander("🏖️ Registrar Intervalo de Folga"):
    colab_f = st.selectbox("Funcionário", EQUIPE)
    data_ini = st.date_input("Data Início")
    data_fim = st.date_input("Data Fim")
    if st.button("Salvar Folga"):
        novas_folgas = []
        atual = data_ini
        while atual <= data_fim:
            novas_folgas.append({'Colaborador': colab_f, 'Data': atual})
            atual += timedelta(days=1)
        st.session_state.folgas = pd.concat([st.session_state.folgas, pd.DataFrame(novas_folgas)]).drop_duplicates()
        st.success("Folgas registradas!")

if st.sidebar.button("🗑️ Limpar Banco de Dados"):
    st.session_state.historico = pd.DataFrame()
    st.session_state.arquivos_lidos = []
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])
    st.rerun()

# --- PROCESSAMENTO ---
if uploaded_files:
    for f in uploaded_files:
        if f.name not in st.session_state.arquivos_lidos:
            res = extrair_dados_pdf(f)
            if not res.empty:
                st.session_state.historico = pd.concat([st.session_state.historico, res], ignore_index=True)
                st.session_state.arquivos_lidos.append(f.name)

# --- DASHBOARD ---
if not st.session_state.historico.empty:
    hist = st.session_state.historico
    folgas = st.session_state.folgas
    
    t1, t2 = st.tabs(["🌎 Resumo de Carga HH", "📅 Detalhes Diários"])
    
    with t1:
        # Dias carregados no total
        total_dias_pdf = hist['Data'].nunique()
        st.info(f"Dados baseados em {total_dias_pdf} dias de programação carregados.")
        
        dados_resumo = []
        for p in EQUIPE:
            # HH Programado
            hh_p = hist[hist['Colaborador'] == p]['HH'].sum()
            # Dias de folga registrados que coincidem com os dias dos PDFs
            dias_f = folgas[(folgas['Colaborador'] == p) & (folgas['Data'].isin(hist['Data'].unique()))].shape[0]
            
            dias_disponiveis = total_dias_pdf - dias_f
            hh_disponivel = dias_disponiveis * jornada_h
            
            dados_resumo.append({
                "Colaborador": p,
                "Dias Úteis": dias_disponiveis,
                "HH Disponível": hh_disponivel,
                "HH Programado": round(hh_p, 1),
                "Saldo HH": round(hh_disponivel - hh_p, 1),
                "% Carga": f"{(hh_p / hh_disponivel * 100):.1f}%" if hh_disponivel > 0 else "0%"
            })
        
        st.table(pd.DataFrame(dados_resumo))

    with t2:
        for d in sorted(hist['Data'].unique(), reverse=True):
            with st.expander(f"Data: {d.strftime('%d/%m/%Y')}"):
                dia_df = hist[hist['Data'] == d]
                # Verifica quem está de folga neste dia específico
                quem_folga = folgas[folgas['Data'] == d]['Colaborador'].tolist()
                
                # Exibe a tabela do dia
                res_dia = dia_df.groupby('Colaborador')['HH'].sum().reset_index()
                res_dia['Status'] = res_dia['Colaborador'].apply(lambda x: "Folga" if x in quem_folga else "Ativo")
                st.dataframe(res_dia, use_container_width=True)
