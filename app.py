import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import math

st.set_page_config(page_title="Telemetria Sumaresat", layout="wide")
st.title("Painel de Telemetria e Georreferenciamento")

# --- MOTOR MATEMÁTICO: GEOFENCING ---
def calcular_perimetro_raio(lat, lon, raio_m):
    raio_terra = 6378137.0 
    pontos_lat = []
    pontos_lon = []
    for angulo in range(0, 361, 10):
        rad = math.radians(angulo)
        lat_offset = (raio_m / raio_terra) * (180 / math.pi) * math.cos(rad)
        lon_offset = (raio_m / (raio_terra * math.cos(math.pi * lat / 180))) * (180 / math.pi) * math.sin(rad)
        pontos_lat.append(lat + lat_offset)
        pontos_lon.append(lon + lon_offset)
    return pontos_lat, pontos_lon

# Inicializa locais na memória
if 'locais' not in st.session_state:
    st.session_state.locais = []

# --- PAINEL LATERAL: UPLOAD E CONTROLES ---
with st.sidebar:
    st.header("📂 Ingestão de Dados")
    # A Mágica do Upload: Lê os arquivos direto do navegador do usuário
    arquivos_up = st.file_uploader("Arraste os relatórios do Sumaresat aqui", type=['csv', 'xls', 'xlsx'], accept_multiple_files=True)

# --- MOTOR DE PROCESSAMENTO EM MEMÓRIA ---
@st.cache_data
def processar_arquivos(arquivos_carregados):
    if not arquivos_carregados:
        return pd.DataFrame()

    lista_df = []
    for arquivo in arquivos_carregados:
        try:
            if arquivo.name.lower().endswith('.xlsx') or arquivo.name.lower().endswith('.xls'):
                try:
                    df_temp = pd.read_excel(arquivo, engine='calamine')
                except Exception:
                    try:
                        tabelas = pd.read_html(arquivo, decimal=',', thousands='.')
                        df_temp = tabelas[0]
                    except Exception as e_interno:
                        st.sidebar.error(f"Erro ao ler {arquivo.name}")
                        continue
            else:
                df_temp = pd.read_csv(arquivo, sep=';', encoding='latin1', on_bad_lines='skip')
                
            lista_df.append(df_temp)
        except Exception as e:
            st.sidebar.error(f"Falha no arquivo {arquivo.name}: {e}")
            
    if not lista_df:
        return pd.DataFrame()
        
    df = pd.concat(lista_df, ignore_index=True)
    df.rename(columns=lambda x: str(x).strip(), inplace=True)
    
    colunas_map = {'Rótulo': 'Placa', 'Data': 'DataHora', 'Vel.': 'Velocidade', 'Latitude': 'Latitude', 'Longitude': 'Longitude'}
    df = df.rename(columns=colunas_map)
    
    if 'DataHora' not in df.columns:
        return pd.DataFrame() # Falha silenciosa controlada se o arquivo for lixo
    
    df['DataHora'] = pd.to_datetime(df['DataHora'], dayfirst=True, errors='coerce')
    for col in ['Latitude', 'Longitude', 'Velocidade']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df = df.dropna(subset=['DataHora', 'Latitude', 'Longitude'])
    df = df[(df['Latitude'] != 0) & (df['Longitude'] != 0)]
    
    df['Dia_Semana'] = df['DataHora'].dt.dayofweek
    df['Nome_Dia'] = df['DataHora'].dt.day_name(locale='pt_BR.utf8').str.capitalize() # Tenta PT-BR, fallback para inglês
    df['Hora_Int'] = df['DataHora'].dt.hour
    df['Infracao_Velocidade'] = df['Velocidade'] > 115
    df['Fora_Expediente'] = (df['Hora_Int'] < 5) | (df['Hora_Int'] >= 19) | (df['Dia_Semana'] > 4)
    
    return df.sort_values('DataHora')

# Executa o processamento
df_frota = processar_arquivos(arquivos_up)

