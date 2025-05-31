import sys
import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(SCRIPT_DIR, "..")))
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.converters import convertir_numero
from analysis.predictor import generate_predictions # Importar función de predicción

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(
    page_title="Instagram Analyzer Dashboard",
    page_icon="📱",
    layout="wide"
)

st.markdown("""
    <style>
        /* Cambiar el color de fondo principal de la aplicación */
        .stApp {
            background-color: #691C32; /* Puedes usar cualquier color CSS válido */
        }
        .big-font {
            font-size:32px !important;
            font-weight: bold;
        }
        .metric-label {
            font-size:18px;
            color: #777;
        }
        .block-container {
            padding-top: 2.5rem; /* Aumentado para bajar el contenido */
        }
        /* Si el color anterior no afecta a todo, puedes probar con el body */
        /* body {
            background-color: #f0f2f6 !important;
        } */
    </style>
""", unsafe_allow_html=True)

# --- LOGO ---
# Asegúrate de que la ruta al logo sea correcta.
# Si creaste una carpeta 'assets' dentro de 'dashboard':
LOGO_PATH = os.path.join(SCRIPT_DIR,"assets","LOGO.png")
if os.path.exists(LOGO_PATH):
    st.image(LOGO_PATH,width=150) # Puedes ajustar el 'width' según necesites, ej: 400

# --- TÍTULO ---
st.markdown("<div class='big-font'>📊 Instagram Analyzer: Actividad y Anomalías</div>", unsafe_allow_html=True)
st.markdown("Análisis visual de perfiles públicos: publicaciones, seguidores y seguidos.")

# --- RUTA A LA BASE DE DATOS ---
DB_PATH = os.path.join(SCRIPT_DIR, "..", "data", "analisis_instagram.db")

# --- CARGA DE DATOS ---
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT id, usuario, fecha, publicaciones, seguidores, seguidos, anomalia_descripcion FROM estadisticas", conn)
conn.close()

df["publicaciones"] = df["publicaciones"].apply(convertir_numero)
df["seguidores"] = df["seguidores"].apply(convertir_numero)
df["seguidos"] = df["seguidos"].apply(convertir_numero)

df["fecha"] = pd.to_datetime(df["fecha"])
df_latest = df.sort_values("fecha").groupby("usuario").tail(1)
if df.empty:
    st.warning("⚠️ No hay datos en la base de datos. Ejecuta el scraper primero.")
    st.stop()

# --- SIDEBAR ---
st.sidebar.header("⚙️ Filtros Principales") # Encabezado mejorado con icono

available_users = df_latest["usuario"].unique()
usuario = None # Inicializar usuario

if not available_users.any():
    st.sidebar.warning("No hay perfiles con datos para analizar.")
    # El script principal se detendrá si no hay 'usuario'
else:
    usuario = st.sidebar.selectbox(
        "👤 Selecciona un perfil", # Etiqueta con icono
        available_users,
        index=0 if len(available_users) > 0 else None, # Seleccionar el primero por defecto
        key="sb_select_user"
    )

# Inicializar DataFrames para evitar errores si no hay datos
perfil_df = pd.DataFrame() # DataFrame con todos los datos del usuario seleccionado
perfil_df_filtered = pd.DataFrame() # DataFrame filtrado por fecha para gráficas

if usuario:
    # Cargar todos los datos para el usuario seleccionado
    perfil_df = df[df["usuario"] == usuario].sort_values("fecha")

    if not perfil_df.empty:
        # Calcular Ratio Seguidores/Seguidos para el DataFrame completo del perfil
        perfil_df["ratio_seguidores_seguidos"] = perfil_df.apply(
            lambda row: row["seguidores"] / row["seguidos"] if row["seguidos"] > 0 else 0, axis=1
        )

        # --- FILTRO DE RANGO DE FECHAS (MOVIDO A LA SIDEBAR) ---
        st.sidebar.markdown("---") # Separador visual
        st.sidebar.markdown("#### 📅 Rango de Fechas para Gráficas")

        min_date_profile = perfil_df["fecha"].min().date()
        max_date_profile = perfil_df["fecha"].max().date()

        if len(perfil_df) < 2 or min_date_profile == max_date_profile:
            st.sidebar.info("Mostrando todos los datos (rango no aplicable).")
            perfil_df_filtered = perfil_df # Usar todos los datos si no hay rango suficiente
        else:
            date_range_val = st.sidebar.date_input(
                "Selecciona el rango:",
                (min_date_profile, max_date_profile),
                min_value=min_date_profile,
                max_value=max_date_profile,
                key=f"sidebar_date_range_{usuario}" # Clave única por usuario
            )
            if date_range_val and len(date_range_val) == 2:
                start_date_dt = pd.to_datetime(date_range_val[0])
                end_date_dt = pd.to_datetime(date_range_val[1]).replace(hour=23, minute=59, second=59) # Incluir todo el día final
                perfil_df_filtered = perfil_df[
                    (perfil_df["fecha"] >= start_date_dt) & (perfil_df["fecha"] <= end_date_dt)
                ]
            else:
                # Si el rango no está completamente definido, mostrar todos los datos del perfil
                perfil_df_filtered = perfil_df
    else: # perfil_df está vacío para el usuario seleccionado
        perfil_df_filtered = perfil_df # También será un DataFrame vacío
