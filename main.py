import streamlit as st
import pandas as pd
import pdfplumber
import re
import unicodedata
from datetime import datetime, timedelta

st.set_page_config(page_title="Gestão HH Automação", layout="wide")

# --- MEMÓRIA PERSISTENTE ---
if 'db_pd' not in st.session_state: st.session_state['db_pd'] = pd.DataFrame()
if 'arquivos_processados' not in st.session_state: st.session_state['arquivos_processados'] = []
if 'folgas' not in st.session_state: st.session_state['folgas'] = []

st.title("📊 Gestão de Planejamento - Automação")

EQUIPE_AUTOMACAO = ["ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"]

def remover_acentos(txt):
    if not txt: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(txt).upper()) if unicodedata.category(c) != 'Mn')

def identificar_colaborador(texto_celula):
    texto = remover_acentos(texto_celula)
    # Ordem estratégica de busca
    if "JOSE GERALDO" in texto or "GERALDO" in texto: return "JOSÉ GERALDO"
    if "EDILON" in texto: return "EDILON"
    if "ALESSANDRO" in texto: return "ALESSANDRO"
    if "ANDRE" in texto: return "ANDRÉ P"
    if "DIENIFER" in texto: return "DIENIFER"
    if "ELCIO" in texto: return "ELCIO"
    if "GILMAR" in texto: return "GILMAR"
    if "SAMUELL" in texto: return "SAMUELL"
    return None

def limpar_colunas(lista_colunas):
    nova_lista = []
    counts = {}
    for col in lista_colunas:
        nome = str(col).replace('\n', ' ').strip() if col else "Vazia"
        if nome in counts:
            counts[nome] += 1
            nova_lista.append(f"{nome}_{counts[nome]}")
        else:
            counts[nome] = 0
            nova_lista.append(nome)
    return nova_lista

# --- SIDEBAR ---
st.sidebar.header("📁 Banco de Dados")
uploaded_files = st.sidebar.file_uploader("Adicionar novos PDFs (os antigos permanecem)", type="pdf", accept_multiple_files=True)
jornada_disp = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

with st.sidebar.expander("🏖️ Registrar Folga"):
    c_folga = st.selectbox("Colaborador", EQUIPE_AUTOMACAO)
    d_ini = st.date_input("Início")
    d_fim = st.date_input("Fim")
    if st.button("Salvar Folga"):
        dias = (d_fim - d_ini).days + 1
        for i in range(dias):
            dia = d_ini + timedelta(days=i)
            st.session_state['folgas'].append({"Colaborador": c_folga, "Data": dia, "Mês": dia.strftime('%m - %B'), "HH_Folga": jornada_disp})
        st.success("Folga registrada!")