if df_frota.empty:
    st.info("👈 Por favor, faça o upload de pelo menos um relatório do Sumaresat no menu lateral para iniciar o sistema.")
    st.stop()

if 'Placa' not in df_frota.columns:
    df_frota['Placa'] = 'Equipamento Único'

# --- CONTINUAÇÃO DO PAINEL LATERAL ---
with st.sidebar:
    st.markdown("---")
    st.header("⚙️ Painel de Controle")
    veiculo_selecionado = st.selectbox("Selecione o Equipamento", df_frota['Placa'].unique().tolist())
    
    st.markdown("---")
    st.subheader("📅 Filtros de Tempo")
    
    # Filtro 1: Calendário (Range de Datas)
    min_data = df_frota['DataHora'].dt.date.min()
    max_data = df_frota['DataHora'].dt.date.max()
    datas_selecionadas = st.date_input("Período de Análise", [min_data, max_data], min_value=min_data, max_value=max_data)
    
    # Filtro 2: Dias da Semana
    dias_disponiveis = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dias_nomes_br = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    dias_selecionados = st.multiselect("Dias da Semana", dias_nomes_br, default=dias_nomes_br)
    
    st.markdown("---")
    st.subheader("📍 Frentes de Obra e Locais")
    
    with st.expander("➕ Adicionar Novo Local", expanded=False):
        novo_nome = st.text_input("Nome da Obra/Local")
        col_coord1, col_coord2 = st.columns(2)
        nova_lat = col_coord1.number_input("Latitude", format="%.6f")
        nova_lon = col_coord2.number_input("Longitude", format="%.6f")
        novo_raio = st.number_input("Raio da Cerca (Metros)", min_value=10, value=50, step=10)
        nova_cor = st.color_picker("Cor do Marcador", "#1E90FF")
        
        if st.button("Salvar Local", use_container_width=True):
            if novo_nome and nova_lat != 0 and nova_lon != 0:
                st.session_state.locais.append({
                    "nome": novo_nome, "lat": nova_lat, "lon": nova_lon, "raio": novo_raio, "cor": nova_cor
                })
                st.rerun()
            else:
                st.error("Preencha Nome e Coordenadas.")

    if st.session_state.locais:
        st.markdown("**Locais Ativos:**")
        for i, local in enumerate(st.session_state.locais):
            col_info, col_btn = st.columns([5, 1])
            col_info.markdown(f"<span style='color:{local['cor']}; font-size:18px;'>⬤</span> **{local['nome']}** <br> <small>Raio: {local['raio']}m</small>", unsafe_allow_html=True)
            if col_btn.button("❌", key=f"del_{i}"):
                st.session_state.locais.pop(i)
                st.rerun()
            st.markdown("---")
            
    st.subheader("🚦 Filtros Operacionais")
    mostrar_apenas_infracoes = st.checkbox("Excesso de velocidade (>115 km/h)")
    mostrar_apenas_fora_hora = st.checkbox("Rodagem fora do expediente/FDS")
    
    st.markdown("---")
    if st.button("🖨️ Gerar Relatório PDF", use_container_width=True):
        st.components.v1.html("<script>window.print()</script>", height=0)

# --- APLICAÇÃO DOS FILTROS ---
df_veiculo = df_frota[df_frota['Placa'] == veiculo_selecionado].copy()

# Aplica o filtro do calendário (lida com o fato de o usuário escolher só 1 dia ou um range)
if len(datas_selecionadas) == 2:
    start_date, end_date = datas_selecionadas
    df_veiculo = df_veiculo[(df_veiculo['DataHora'].dt.date >= start_date) & (df_veiculo['DataHora'].dt.date <= end_date)]
elif len(datas_selecionadas) == 1:
    start_date = datas_selecionadas[0]
    df_veiculo = df_veiculo[df_veiculo['DataHora'].dt.date == start_date]

