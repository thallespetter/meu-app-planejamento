import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="Gestão de HH - Automação", layout="wide")

st.title("📊 Calculador de HH - Planejamento")
st.sidebar.header("Configurações")

# Upload do arquivo
uploaded_file = st.sidebar.file_uploader("Suba o PDF original da programação", type="pdf")

# Parâmetros Fixos
DISCIPLINA_ALVO = "Automação"
JORNADA_DISPONIVEL = 8.0 # 07:00 às 16:00 (com 1h de almoço)

if uploaded_file:
    with pdfplumber.open(uploaded_file) as pdf:
        all_data = []
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                # O cabeçalho geralmente está na primeira linha da primeira página
                all_data.extend(table)
        
        # Criar DataFrame (ajustando colunas conforme suas imagens)
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        
        # Limpeza de dados nulos
        df = df.dropna(subset=['Supervisão', 'Duração', 'Nomes dos recursos'])
        
        # 1. Filtrar apenas Automação
        df_aut = df[df['Supervisão'].str.contains(DISCIPLINA_ALVO, case=False)].copy()

        # 2. Função para converter "480 mins" ou "120" em horas decimais
        def converter_min_em_hh(tempo_str):
            numeros = re.findall(r'\d+', str(tempo_str))
            if numeros:
                return int(numeros[0]) / 60
            return 0.0

        # 3. Tratamento de múltiplos executantes (Separados por ;)
        df_aut['Executante'] = df_aut['Nomes dos recursos'].str.split(';')
        df_exploded = df_aut.explode('Executante')
        df_exploded['Executante'] = df_exploded['Executante'].str.strip()
        
        # Aplicar conversão de tempo
        df_exploded['HH_Programado'] = df_exploded['Duração'].apply(converter_min_em_hh)

        # 4. Agrupamento e Cálculos
        resumo = df_exploded.groupby('Executante')['HH_Programado'].sum().reset_index()
        resumo['HH_Disponível'] = JORNADA_DISPONIVEL
        resumo['Saldo_HH'] = resumo['HH_Disponível'] - resumo['HH_Programado']
        resumo['Ocupação_%'] = (resumo['HH_Programado'] / resumo['HH_Disponível'] * 100).round(1)

        # Exibição dos Resultados
        st.header(f"Resultados: Disciplina {DISCIPLINA_ALVO}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total HH Planejado", f"{resumo['HH_Programado'].sum():.1f}h")
        col2.metric("Total HH Disponível", f"{resumo['HH_Disponível'].sum():.1f}h")
        col3.metric("Saldo Equipe", f"{resumo['Saldo_HH'].sum():.1f}h")

        st.subheader("Detalhamento por Colaborador")
        st.dataframe(resumo.style.format({'HH_Programado': '{:.2f}', 'Saldo_HH': '{:.2f}', 'Ocupação_%': '{:.1f}%'}))
        
        # Gráfico de Barras
        st.bar_chart(resumo.set_index('Executante')['HH_Programado'])

else:
    st.info("Aguardando upload do PDF original para processar os dados de Automação.")
