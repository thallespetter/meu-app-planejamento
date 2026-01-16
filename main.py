import streamlit as st
import pandas as pd
import pdfplumber
import re
import unicodedata
import io
from datetime import datetime, timedelta

# Configuração da página
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
    if "GERALDO" in t: return "JOSÉ GERALDO"
    if "EDILON" in t: return "EDILON"
    for nome in EQUIPE:
        if normalizar(nome) in t: return nome
    return None

@st.cache_data(show_spinner=False)
def extrair_dados_pdf_robusto(file_bytes, file_name):
    try:
        # Processamento via BytesIO para evitar AxiosError (Network Error)
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            dados = []
            for page in pdf.pages:
                # Estratégia de extração otimizada para tabelas complexas
                table = page.extract_table({
                    "vertical_strategy": "lines", 
                    "horizontal_strategy": "lines",
                })
                if table:
                    dados.extend(table)
                page.flush_cache() # Limpeza de memória imediata
            
            if not dados: return pd.DataFrame()
            
            df_raw = pd.DataFrame(dados)
            h_idx = None
            for i, row in df_raw.iterrows():
                row_str = " ".join([str(x) for x in row if x]).lower()
                if "supervisão" in row_str:
                    h_idx = i
                    break
            
            if h_idx is None: return pd.DataFrame()
            
            headers = [str(c).lower().replace('\n', ' ') for c in df_raw.iloc[h_idx]]
            df = df_raw.drop(range(h_idx + 1)).reset_index(drop=True)
            
            idx_sup = next((i for i, h in enumerate(headers) if 'superv' in h), None)
            idx_rec = next((i for i, h in enumerate(headers) if 'recursos' in h or 'nomes' in h), None)
            idx_dur = next((i for i, h in enumerate(headers) if 'dura' in h or 'ssuorra' in h), None)
            idx_dat = next((i for i, h in enumerate(headers) if any(x in h for x in ['início', 'data', 'começo'])), None)

            if None in [idx_sup, idx_rec, idx_dur, idx_dat]:
                return pd.DataFrame()

            df = df[df[idx_sup].astype(str).str.contains('Automação', case=False, na=False)].copy()
            if df.empty: return pd.DataFrame()
            
            primeira_data_celula = str(df[idx_dat].iloc[0]).replace('\n', ' ')
            dt_match = re.search(r'\d{2}/\d{2}/\d{2}', primeira_data_celula)
            data_ref = datetime.strptime(dt_match.group(), '%d/%m/%y').date() if dt_match else datetime.now().date()
            
            def limpar_hh(val):
                nums = re.findall(r'\d+', str(val).replace('\n', ''))
                return int(nums[0])/60 if nums else 0

            df['HH'] = df[idx_dur].apply(limpar_hh)
            df['Nomes_Limpos'] = df[idx_rec].fillna("").astype(str).str.replace('\n', ' ').str.split(';')
            df = df.explode('Nomes_Limpos')
            df['Colaborador'] = df['Nomes_Limpos'].apply(identificar_colab)
            df = df.dropna(subset=['Colaborador'])
            
            return pd.DataFrame({
                'Colaborador': df['Colaborador'],
                'HH': df['HH'],
                'Data': data_ref,
                'Ano': data_ref.year,
                'Mês': data_ref.strftime('%m - %B')
            })
    except Exception:
        return pd.DataFrame()

# --- SIDEBAR ---
st.sidebar.header("📁 Entrada de Dados")
uploaded_files = st.sidebar.file_uploader("Carregar PDFs", type="pdf", accept_multiple_files=True)
jornada_h = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

if uploaded_files:
    for f in uploaded_files:
        if f.name not in st.session_state.arquivos_lidos:
            file_bytes = f.read() # Leitura única dos bytes
            res = extrair_dados_pdf_robusto(file_bytes, f.name)
            if not res.empty:
                st.session_state.db_pd = pd.concat([st.session_state.db_pd, res], ignore_index=True)
                st.session_state.arquivos_lidos.append(f.name)
            else:
                st.sidebar.warning(f"Aviso: {f.name} não contém dados de Automação ou formato inválido.")