# Aplica o filtro de dias da semana convertendo a escolha em BR para os índices numéricos
indices_dias = [dias_nomes_br.index(dia) for dia in dias_selecionados]
df_veiculo = df_veiculo[df_veiculo['Dia_Semana'].isin(indices_dias)]

if mostrar_apenas_infracoes:
    df_veiculo = df_veiculo[df_veiculo['Infracao_Velocidade'] == True]
if mostrar_apenas_fora_hora:
    df_veiculo = df_veiculo[df_veiculo['Fora_Expediente'] == True]

# --- RENDERIZAÇÃO PRINCIPAL ---
st.subheader(f"Análise de Rota: {veiculo_selecionado}")

col1, col2, col3 = st.columns(3)
# Proteção contra dataframe vazio após os filtros
vel_max = df_veiculo['Velocidade'].max() if not df_veiculo.empty else 0
inf_sum = df_veiculo['Infracao_Velocidade'].sum() if not df_veiculo.empty else 0
fora_sum = df_veiculo['Fora_Expediente'].sum() if not df_veiculo.empty else 0

col1.metric("Velocidade Máxima Registrada", f"{vel_max} km/h")
col2.metric("Ocorrências > 115 km/h", inf_sum)
col3.metric("Ocorrências Fora do Expediente", fora_sum)

if not df_veiculo.empty:
    fig_mapa = go.Figure()

    fig_mapa.add_trace(go.Scattermapbox(
        lat=df_veiculo['Latitude'], lon=df_veiculo['Longitude'],
        mode='lines', line=dict(width=2, color='rgba(100, 100, 100, 0.5)'),
        hoverinfo='skip', name='Trajeto'
    ))

    for local in st.session_state.locais:
        perim_lat, perim_lon = calcular_perimetro_raio(local['lat'], local['lon'], local['raio'])
        fig_mapa.add_trace(go.Scattermapbox(
            lat=perim_lat, lon=perim_lon,
            mode='lines', fill='toself', fillcolor=local['cor'], opacity=0.4,
            line=dict(color=local['cor'], width=1),
            text=f"{local['nome']} (Raio: {local['raio']}m)", hoverinfo='text', name=local['nome']
        ))
        fig_mapa.add_trace(go.Scattermapbox(
            lat=[local['lat']], lon=[local['lon']],
            mode='markers+text', marker=dict(size=10, color=local['cor'], symbol='marker'),
            text=[local['nome']], textposition="bottom center",
            hoverinfo='skip', showlegend=False
        ))

    fig_mapa.add_trace(go.Scattermapbox(
        lat=df_veiculo['Latitude'], lon=df_veiculo['Longitude'],
        mode='markers',
        marker=dict(size=7, color=df_veiculo['Velocidade'], colorscale='RdYlGn_r', cmin=0, cmax=115, showscale=True, colorbar=dict(title="km/h")),
        text=df_veiculo['DataHora'].dt.strftime('%d/%m/%Y %H:%M:%S') + '<br>Vel: ' + df_veiculo['Velocidade'].astype(str) + ' km/h',
        hoverinfo='text', name='Registro GPS'
    ))

    fig_mapa.update_layout(
        mapbox_style="carto-positron", mapbox_zoom=13,
        mapbox_center={"lat": df_veiculo['Latitude'].mean(), "lon": df_veiculo['Longitude'].mean()},
        margin={"r":0,"t":0,"l":0,"b":0}, showlegend=False
    )
    st.plotly_chart(fig_mapa, use_container_width=True)
    
    st.subheader("Perfil Cinemático de Velocidade")
    fig_linha = px.line(df_veiculo, x='DataHora', y='Velocidade', template="plotly_white")
    fig_linha.add_hline(y=115, line_dash="dash", line_color="red", annotation_text="Limite de Segurança (115 km/h)")
    st.plotly_chart(fig_linha, use_container_width=True)
else:
    st.info("Nenhum dado encontrado para exibir. Verifique os filtros de data e equipamento selecionados.")
