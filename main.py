import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import unicodedata
import io
from datetime import datetime, timedelta

# Configuração da página para máxima performance
st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# --- INICIALIZAÇÃO DA MEMÓRIA ---
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

def extrair_dados_pdf_seguro(file_obj):
    try:
        file_bytes = file_obj.getvalue()
        if not file_bytes: return pd.DataFrame()
            
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        dados_lista = []
        data_ref = datetime.now().date()
        
        primeira_pag_texto = doc[0].get_text()
        dt_match = re.search(r'\d{2}/\d{2}/\d{2}', primeira_pag_texto)
        if dt_match:
            try:
                data_ref = datetime.strptime(dt_match.group(), '%d/%m/%y').date()
            except: pass

        for page in doc:
            tabs = page.find_tables()
            for tab in tabs:
                df = tab.to_pandas()
                df.columns = [str(c).lower().replace('\n', ' ') for c in df.columns]
                idx_sup = next((c for c in df.columns if 'superv' in c), None)
                idx_rec = next((c for c in df.columns if 'recursos' in c or 'nomes' in c), None)
                idx_dur = next((c for c in df.columns if 'dura' in c or 'ssuorra' in c), None)
                
                if idx_sup and idx_rec and idx_dur:
                    df_aut = df[df[idx_sup].astype(str).str.contains('Automação', case=False, na=False)].copy()
                    for _, row in df_aut.iterrows():
                        nums = re.findall(r'\d+', str(row[idx_dur]).replace('\n', ''))
                        hh_val = int(nums[0])/60 if nums else 0
                        nomes_sujos = str(row[idx_rec]).replace('\n', ' ').split(';')
                        for n in nomes_sujos:
                            colab = identificar_colab(n)
                            if colab:
                                dados_lista.append({
                                    'Colaborador': colab, 'HH': hh_val, 'Data': data_ref,
                                    'Ano': data_ref.year, 'Mês': data_ref.strftime('%m - %B')
                                })
        doc.close()
        return pd.DataFrame(dados_lista)
    except Exception as e:
        st.error(f"Erro no processamento: {e}")
        return pd.DataFrame()

# --- SIDEBAR ---
st.sidebar.header("📁 Entrada de Dados")
uploaded_files = st.sidebar.file_uploader("Carregar PDFs", type="pdf", accept_multiple_files=True)
jornada_h = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

if uploaded_files:
    for f in uploaded_files:
        if f.name not in st.session_state.arquivos_lidos:
            with st.spinner(f"Lendo {f.name}..."):
                res = extrair_dados_pdf_seguro(f)
                if not res.empty:
                    st.session_state.db_pd = pd.concat([st.session_state.db_pd, res], ignore_index=True).drop_duplicates()
                    st.session_state.arquivos_lidos.append(f.name)
                    st.rerun()

# Filtros
st.sidebar.markdown("---")
st.sidebar.header("🔍 Filtros")
if not st.session_state.db_pd.empty:
    db = st.session_state.db_pd
    anos = sorted(db['Ano'].unique())
    meses = sorted(db['Mês'].unique(), key=lambda x: x.split(' - ')[0])
    f_ano = st.sidebar.multiselect("Ano", anos, default=anos)
    f_mes = st.sidebar.multiselect("Mês", meses, default=meses)
    f_colab = st.sidebar.multiselect("Colaborador", EQUIPE, default=EQUIPE)
    df_filtrado = db[(db['Ano'].isin(f_ano)) & (db['Mês'].isin(f_mes)) & (db['Colaborador'].isin(f_colab))]
else:
    df_filtrado = pd.DataFrame()

with st.sidebar.expander("🏖️ Lançar Folga"):
    c_f = st.selectbox("Colaborador", EQUIPE)
    d_i = st.date_input("Início")
    d_f = st.date_input("Fim")
    if st.button("Salvar Folga"):
        curr = d_i
        novas = []
        while curr <= d_f:
            novas.append({'Colaborador': c_f, 'Data': curr})
            curr += timedelta(days=1)
        st.session_state.folgas = pd.concat([st.session_state.folgas, pd.DataFrame(novas)]).drop_duplicates()
        st.success("Folga registrada!")

if st.sidebar.button("🗑️ Resetar Sistema"):
    st.session_state.db_pd = pd.DataFrame()
    st.session_state.arquivos_lidos = []
    st.session_state.folgas = pd.DataFrame(columns=['Colaborador', 'Data'])
    st.rerun()

# --- DASHBOARD ---
if not df_filtrado.empty:
    st.subheader("📈 Indicadores Consolidados")
    dias_u = sorted(df_filtrado['Data'].unique())
    n_dias = len(dias_u)
    total_prog = df_filtrado['HH'].sum()
    total_disp = 0
    tabela_resumo = []
    
    for p in f_colab:
        hh_p = df_filtrado[df_filtrado['Colaborador'] == p]['HH'].sum()
        dias_f = st.session_state.folgas[(st.session_state.folgas['Colaborador'] == p) & (st.session_state.folgas['Data'].isin(dias_u))].shape[0]
        hh_d = (n_dias - dias_f) * jornada_h
        total_disp += hh_d
        carga = (hh_p / hh_d * 100) if hh_d > 0 else 0
        tabela_resumo.append({
            "Colaborador": p, "Dias Úteis": n_dias - dias_f, 
            "HH Disponível": round(hh_d, 1), "HH Programado": round(hh_p, 1),
            "Saldo": round(hh_d - hh_p, 1), "% Carga": f"{carga:.1f}%"
        })

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nº de Dias Computados", n_dias)
    c2.metric("Total HH Disponível", f"{total_disp:.1f}h")
    c3.metric("Total HH Programado", f"{total_prog:.1f}h")
    carga_total = (total_prog / total_disp * 100) if total_disp > 0 else 0
    c4.metric("% Carga Total", f"{carga_total:.1f}%")
    
    st.table(pd.DataFrame(tabela_resumo))

    t1, t2, t3 = st.tabs(["📅 Detalhe Diário", "🏖️ Folgas Concedidas", "📊 Resumo de Folgas"])
    with t1:
        for d in sorted(dias_u, reverse=True):
            with st.expander(f"Programação do dia {d.strftime('%d/%m/%Y')}"):
                st.dataframe(df_filtrado[df_filtrado['Data'] == d].groupby('Colaborador')['HH'].sum().reset_index(), use_container_width=True)
    with t2:
        st.dataframe(st.session_state.folgas[st.session_state.folgas['Colaborador'].isin(f_colab)], use_container_width=True)
    with t3:
        res_f = []
        for p in f_colab:
            h_f = st.session_state.folgas[st.session_state.folgas['Colaborador'] == p].shape[0] * jornada_h
            res_f.append({"Colaborador": p, "Total Horas Folga": h_f})
        st.table(pd.DataFrame(res_f))
else:
    st.info("Por favor, carregue os arquivos PDF na barra lateral para gerar os indicadores.")