# Filtros na Sidebar
st.sidebar.markdown("---")
st.sidebar.header("🔍 Filtros de Visualização")
if not st.session_state.db_pd.empty:
    anos = sorted(st.session_state.db_pd['Ano'].unique())
    meses = sorted(st.session_state.db_pd['Mês'].unique(), key=lambda x: x.split(' - ')[0])
    
    filtro_ano = st.sidebar.multiselect("Ano", anos, default=anos)
    filtro_mes = st.sidebar.multiselect("Mês", meses, default=meses)
    filtro_colab = st.sidebar.multiselect("Colaborador", EQUIPE, default=EQUIPE)
else:
    st.sidebar.info("Carregue dados para filtrar.")

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

# --- LÓGICA DE FILTRAGEM ---
if not st.session_state.db_pd.empty:
    df_filtrado = st.session_state.db_pd[
        (st.session_state.db_pd['Ano'].isin(filtro_ano)) &
        (st.session_state.db_pd['Mês'].isin(filtro_mes)) &
        (st.session_state.db_pd['Colaborador'].isin(filtro_colab))
    ]
    
    folgas_filtradas = st.session_state.folgas[
        (st.session_state.folgas['Colaborador'].isin(filtro_colab))
    ]

    if not df_filtrado.empty:
        st.subheader("📈 Indicadores Consolidados")
        dias_unicos = sorted(df_filtrado['Data'].unique())
        n_dias = len(dias_unicos)
        
        total_hh_prog = df_filtrado['HH'].sum()
        total_hh_disp = 0
        resumo_tabela = []
        
        for p in filtro_colab:
            hh_p = df_filtrado[df_filtrado['Colaborador'] == p]['HH'].sum()
            dias_f = folgas_filtradas[(folgas_filtradas['Colaborador'] == p) & (folgas_filtradas['Data'].isin(dias_unicos))].shape[0]
            hh_d = (n_dias - dias_f) * jornada_h
            total_hh_disp += hh_d
            
            saldo = hh_d - hh_p
            carga = (hh_p / hh_d * 100) if hh_d > 0 else 0
            
            resumo_tabela.append({
                "Colaborador": p,
                "Dias Úteis": n_dias - dias_f,
                "HH Disponível": round(hh_d, 1),
                "HH Programado": round(hh_p, 1),
                "Saldo HH": round(saldo, 1),
                "% de Carga": f"{carga:.1f}%"
            })

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Nº de Dias Computados", n_dias)
        c2.metric("Total HH Disponível", f"{total_hh_disp:.1f}h")
        c3.metric("Total HH Programado", f"{total_hh_prog:.1f}h")
        carga_total = (total_hh_prog / total_hh_disp * 100) if total_hh_disp > 0 else 0
        c4.metric("% Carga Total", f"{carga_total:.1f}%")
        
        st.table(pd.DataFrame(resumo_tabela))

        tab1, tab2, tab3 = st.tabs(["📅 Detalhe Diário", "🏖️ Folgas Concedidas", "📊 Resumo de Folgas"])
        
        with tab1:
            for d in sorted(dias_unicos, reverse=True):
                with st.expander(f"Programação do dia {d.strftime('%d/%m/%Y')}"):
                    dia_df = df_filtrado[df_filtrado['Data'] == d]
                    st.dataframe(dia_df.groupby('Colaborador')['HH'].sum().reset_index(), use_container_width=True)

        with tab2:
            if not folgas_filtradas.empty:
                st.dataframe(folgas_filtradas.sort_values(by='Data', ascending=False), use_container_width=True)
            else:
                st.info("Nenhuma folga no filtro selecionado.")

        with tab3:
            resumo_f = []
            for p in filtro_colab:
                dias_f = st.session_state.folgas[st.session_state.folgas['Colaborador'] == p].shape[0]
                resumo_f.append({"Colaborador": p, "Total Horas Folga": dias_f * jornada_h})
            st.table(pd.DataFrame(resumo_f))
    else:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
else:
    st.info("Aguardando carregamento de arquivos PDF...")