else:
    # No hay usuario seleccionado (sucede si available_users estaba vacío)
    # perfil_df y perfil_df_filtered permanecen como DataFrames vacíos
    pass

# --- VALIDACIONES PRINCIPALES (DESPUÉS DE PROCESAR SIDEBAR) ---
if usuario is None:
    st.error("No hay perfiles disponibles en la base de datos para analizar. Ejecuta el scraper primero.")
    st.stop()

if perfil_df.empty: # Esto significa que el 'usuario' seleccionado no tiene datos
    st.warning(f"⚠️ No hay datos históricos para el perfil **{usuario}**.")
    st.stop()

# --- PESTAÑAS PRINCIPALES ---
tab_dashboard, tab_ciberseguridad = st.tabs(["📊 Dashboard Principal", "🛡️ Ciberseguridad y Ayuda"])

with tab_dashboard:
    # --- KPIs Y CAMBIOS ---
    # Esta sección ahora usa 'perfil_df' que contiene todos los datos del usuario seleccionado
    st.markdown(f"### 📌 Últimos datos y cambios para: {usuario}")
    latest_data = perfil_df.iloc[-1]
    previous_data = perfil_df.iloc[-2] if len(perfil_df) > 1 else None

    col1, col2, col3, col4 = st.columns(4)

    pub_delta = int(latest_data["publicaciones"] - previous_data["publicaciones"]) if previous_data is not None else None
    seg_delta = int(latest_data["seguidores"] - previous_data["seguidores"]) if previous_data is not None else None
    segdos_delta = int(latest_data["seguidos"] - previous_data["seguidos"]) if previous_data is not None else None
    ratio_actual = latest_data["ratio_seguidores_seguidos"]
    ratio_anterior = previous_data["ratio_seguidores_seguidos"] if previous_data is not None else None
    ratio_delta = (ratio_actual - ratio_anterior) if previous_data is not None else None

    col1.metric("Publicaciones", int(latest_data["publicaciones"]), delta=pub_delta, delta_color="normal" if pub_delta is None else ("inverse" if pub_delta < 0 else "normal"))
    col2.metric("Seguidores", int(latest_data["seguidores"]), delta=seg_delta, delta_color="normal" if seg_delta is None else ("inverse" if seg_delta < 0 else "normal"))
    col3.metric("Seguidos", int(latest_data["seguidos"]), delta=segdos_delta, delta_color="normal" if segdos_delta is None else ("inverse" if segdos_delta < 0 else "normal"))
    col4.metric("Ratio Sgs/Sdos", f"{ratio_actual:.2f}", delta=f"{ratio_delta:.2f}" if ratio_delta is not None else None, delta_color="normal" if ratio_delta is None else ("inverse" if ratio_delta < 0 else "normal"))


    # --- GRÁFICAS ---
    # Esta sección ahora usa 'perfil_df_filtered' que es el DataFrame filtrado por fecha desde la sidebar
    if not perfil_df_filtered.empty and len(perfil_df_filtered) > 1:
        st.markdown(f"### 📈 Evolución histórica para {usuario}")

        metrics_to_plot = ["publicaciones", "seguidores", "seguidos", "ratio_seguidores_seguidos"]
        ylabels = ["Nº Publicaciones", "Nº Seguidores", "Nº Seguidos", "Ratio Sgs/Sdos"]
        subplot_titles = [f"Evolución de {m.replace('_', ' ').capitalize()}" for m in metrics_to_plot]

        fig_evolution = make_subplots(
            rows=len(metrics_to_plot),
            cols=1,
            shared_xaxes=True,
            subplot_titles=subplot_titles,
            vertical_spacing=0.08 # Ajusta según sea necesario
        )

        for i, metric in enumerate(metrics_to_plot):
            # Línea principal de la métrica
            fig_evolution.add_trace(
                go.Scatter(x=perfil_df_filtered["fecha"], y=perfil_df_filtered[metric],
                           mode='lines+markers', name=ylabels[i],
                           hovertemplate ='<b>Fecha</b>: %{x|%Y-%m-%d}<br><b>'+ ylabels[i] +'</b>: %{y:.2f}<extra></extra>'), # Plantilla de hover personalizada
                row=i+1, col=1
            )

            # Añadir predicciones para 'seguidores'
            if metric == "seguidores" and not perfil_df_filtered.empty:
                historical_series_for_pred = perfil_df_filtered.set_index('fecha')[metric].sort_index()
                if len(historical_series_for_pred) >= 10:
                    predicted_values = generate_predictions(historical_series_for_pred, n_future_steps=7) # sequence_length ya no es necesario
                    if not predicted_values.empty:
                        fig_evolution.add_trace(
                            go.Scatter(x=predicted_values.index, y=predicted_values.values,
                                       mode='lines+markers', name='Predicción Seguidores',
                                       line=dict(dash='dash', color='rgba(0,191,255,0.8)'), # Dodgerblue con transparencia
                                       hovertemplate ='<b>Fecha Pred.</b>: %{x|%Y-%m-%d}<br><b>Seg. Predichos</b>: %{y:.0f}<extra></extra>'),
                            row=i+1, col=1
                        )

            # Marcar anomalías
            anomalies_df = perfil_df_filtered[perfil_df_filtered['anomalia_descripcion'].notna()]
            if not anomalies_df.empty:
                fig_evolution.add_trace(
                    go.Scatter(x=anomalies_df['fecha'], y=anomalies_df[metric],
                               mode='markers', name='Anomalía',
                               marker=dict(color='red', size=10, symbol='x'),
                               customdata=anomalies_df['anomalia_descripcion'], # Para mostrar en hover
                               hovertemplate ='<b>Fecha</b>: %{x|%Y-%m-%d}<br><b>Valor</b>: %{y:.2f}<br><b>Anomalía</b>: %{customdata}<extra></extra>'),
                    row=i+1, col=1
                )
            # Actualizar el título del eje Y para cada subplot
            fig_evolution.update_yaxes(title_text=ylabels[i], row=i+1, col=1)

        fig_evolution.update_layout(
            template='plotly_white', # Asegurar tema claro para la gráfica
            height=1200, # Ajusta la altura total según sea necesario
            showlegend=True,
            legend_tracegroupgap=20, # Espacio entre grupos de leyendas si se usan tracegroup
            hovermode='x unified', # Muestra tooltips para todos los traces en el mismo punto x
            margin=dict(l=40, r=40, t=60, b=40) # Ajustar márgenes
        )
        # Rotar etiquetas del eje X para la última subgráfica (ya que comparten eje X)
        fig_evolution.update_xaxes(tickangle=45, row=len(metrics_to_plot), col=1)
        st.plotly_chart(fig_evolution, use_container_width=True)

    elif len(perfil_df_filtered) <= 1:
        st.info(f"No hay suficientes datos en el rango seleccionado para graficar la evolución de {usuario}.")


    # --- COMPARATIVA ENTRE PERFILES ---
    st.markdown("### 📊 Comparativa entre perfiles (último registro)")
    metric_to_compare_options = ("seguidores", "publicaciones", "seguidos")
    metric_to_compare = st.selectbox( # Corregido para usar las opciones correctas
        "Selecciona la métrica para comparar:",
        metric_to_compare_options,
        key="compare_metric"
    )

    fig_compare = px.bar(
        df_latest.sort_values(metric_to_compare, ascending=False),
        x="usuario",
        y=metric_to_compare,
        title=f"{metric_to_compare.capitalize()} por perfil",
        labels={'usuario': 'Perfil de Usuario', metric_to_compare: f"Nº de {metric_to_compare}"},
        color="usuario", # Colorea las barras por usuario
        text_auto=True # Muestra el valor encima de las barras
    )
    fig_compare.update_layout(
        template='plotly_white', # Asegurar tema claro para la gráfica
        xaxis_title="Perfil de Usuario",
        yaxis_title=f"Nº de {metric_to_compare.capitalize()}",
        showlegend=False # El color ya distingue, la leyenda podría ser redundante aquí
    )
    fig_compare.update_xaxes(tickangle=45)
    st.plotly_chart(fig_compare, use_container_width=True)

    # --- TABLA FINAL ---
    st.markdown("### 📋 Tabla completa de registros")
    st.dataframe(perfil_df.style.format({
        "publicaciones": "{:.0f}",
        "seguidores": "{:.0f}",
        "seguidos": "{:.0f}",
        "ratio_seguidores_seguidos": "{:.2f}",
        "anomalia_descripcion": "{}"
    }).set_properties(**{"text-align": "left"}).hide(axis="index"), use_container_width=True) # Ocultar índice

    # --- BOTÓN DE DESCARGA ---
    csv_data = perfil_df_filtered.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Descargar datos del perfil (CSV)",
        data=csv_data,
        file_name=f"{usuario}_instagram_data.csv",
        mime="text/csv",
        key=f"download_{usuario}"
    )

    # --- SECCIÓN DE ANOMALÍAS ---
    st.markdown("### ⚠️ Registros con Anomalías Detectadas")
    anomalies_display_df = perfil_df_filtered[perfil_df_filtered['anomalia_descripcion'].notna()]
    if not anomalies_display_df.empty:
        st.dataframe(
            anomalies_display_df[['fecha', 'publicaciones', 'seguidores', 'seguidos', 'anomalia_descripcion']].sort_values(by="fecha", ascending=False),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info(f"No se detectaron anomalías para {usuario} en el rango de fechas seleccionado.")

    # --- SECCIÓN DE PREDICCIONES ---
    st.markdown("### 🔮 Predicciones de Seguidores (con Statsmodels ARIMA)")

    # Usar todos los datos históricos del perfil para la tabla de predicciones
    historical_seguidores_full = perfil_df.set_index('fecha')['seguidores'].sort_index()

    # La función generate_predictions ahora maneja su propia lógica de datos mínimos.
    # Usamos un umbral aquí para evitar llamar a la función innecesariamente con muy pocos datos.
    if len(historical_seguidores_full) >= 10: # Un umbral razonable para intentar predicciones
        predictions_table_data = generate_predictions(historical_seguidores_full, n_future_steps=7) # sequence_length ya no es necesario
        if not predictions_table_data.empty:
            st.write(f"Predicción de seguidores para {usuario} en los próximos 7 días:")
            # Formatear para la tabla
            predictions_df_display = predictions_table_data.reset_index()
            predictions_df_display.columns = ['Fecha Predicha', 'Seguidores Predichos']
            # Asegurar que los seguidores predichos sean enteros para la visualización
            predictions_df_display['Seguidores Predichos'] = predictions_df_display['Seguidores Predichos'].astype(int)
            st.dataframe(
                predictions_df_display.style.format({'Fecha Predicha': '{:%Y-%m-%d}', "Seguidores Predichos": "{:,.0f}"}),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info(f"No se pudieron generar predicciones para {usuario} (modelo no cargado o datos históricos insuficientes).")
    else:
        st.info(f"No hay suficientes datos históricos para {usuario} para generar predicciones de seguidores.")

with tab_ciberseguridad:
    st.header("🛡️ Consejos de Ciberseguridad y Ayuda contra el Robo de Identidad")
    st.write("""
    Proteger tu identidad en línea es crucial. ¡No te preocupes! Aquí te dejamos algunos consejos prácticos y recursos útiles para mantenerte seguro.
    """)

    st.subheader("🔑 Cómo Prevenir el Robo de Identidad y Proteger tu Cuenta")
    st.markdown("""
    *   🔐 **Contraseñas Fuertes y Únicas:** ¡Crea contraseñas robustas! Mezcla mayúsculas, minúsculas, números y símbolos. ¡Y muy importante! Usa una contraseña diferente para cada cuenta. Un gestor de contraseñas puede ser tu mejor aliado.
                
    *   📱 **Autenticación de Dos Factores (2FA):** Actívala siempre que puedas, especialmente en Instagram. Es como ponerle un doble candado a tu cuenta.
                
    *   🎣 **¡Ojo con el Phishing!** Desconfía de correos, mensajes o webs que te pidan tu contraseña. Instagram NUNCA te la pedirá por esos medios. Revisa siempre que la dirección web (URL) sea la oficial.
                
    *   ⚙️ **Configuración de Privacidad al Día:** Echa un vistazo a quién puede ver tus cosas en Instagram. Decide qué compartes públicamente y qué no.
                
    *   🤫 **Información Sensible, ¡en Privado!** Evita publicar tu dirección completa, teléfono, datos bancarios o documentos personales.
    *   🔄 **Software Siempre Actualizado:** Mantén tu sistema operativo, navegador y la app de Instagram al día. ¡Las actualizaciones suelen incluir parches de seguridad!
    *   📶 **Cuidado con el Wi-Fi Público:** Si te conectas a una red Wi-Fi abierta, evita manejar información delicada. Una VPN puede ser una buena idea.
    *   👀 **Monitorea tu Actividad:** Revisa de vez en cuando quién ha iniciado sesión en tu cuenta (Configuración > Seguridad > Actividad de inicio de sesión) y los correos de seguridad de Instagram.
    """)

    st.subheader("🚨 ¿Qué Hacer si Sospechas de un Problema?")
    st.markdown("""
    Si crees que tu identidad ha sido robada o tu cuenta está en peligro:

    1.  🏃‍♂️ **¡Cambia tus Contraseñas YA!** Empieza por la de tu correo y la de Instagram.
    2.  🗣️ **Reporta a Instagram:** Usa las opciones de ayuda de la app para informar sobre el problema.
    3.  💳 **Avisa a tu Banco:** Si hay riesgo financiero, contacta a tus instituciones bancarias.
    4.  📧 **Revisa tu Correo:** Busca mensajes de Instagram sobre cambios no autorizados.
    5.  📢 **Alerta a tus Contactos:** Si tu cuenta está haciendo cosas raras (spam, mensajes extraños), avisa a tus amigos.
    """)

    st.subheader("🏛️ ¿A Quién Acudir para Ayuda Profesional?")
    st.markdown("""
    Si necesitas ayuda especializada, aquí tienes algunos contactos (ejemplos para México):

    *   **Guardia Nacional - Comando de Operaciones Cibernéticas:** Para reportar delitos cibernéticos. Puedes encontrar su información de contacto en el sitio oficial del Gobierno de México.
    *   **CONDUSEF (Comisión Nacional para la Protección y Defensa de los Usuarios de Servicios Financieros):** Útil si el robo de identidad involucra fraudes financieros.
    *   **Fiscalía General de la República (FGR) o Fiscalías Estatales:** Para realizar una denuncia formal.

    """)
    
# --- AVISO DE PRIVACIDAD Y LICENCIA ---
st.markdown("---") # Separador visual

with st.expander("📝 Aviso de Privacidad, Licencia y Autoría"):
    st.subheader("📄 Aviso de Privacidad")
    st.markdown("""
        Esta herramienta ha sido desarrollada con fines exclusivamente académicos y educativos como parte de un proyecto para la
        Universidad Nacional Rosario Castellanos (UNRC), Plantel Magdalena Contreras.
        
        La aplicación analiza datos de perfiles públicos de Instagram y no almacena información personal sensible
        más allá de los datos públicamente disponibles y necesarios para el análisis estadístico.
        
        El uso de esta herramienta es responsabilidad del usuario.
    """)

    st.subheader("⚖️ Licencia y Autoría")
    st.markdown("""
        **Licencia y Autoría:**
        *   **Proyecto Universitario:** Instagram Analyzer
        *   **Institución:** Universidad Nacional Rosario Castellanos, Plantel Magdalena Contreras.
        *   **Autores:** Carlos Daniel López Gordillo, Andrea Hernández de la Cruz.
        *   **Propósito:** Herramienta para el análisis de actividad y detección de anomalías en perfiles de Instagram.
        *   **Licencia:** Este proyecto se distribuye bajo una licencia educativa/académica. (Puedes especificar una licencia si la tienes, ej. MIT, Creative Commons, o simplemente dejarlo así para un proyecto universitario).
    """)