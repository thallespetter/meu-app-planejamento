import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Gestão de HH - Automação", layout="wide")
st.title("📊 Painel de Planejamento - Automação")

uploaded_files = st.sidebar.file_uploader("Suba um ou mais PDFs", type="pdf", accept_multiple_files=True)
jornada_disp = st.sidebar.number_input("HH Disponível p/ dia", value=8.0)

def limpar_colunas_duplicadas(df):
    # Remove colunas com nomes repetidos que causam o erro ValueError
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
    return df

def processar_pdf(file):
    with pdfplumber.open(file) as pdf:
        all_rows = []
        for page in pdf.pages:
            table = page.extract_table()
            if table: all_rows.extend(table)
        
        if not all_rows: return pd.DataFrame()
        
        df_raw = pd.DataFrame(all_rows)
        
        # Localiza o cabeçalho real
        header_idx = None
        for i, row in df_raw.iterrows():
            row_str = " ".join([str(x) for x in row.values if x]).lower()
            if "supervisão" in row_str or "recursos" in row_str:
                header_idx = i
                break
        
        if header_idx is None: return pd.DataFrame()
        
        df = df_raw.drop(range(header_idx + 1)).reset_index(drop=True)
        df.columns = [str(c).replace('\n', ' ').strip() for c in df_raw.iloc[header_idx]]
        
        # CORREÇÃO DO ERRO: Remove duplicatas de nomes de colunas
        df = limpar_colunas_duplicadas(df)
        return df

if uploaded_files:
    dados_acumulados = []
    
    for file in uploaded_files:
        df = processar_pdf(file)
        if not df.empty:
            # Identifica as colunas principais de forma flexível
            col_sup = [c for c in df.columns if 'Supervisão' in c][0]
            col_rec = [c for c in df.columns if 'recursos' in c.lower()][0]
            col_dur = [c for c in df.columns if 'Duração' in c][0]
            
            # Filtra Automação
            df_aut = df[df[col_sup].str.contains('Automação', case=False, na=False)].copy()
            
            # Limpa HH e Nomes
            df_aut['HH_Prog'] = df_aut[col_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
            df_aut['Executante'] = df_aut[col_rec].str.split(';')
            df_exploded = df_aut.explode('Executante')
            df_exploded['Executante'] = df_exploded['Executante'].str.strip()
            df_exploded['Dia'] = file.name
            
            dados_acumulados.append(df_exploded[['Executante', 'HH_Prog', 'Dia']])

    if dados_acumulados:
        df_final = pd.concat(dados_acumulados)
        
        tab1, tab2 = st.tabs(["👥 Geral da Equipe", "📅 Por Dia"])
        
        with tab1:
            geral = df_final.groupby('Executante')['HH_Prog'].sum().reset_index()
            geral['HH Disponível'] = len(uploaded_files) * jornada_disp
            geral['Saldo'] = geral['HH Disponível'] - geral['HH_Prog']
            st.write("### Acumulado de todos os dias selecionados")
            st.dataframe(geral.style.format({'HH_Prog': '{:.1f}', 'Saldo': '{:.1f}'}))
            st.bar_chart(geral.set_index('Executante')['HH_Prog'])

        with tab2:
            for dia in df_final['Dia'].unique():
                st.write(f"#### Arquivo: {dia}")
                resumo_dia = df_final[df_final['Dia'] == dia].groupby('Executante')['HH_Prog'].sum().reset_index()
                resumo_dia['Carga %'] = (resumo_dia['HH_Prog'] / jornada_disp * 100).round(1)
                st.table(resumo_dia)
            
