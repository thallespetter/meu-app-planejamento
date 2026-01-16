import streamlit as st
import pandas as pd
import pdfplumber
import re
import unicodedata
from datetime import datetime, timedelta

# 1. CONFIGURAÇÃO E MEMÓRIA
st.set_page_config(page_title="Gestão HH Automação", layout="wide")

if 'historico' not in st.session_state:
    st.session_state.historico = pd.DataFrame()
if 'arquivos_lidos' not in st.session_state:
    st.session_state.arquivos_lidos = []
if 'folgas' not in st.session_state:
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])

st.title("📊 Gestão de Planejamento - Automação")

# 2. EQUIPE E AUXILIARES
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

# 3. EXTRAÇÃO DE DADOS (BLINDADA)
def extrair_dados_pdf(file):
    with pdfplumber.open(file) as pdf:
        dados = []
        for page in pdf.pages:
            table = page.extract_table()
            if table: dados.extend(table)
        
        if not dados: return pd.DataFrame()
        
        df_raw = pd.DataFrame(dados)
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
        except: return pd.DataFrame()

        df = df[df[idx_sup].astype(str).str.contains('Automação', case=False, na=False)].copy()
        if df.empty: return pd.DataFrame()

        dt_match = re.search(r'\d{2}/\d{2}/\d{2}', str(df[idx_dat].iloc[0]))
        data_ref = datetime.strptime(dt_match.group(), '%d/%m/%y').date() if dt_match else datetime.now().date()
        
        df['HH'] = df[idx_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
        df['Colab_List'] = df[idx_rec].fillna("").astype(str).str.split('\n').apply(lambda x: [identificar_colab(n) for n in x if identificar_colab(n)])
        df = df.explode('Colab_List').dropna(subset=['Colab_List'])
        
        return pd.DataFrame({'Colaborador': df['Colab_List'], 'HH': df['HH'], 'Data': data_ref, 'Mês': data_ref.strftime('%m - %B')})

# 4. INTERFACE LATERAL (INPUTS)
st.sidebar.header("📁 Entrada de Dados")
files = st.sidebar.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)
jornada_h = st.sidebar.number_input("Jornada Diária (Horas)", value=8.0)

with st.sidebar.expander("🏖️ Lançar Intervalo de Folga"):
    colab_f = st.selectbox("Colaborador", EQUIPE)
    d_ini = st.date_input("Início")
    d_fim = st.date_input("Fim")
    if st.button("Registrar Folga"):
        novas = []
        curr = d_ini
        while curr <= d_fim:
            novas.append({'Colaborador': colab_f, 'Data': curr})
            curr += timedelta(days=1)
        st.session_state.folgas = pd.concat([st.session_state.folgas, pd.DataFrame(novas)]).drop_duplicates()
        st.success("Folgas registradas!")

if st.sidebar.button("🗑️ Resetar Sistema"):
    st.session_state.historico = pd.DataFrame()
    st.session_state.arquivos_lidos = []
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])
    st.rerun()

# 5. PROCESSAMENTO
if files:
    for f in files:
        if f.name not in st.session_state.arquivos_lidos:
            res = extrair_dados_pdf(f)
            if not res.empty:
                st.session_state.historico = pd.concat([st.session_state.historico, res], ignore_index=True)
                st.session_state.arquivos_lidos.append(f.name)

# 6. DASHBOARD E INDICADORES
if not st.session_state.historico.empty:
    hist = st.session_state.historico
    
    st.write("### 🔍 Filtros de Visualização")
    c1, c2 = st.columns(2)
    f_mes = c1.multiselect("Filtrar Meses", sorted(hist['Mês'].unique()), default=hist['Mês'].unique())
    f_col = c2.multiselect("Filtrar Equipe", EQUIPE, default=EQUIPE)
    
    df_filtrado = hist[(hist['Mês'].isin(f_mes)) & (hist['Colaborador'].isin(f_col))]
    
    tab1, tab2 = st.tabs(["🌎 Indicadores do Período", "📅 Detalhe Diário"])

    with tab1:
        dias_no_periodo = df_filtrado['Data'].nunique()
        st.info(f"Indicadores baseados em {dias_no_periodo} dias de programação carregados.")
        
        dados_resumo = []
        for p in f_col:
            hh_prog = df_filtrado[df_filtrado['Colaborador'] == p]['HH'].sum()
            # Conta folgas apenas dentro dos dias que existem nos PDFs carregados
            dias_f = st.session_state.folgas[(st.session_state.folgas['Colaborador'] == p) & (st.session_state.folgas['Data'].isin(df_filtrado['Data'].unique()))].shape[0]
            
            dias_uteis = dias_no_periodo - dias_f
            hh_disp = dias_uteis * jornada_h
            saldo = hh_disp - hh_prog
            carga = (hh_prog / hh_disp * 100) if hh_disp > 0 else 0
            
            dados_resumo.append({
                "Colaborador": p,
                "Dias Computados": dias_uteis,
                "HH Disponível": round(hh_disp, 1),
                "HH Programado": round(hh_prog, 1),
                "Saldo HH": round(saldo, 1),
                "% Carga": f"{carga:.1f}%"
            })
        
        st.table(pd.DataFrame(dados_resumo))

    with tab2:
        for d in sorted(df_filtrado['Data'].unique(), reverse=True):
            with st.expander(f"Data: {d.strftime('%d/%m/%Y')}"):
                dia_df = df_filtrado[df_filtrado['Data'] == d]
                quem_folga = st.session_state.folgas[st.session_state.folgas['Data'] == d]['Colaborador'].tolist()
                
                res_dia = dia_df.groupby('Colaborador')['HH'].sum().reset_index()
                res_dia['Status'] = res_dia['Colaborador'].apply(lambda x: "🏖️ Folga" if x in quem_folga else "✅ Ativo")
                st.dataframe(res_dia, use_container_width=True)
else:
    st.warning("Aguardando upload de arquivos para gerar indicadores.")
