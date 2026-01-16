import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime

st.set_page_config(page_title="Gestão de HH Automação", layout="wide")
st.title("📊 Gestão de Planejamento - Automação")

# --- Configurações na Sidebar ---
uploaded_files = st.sidebar.file_uploader("Suba os PDFs (SEM03, SEM04, etc)", type="pdf", accept_multiple_files=True)
jornada_disp = st.sidebar.number_input("Jornada Diária (HH)", value=8.0)

def normalizar_nome(nome):
    """Padroniza nomes para agrupar mesmo com variações (ex: Gilmar e Gilmar Patrício)"""
    if not nome: return "Indefinido"
    nome = str(nome).upper().strip()
    # Lista de nomes principais para garantir o agrupamento correto
    referencias = ["ALESSANDRO", "ANDRÉ P", "DIENIFER", "ELCIO", "EDILON", "GILMAR", "JOSÉ GERALDO", "SAMUELL"]
    for ref in referencias:
        if ref in nome:
            return ref
    return nome.split()[0] # Retorna o primeiro nome caso não esteja na lista

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
        df.columns = [str(c).replace('\n', ' ').strip() for c in df_raw.iloc[header_idx]]
        
        # Resolve colunas duplicadas
        cols = pd.Series(df.columns)
        for dup in cols[cols.duplicated()].unique():
            cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))]
        df.columns = cols
        return df

if uploaded_files:
    lista_geral = []
    
    for file in uploaded_files:
        df = processar_pdf(file)
        if not df.empty:
            # Identificação flexível de colunas
            col_sup = [c for c in df.columns if 'Supervisão' in c][0]
            col_rec = [c for c in df.columns if 'recursos' in c.lower()][0]
            col_dur = [c for c in df.columns if 'Duração' in c][0]
            col_data = [c for c in df.columns if 'Início' in c or 'Termino' in c or 'Data' in c][0]

            # Filtro Automação
            df_aut = df[df[col_sup].str.contains('Automação', case=False, na=False)].copy()
            
            # Extração de Data para Filtros
            sample_date = str(df_aut[col_data].iloc[0]) if not df_aut.empty else ""
            data_obj = datetime.now() # Fallback
            if "/" in sample_date:
                try:
                    data_str = re.search(r'\d{2}/\d{2}/\d{2}', sample_date).group()
                    data_obj = datetime.strptime(data_str, '%d/%m/%y')
                except: pass

            # Processamento de HH e Executantes
            df_aut['HH_Prog'] = df_aut[col_dur].apply(lambda x: int(re.findall(r'\d+', str(x))[0])/60 if re.findall(r'\d+', str(x)) else 0)
            df_aut['Executante_Bruto'] = df_aut[col_rec].str.split(';')
            df_exploded = df_aut.explode('Executante_Bruto')
            df_exploded['Colaborador'] = df_exploded['Executante_Bruto'].apply(normalizar_nome)
            
            df_exploded['Mês'] = data_obj.strftime('%m - %B')
            df_exploded['Ano'] = data_obj.year
            df_exploded['Arquivo'] = file.name
            
            lista_geral.append(df_exploded)

    if lista_geral:
        df_master = pd.concat(lista_geral)
        
        # --- FILTROS NO TOPO ---
        st.write("### 🔍 Filtros")
        col_f1, col_f2 = st.columns(2)
        meses = sorted(df_master['Mês'].unique())
        mes_sel = col_f1.multiselect("Filtrar por Mês", meses, default=meses)
        colaboradores = sorted(df_master['Colaborador'].unique())
        colab_sel = col_f2.multiselect("Filtrar por Colaborador", colaboradores, default=colaboradores)
        
        df_filt = df_master[(df_master['Mês'].isin(mes_sel)) & (df_master['Colaborador'].isin(colab_sel))]

        tab1, tab2 = st.tabs(["🌎 Relatório Geral Acumulado", "📅 Detalhamento por Dia"])

        with tab1:
            # Agrupamento Geral
            # Calculando número de dias (arquivos únicos) por pessoa
            dias_por_pessoa = df_filt.groupby('Colaborador')['Arquivo'].nunique()
            hh_prog_pessoa = df_filt.groupby('Colaborador')['HH_Prog'].sum()
            
            resumo_geral = pd.DataFrame({
                'N° de dias computadados': dias_por_pessoa,
                'HH Programado': hh_prog_pessoa
            }).reset_index()
            
            resumo_geral['HH Disponível'] = resumo_geral['N° de dias computadados'] * jornada_disp
            resumo_geral['Saldo HH'] = resumo_geral['HH Disponível'] - resumo_geral['HH Programado']
            resumo_geral['% Carga'] = (resumo_geral['HH Programado'] / resumo_geral['HH Disponível'] * 100).round(1)
            
            # Reordenando conforme solicitado
            resumo_geral = resumo_geral[['Colaborador', 'N° de dias computadados', 'HH Disponível', 'HH Programado', 'Saldo HH', '% Carga']]
            
            st.write(f"#### Consolidado Anual {df_filt['Ano'].unique()}")
            st.dataframe(resumo_geral.style.format({'HH Programado': '{:.1f}', 'HH Disponível': '{:.1f}', 'Saldo HH': '{:.1f}', '% Carga': '{:.1f}%'}))
            
            st.metric("HH Total da Equipe (Programado)", f"{resumo_geral['HH Programado'].sum():.1f}h")

        with tab2:
            for dia in df_filt['Arquivo'].unique():
                df_dia = df_filt[df_filt['Arquivo'] == dia]
                st.write(f"---")
                st.write(f"📂 **Arquivo/Dia:** {dia}")
                
                resumo_dia = df_dia.groupby('Colaborador')['HH_Prog'].sum().reset_index()
                resumo_dia['HH Disponível'] = jornada_disp
                resumo_dia['Saldo HH'] = resumo_dia['HH Disponível'] - resumo_dia['HH_Prog']
                resumo_dia['% Carga'] = (resumo_dia['HH_Prog'] / resumo_dia['HH Disponível'] * 100).round(1)
                
                # Reordenando colunas do dia
                resumo_dia = resumo_dia[['Colaborador', 'HH Disponível', 'HH_Prog', 'Saldo HH', '% Carga']]
                
                st.table(resumo_dia)
                
                col_d1, col_d2 = st.columns(2)
                col_d1.write(f"**Soma HH Programado no dia:** {resumo_dia['HH_Prog'].sum():.1f}h")
                col_d2.write(f"**Soma HH Disponível no dia:** {resumo_dia['HH Disponível'].sum():.1f}h")
