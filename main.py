import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Gestão de HH - Automação", layout="wide")
st.title("📊 Painel de Planejamento - Automação")

# Sidebar para Upload e Configurações
st.sidebar.header("Configurações")
uploaded_files = st.sidebar.file_uploader("Suba um ou mais PDFs de programação", type="pdf", accept_multiple_files=True)
jornada_disponivel = st.sidebar.number_input("HH Disponível por Colaborador", value=8.0)

def processar_pdf(file):
    with pdfplumber.open(file) as pdf:
        all_rows = []
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                all_rows.extend(table)
        
        if not all_rows:
            return pd.DataFrame()

        df_raw = pd.DataFrame(all_rows)
        
        # Localiza a linha do cabeçalho procurando por palavras-chave conhecidas
        header_row_idx = None
        for i, row in df_raw.iterrows():
            row_str = " ".join([str(x) for x in row.values if x]).lower()
            if "supervisão" in row_str or "nomes dos recursos" in row_str:
                header_row_idx = i
                break
        
        if header_row_idx is None:
            return pd.DataFrame()

        # Define cabeçalhos e limpa o DataFrame
        df_raw.columns = df_raw.iloc[header_row_idx]
        df = df_raw.drop(range(header_row_idx + 1)).reset_index(drop=True)
        
        # Padroniza nomes das colunas (remove espaços e quebras de linha)
        df.columns = [str(c).replace('\n', ' ').strip() for c in df.columns]
        
        return df

if uploaded_files:
    lista_dfs = []
    
    for file in uploaded_files:
        df_extraido = processar_pdf(file)
        if not df_extraido.empty:
            # Adiciona o nome do arquivo/dia para referência
            df_extraido['Arquivo_Origem'] = file.name
            lista_dfs.append(df_extraido)
    
    if lista_dfs:
        df_total = pd.concat(lista_dfs, ignore_index=True)
        
        # Filtro de Automação (flexível para variações de escrita)
        col_supervisao = [c for c in df_total.columns if 'Supervisão' in c]
        if col_supervisao:
            df_aut = df_total[df_total[col_supervisao[0]].str.contains('Automação', case=False, na=False)].copy()
            
            # Tratamento de Duração (Extrai números de "480 mins")
            def limpar_hh(valor):
                nums = re.findall(r'\d+', str(valor))
                return int(nums[0]) / 60 if nums else 0.0

            # Tratamento de Executantes (Explode nomes separados por ;)
            col_recursos = [c for c in df_total.columns if 'recursos' in c.lower()][0]
            df_aut['Executante'] = df_aut[col_recursos].str.split(';')
            df_exploded = df_aut.explode('Executante')
            df_exploded['Executante'] = df_exploded['Executante'].str.strip()
            
            col_duracao = [c for c in df_total.columns if 'Duração' in c][0]
            df_exploded['HH_Prog'] = df_exploded[col_duracao].apply(limpar_hh)

            # --- RESULTADOS ---
            tab1, tab2 = st.tabs(["📊 Visão Geral da Equipe", "📅 Detalhado por Dia"])

            with tab1:
                st.subheader("HH Total Acumulado (Todos os arquivos)")
                resumo_geral = df_exploded.groupby('Executante')['HH_Prog'].sum().reset_index()
                resumo_geral['HH_Disponível Total'] = len(uploaded_files) * jornada_disponivel
                resumo_geral['Saldo'] = resumo_geral['HH_Disponível Total'] - resumo_geral['HH_Prog']
                st.dataframe(resumo_geral.style.format({'HH_Prog': '{:.1f}', 'Saldo': '{:.1f}'}))
                st.bar_chart(resumo_geral.set_index('Executante')['HH_Prog'])

            with tab2:
                for dia in df_exploded['Arquivo_Origem'].unique():
                    st.write(f"### Arquivo: {dia}")
                    df_dia = df_exploded[df_exploded['Arquivo_Origem'] == dia]
                    resumo_dia = df_dia.groupby('Executante')['HH_Prog'].sum().reset_index()
                    resumo_dia['Status'] = resumo_dia['HH_Prog'].apply(lambda x: "⚠️ Sobrecarga" if x > jornada_disponivel else "✅ OK")
                    st.table(resumo_dia)
        else:
            st.error("Não foi possível encontrar a coluna 'Supervisão' nos arquivos.")
    else:
        st.warning("Nenhum dado válido encontrado nos arquivos carregados.")
            