if st.sidebar.button("🗑️ RESET TOTAL (Apagar tudo)"):
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
                    h_idx = 0
                    for i, r in df_raw.iterrows():
                        if "supervisão" in " ".join(map(str, r)).lower():
                            h_idx = i; break
                    
                    df = df_raw.drop(range(h_idx + 1)).reset_index(drop=True)
                    df.columns = limpar_colunas(df_raw.iloc[h_idx])
                    
                    try:
                        col_sup = [c for c in df.columns if 'Supervisão' in c][0]
                        col_rec = [c for c in df.columns if 'recursos' in c.lower() or 'Nomes' in c][0]
                        col_dur = [c for c in df.columns if 'Duração' in c][0]
                        col_dat = [c for c in df.columns if any(x in c for x in ['Início', 'Data', 'Termino'])][0]

                        df_aut = df[df[col_sup].str.contains('Automação', case=False, na=False)].copy()
                        
                        dt_obj = datetime.now()
                        try: 
                            dt_s = re.search(r'\d{2}/\d{2}/\d{2}', str(df_aut[col_dat].iloc[0])).group()
                            dt_obj = datetime.strptime(dt_s, '%d/%m/%y')
                        except: pass

                        df_aut['HH_Val'] = df_aut[col_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
                        df_aut['Executante'] = df_aut[col_rec].str.split(';')
                        df_exp = df_aut.explode('Executante')
                        df_exp['Colaborador'] = df_exp['Executante'].apply(identificar_colaborador)
                        df_exp = df_exp.dropna(subset=['Colaborador'])
                        
                        df_exp['Data'] = dt_obj.date()
                        df_exp['Mês'] = dt_obj.strftime('%m - %B')
                        
                        st.session_state['db_pd'] = pd.concat([st.session_state['db_pd'], df_exp], ignore_index=True)
                        st.session_state['arquivos_processados'].append(file.name)
                    except Exception as e:
                        st.error(f"Erro no arquivo {file.name}: {e}")

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
        # 1. Total de dias (arquivos) carregados no período
        dias_no_periodo = df_m[df_m['Mês'].isin(sel_mes)]['Data'].nunique() if not df_m.empty else 0
        
        # 2. HH Programado
        if not df_m.empty:
            df_g = df_m[(df_m['Mês'].isin(sel_mes)) & (df_m['Colaborador'].isin(sel_col))]
            res_prog = df_g.groupby('Colaborador')['HH_Val'].sum().reset_index()
        else:
            res_prog = pd.DataFrame(columns=['Colaborador', 'HH_Val'])

        # 3. Cruzamento com a equipe total
        res_final = pd.DataFrame({'Colaborador': sel_col})
        res_final = res_final.merge(res_prog, on='Colaborador', how='left').fillna(0)
        
        # 4. Cálculo de Folgas (Prevenção do KeyError)
        if not df_f.empty:
            df_folga_mes = df_f[df_f['Mês'].isin(sel_mes)]
            if not df_folga_mes.empty:
                res_folga = df_folga_mes.groupby('Colaborador')['Data'].count().reset_index()
                res_folga.columns = ['Colaborador', 'Dias Folga']
                res_final = res_final.merge(res_folga, on='Colaborador', how='left').fillna(0)
            else:
                res_final['Dias Folga'] = 0
        else:
            res_final['Dias Folga'] = 0

        # 5. Métricas de Disponibilidade Real
        res_final['N° de dias computados'] = (dias_no_periodo - res_final['Dias Folga']).clip(lower=0)
        res_final['HH Disponível'] = res_final['N° de dias computados'] * jornada_disp
        res_final['HH Programado'] = res_final['HH_Val']
        res_final['Saldo HH'] = res_final['HH Disponível'] - res_final['HH Programado']
        res_final['% Carga'] = (res_final['HH Programado'] / res_final['HH Disponível'] * 100).fillna(0).round(1)

        m1, m2, m3 = st.columns(3)
        m1.metric("Dias no Período", int(dias_no_periodo))
        m2.metric("HH Total Disponível", f"{res_final['HH Disponível'].sum():.1f}h")
        m3.metric("HH Total Programado", f"{res_final['HH Programado'].sum():.1f}h")

        st.dataframe(res_final[['Colaborador', 'N° de dias computados', 'HH Disponível', 'HH Programado', 'Saldo HH', '% Carga']], use_container_width=True)

    with tab2:
        if not df_m.empty:
            df_dia_f = df_m[(df_m['Mês'].isin(sel_mes)) & (df_m['Colaborador'].isin(sel_col))]
            for d in sorted(df_dia_f['Data'].unique(), reverse=True):
                st.write(f"📅 **{d.strftime('%d/%m/%Y')}**")
                res_d = df_dia_f[df_dia_f['Data'] == d].groupby('Colaborador')['HH_Val'].sum().reset_index()
                
                # Base do dia com todos os colaboradores
                base_dia = pd.DataFrame({'Colaborador': sel_col})
                # Filtra quem está de folga hoje
                quem_folga = df_f[df_f['Data'] == d]['Colaborador'].tolist() if not df_f.empty else []
                
                res_d = base_dia.merge(res_d, on='Colaborador', how='left').fillna(0)
                res_d = res_d[~res_d['Colaborador'].isin(quem_folga)]
                
                res_d['HH Disponível'] = jornada_disp
                res_d['Saldo HH'] = jornada_disp - res_d['HH_Val']
                res_d['% Carga'] = (res_d['HH_Val'] / jornada_disp * 100).round(1)
                st.table(res_d[['Colaborador', 'HH Disponível', 'HH_Val', 'Saldo HH', '% Carga']])

    with tab3:
        if not df_f.empty:
            st.write("#### Ausências Registradas")
            st.dataframe(df_f[df_f['Mês'].isin(sel_mes)], use_container_width=True)
