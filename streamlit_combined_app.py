import streamlit as st
import joblib
import pandas as pd
import sqlite3
from datetime import datetime
from urllib.parse import urlparse
import os
import sys # Para modificar sys.path
import random # Para los consejos dinámicos
import re # Para expresiones regulares (extraer URLs en el analizador de mensajes)

# --- CONFIGURACIÓN PARA ACCEDER A MÓDULOS DE INSTAGRAM_ANALYZER ---
# Obtener el directorio del script actual (streamlit_combined_app.py)
APP_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Construir la ruta a la carpeta 'instagram_analyzer'
# Si streamlit_combined_app.py está DENTRO de 'instagram_analyzer',
# entonces APP_ROOT_DIR ya es la ruta a la carpeta 'instagram_analyzer'.
# INSTAGRAM_ANALYZER_MODULES_PATH = os.path.join(APP_ROOT_DIR, "instagram_analyzer") # Esto causaría .../instagram_analyzer/instagram_analyzer/
INSTAGRAM_ANALYZER_MODULES_PATH = APP_ROOT_DIR

# Añadir esta ruta a sys.path para que Python encuentre 'utils' y 'analysis'
if INSTAGRAM_ANALYZER_MODULES_PATH not in sys.path:
    sys.path.append(INSTAGRAM_ANALYZER_MODULES_PATH)
# --- IMPORTACIONES PARA EL DASHBOARD DE INSTAGRAM ---
try:
    from utils.converters import convertir_numero
    from analysis.predictor import generate_predictions
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    INSTAGRAM_MODULES_LOADED = True
except ImportError as e:
    INSTAGRAM_MODULES_LOADED = False
    INSTAGRAM_IMPORT_ERROR = e
    # Estas funciones serán stubs si los módulos no cargan
    def convertir_numero(x): return x
    def generate_predictions(series, n_future_steps): return pd.Series()


# --- CONSTANTES GLOBALES ---
MODEL_FILENAME_URL_DETECTOR = "modelo_xgboost_urls.pkl"
DB_FILENAME_URL_DETECTOR = "urls.db"
DB_FILENAME_USER_REPORTS = "user_reports.db" # Nueva base de datos para reportes

# Ruta para la base de datos del dashboard de Instagram
DB_PATH_INSTAGRAM = os.path.join(INSTAGRAM_ANALYZER_MODULES_PATH, "data", "analisis_instagram.db")


# --- Funciones para el Detector de URLs (Adaptadas de app.py) ---
@st.cache_resource
def load_model_url_detector(model_path):
    try:
        modelo = joblib.load(model_path)
        return modelo
    except FileNotFoundError:
        st.error(f"Error: El archivo del modelo '{model_path}' no se encontró.")
        return None
    except Exception as e:
        st.error(f"Error al cargar el modelo de URLs: {e}")
        return None

@st.cache_resource
def get_db_connection_url_detector(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historial_urls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT,
        clasificacion TEXT,
        probabilidad REAL,
        fecha TEXT
    )
    """)
    conn.commit()
    return conn

def extraer_caracteristicas_url(url: str):
    parsed = urlparse(url)
    longitud = len(url)
    digitos = sum(c.isdigit() for c in url)
    guiones = url.count("-")
    https = 1 if parsed.scheme == "https" else 0
    puntos = url.count(".")

    # Alineando con la lógica original de app.py (FastAPI) para estas características
    # pero con manejo de errores para evitar fallos si netloc es None o no tiene partes.
    if parsed.netloc:
        netloc_parts = parsed.netloc.split('.')
        subdominios = parsed.netloc.count(".")
        try:
            prefijo_guion = 1 if "-" in netloc_parts[0] else 0
        except IndexError: # En caso de que netloc_parts esté vacío, aunque if parsed.netloc debería prevenirlo
            prefijo_guion = 0
        subdominio_raro = 1 if len(netloc_parts) > 3 else 0
    else:
        subdominios = 0
        prefijo_guion = 0
        subdominio_raro = 0

    acortador = 1 if any(s in url for s in ["bit.ly", "t.co", "tinyurl"]) else 0
    tlds_sospechosos = (".tk", ".ml", ".ga", ".cf", ".gq")
    tld_sospechoso = 1 if url.endswith(tlds_sospechosos) else 0
    return [
        longitud, digitos, guiones, https, # 0, 1, 2, 3
        puntos, subdominios, prefijo_guion, # 4, 5, 6
        subdominio_raro, acortador, tld_sospechoso # 7, 8, 9
    ]

# Lista blanca de dominios seguros conocidos
DOMINIOS_CONFIABLES = [
    "youtube.com", "www.youtube.com", "google.com", "www.google.com",
    "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
    "twitter.com", "www.twitter.com", "linkedin.com", "www.linkedin.com",
    # Agrega más según tu contexto
]

def analizar_y_registrar_url(url: str, modelo, conn):
    parsed = urlparse(url)
    dominio = parsed.netloc.lower()
    # Verifica si el dominio está en la lista blanca
    if any(dominio.endswith(dominio_conf) for dominio_conf in DOMINIOS_CONFIABLES):
        prob_maliciosa = 0.0
        clasificacion = "segura"
        explicacion = [{"text": "✅ Dominio reconocido como seguro.", "tooltip": "Este dominio es ampliamente reconocido y confiable."}]
        # Registrar en historial como segura
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO historial_urls (url, clasificacion, probabilidad, fecha) VALUES (?, ?, ?, ?)",
                        (url, clasificacion, float(prob_maliciosa), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        except sqlite3.Error as e:
            st.error(f"Error al guardar en BD de URLs: {e}")
        return prob_maliciosa, clasificacion, explicacion

    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return None, "URL inválida", ["Por favor, ingresa una URL válida comenzando con http:// o https://."]
    caracteristicas = extraer_caracteristicas_url(url)
    column_names = [
        "longitud_url", "cantidad_digitos", "cantidad_guiones", "https",
        "nb_dots", "nb_subdomains", "prefix_suffix",
        "abnormal_subdomain", "shortening_service", "suspecious_tld"
    ]
    entrada = pd.DataFrame([caracteristicas], columns=column_names)
    prob_maliciosa = modelo.predict_proba(entrada)[0][1]
    clasificacion = "maliciosa" if prob_maliciosa > 0.5 else "segura"
    explicacion = []

    # Diccionario de tooltips
    tooltips = {
        "shortening_service": "Los acortadores de URL (ej. bit.ly, t.co) pueden ocultar el destino real del enlace, siendo a veces usados en phishing o para distribuir malware.",
        "suspecious_tld": "Algunos Dominios de Nivel Superior (TLD) como .tk, .ml, .ga, .cf, .gq son ofrecidos gratuitamente o a bajo costo y son frecuentemente abusados para actividades maliciosas.",
        "prefix_suffix": "El uso de guiones en el nombre de dominio o subdominio (ej. 'secure-paypal.com') puede ser una táctica para imitar sitios legítimos o hacer que la URL parezca más compleja.",
        "abnormal_subdomain": "Un número excesivo de subdominios (ej. login.user.account.secure.example.com) o estructuras de subdominio extrañas pueden indicar un intento de ofuscación o phishing.",
        "no_https": "HTTPS (HyperText Transfer Protocol Secure) cifra la comunicación entre tu navegador y el sitio web. La ausencia de HTTPS significa que los datos transmitidos no son seguros y pueden ser interceptados."
    }

    if entrada["shortening_service"].iloc[0] == 1:
        explicacion.append({
            "text": "⚠️ La URL utiliza un servicio de acortamiento.",
            "tooltip": tooltips["shortening_service"]
        })
    if entrada["suspecious_tld"].iloc[0] == 1:
        explicacion.append({
            "text": "⚠️ El TLD es de un tipo sospechoso.",
            "tooltip": tooltips["suspecious_tld"]
        })
    if entrada["prefix_suffix"].iloc[0] == 1:
        explicacion.append({
            "text": "⚠️ El dominio/subdominio contiene un guion.",
            "tooltip": tooltips["prefix_suffix"]
        })
    if entrada["abnormal_subdomain"].iloc[0] == 1:
        explicacion.append({
            "text": "⚠️ Estructura de subdominios inusual.",
            "tooltip": tooltips["abnormal_subdomain"]
        })
    if entrada["https"].iloc[0] == 0:
        explicacion.append({
            "text": "⚠️ La URL no utiliza HTTPS.",
            "tooltip": tooltips["no_https"]
        })
    if not explicacion:
        explicacion.append({"text": "✅ No se detectaron patrones sospechosos comunes.", "tooltip": "Basado en las características analizadas, la URL no presenta indicadores comunes de riesgo."})
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO historial_urls (url, clasificacion, probabilidad, fecha) VALUES (?, ?, ?, ?)",
                       (url, clasificacion, float(prob_maliciosa), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Error al guardar en BD de URLs: {e}")
    return prob_maliciosa, clasificacion, explicacion

def obtener_historial_urls(conn, limit=10):
    cursor = conn.cursor()
    cursor.execute("SELECT url, clasificacion, probabilidad, fecha FROM historial_urls ORDER BY id DESC LIMIT ?", (limit,))
    return cursor.fetchall()

def obtener_resumen_clasificacion_urls(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT clasificacion, COUNT(*) FROM historial_urls GROUP BY clasificacion")
    return cursor.fetchall()

# --- Funciones para la Base de Datos de Reportes de Usuarios ---
@st.cache_resource
def get_db_connection_user_reports(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reported_incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo_reporte TEXT, -- 'URL' o 'Mensaje'
        contenido_reportado TEXT,
        comentario_adicional TEXT,
        fecha_reporte TEXT
    )
    """)
    conn.commit()
    return conn

def guardar_reporte_usuario(conn, tipo_reporte, contenido, comentario):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO reported_incidents (tipo_reporte, contenido_reportado, comentario_adicional, fecha_reporte) VALUES (?, ?, ?, ?)",
                   (tipo_reporte, contenido, comentario, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()

# --- Funciones para el Analizador de Mensajes Sospechosos ---
def analizar_texto_sospechoso(texto: str, remitente_email: str, modelo_urls, conn_urls):
    indicadores = []
    urls_encontradas_info = []
    puntuacion_sospecha = 0

    # Palabras clave de phishing con pesos (expandir y ajustar pesos según importancia)
    # Categorías: Urgencia, Amenazas, Premios, Solicitud de Info, Técnicas Comunes
    keywords_phishing_con_peso = {
        # Urgencia / Amenazas (Peso Alto)
        "urgente": 3, "inmediatamente": 3, "expira pronto": 3, "suspensión de cuenta": 4, "cuenta bloqueada": 4,
        "actividad sospechosa": 3, "problema de seguridad": 3, "alerta de seguridad": 3, "acción requerida": 3,
        "última advertencia": 4, "su cuenta será eliminada": 4,
        # Premios / Ofertas Irresistibles (Peso Medio-Alto)
        "premio ganado": 3, "ha sido seleccionado": 2, "lotería": 3, "recompensa exclusiva": 2,
        "felicidades": 1, "oferta especial": 1, "regalo": 2, "oportunidad única": 2,
        # Solicitud de Información / Credenciales (Peso Muy Alto)
        "verifique su cuenta": 4, "actualice sus datos": 3, "confirme su contraseña": 5,
        "ingrese sus credenciales": 5, "proporcione su pin": 5, "datos bancarios": 4, "número de tarjeta": 4,
        "iniciar sesión aquí": 3, "haga clic para validar": 3,
        # Nombres de Servicios Comunes (Peso Bajo - para contexto, el peligro real es si piden acción)
        "banco": 1, "paypal": 1, "apple": 1, "google": 1, "microsoft": 1, "amazon": 1,
        "instagram": 1, "facebook": 1, "whatsapp": 1, "netflix": 1, "soporte técnico": 2,
        # Técnicas / Frases Comunes (Peso Medio)
        "estimado cliente": 1, "querido usuario": 1, # Genérico
        "haga clic aquí": 2, "visite este enlace": 2, "descargar archivo adjunto": 3,
        "error gramatical obvio": 2, # Esto requeriría una detección más compleja, por ahora es un placeholder
        "dominio no coincide": 4 # Se evaluará más adelante
    }

    texto_lower = texto.lower()
    for keyword, peso in keywords_phishing_con_peso.items():
        if keyword in texto_lower:
            indicadores.append(f"⚠️ Palabra clave/frase sospechosa: '{keyword}' (Peso: {peso}).")
            puntuacion_sospecha += peso

    # Detección de URLs (Expresión regular mejorada)
    # Fuente: https://stackoverflow.com/questions/3809401/what-is-a-good-regular-expression-to-match-a-url
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    urls_en_texto = re.findall(url_pattern, texto)
    
    dominio_remitente = None
    if remitente_email and "@" in remitente_email:
        try:
            dominio_remitente = remitente_email.split("@")[1].lower()
            indicadores.append(f"ℹ️ Dominio del remitente: {dominio_remitente}")
        except IndexError:
            indicadores.append("⚠️ No se pudo extraer el dominio del remitente.")

    if urls_en_texto:
        indicadores.append(f"ℹ️ Se encontraron {len(urls_en_texto)} URL(s) en el texto. Analizándolas...")
        for url_msg in urls_en_texto:
            # Reutiliza tu función existente para analizar URLs
            prob, clasificacion_url, _ = analizar_y_registrar_url(url_msg, modelo_urls, conn_urls)
            if prob is not None:
                urls_encontradas_info.append({
                    "URL": url_msg,
                    "Clasificación": clasificacion_url.capitalize(),
                    "Prob. Maliciosa (%)": round(prob * 100, 2)
                })
                if clasificacion_url == "maliciosa":
                    puntuacion_sospecha += 5 # Peso alto para URL maliciosa
                    indicadores.append(f"🚨 URL detectada como maliciosa: {url_msg} (Peso: 5)")
                
                # Análisis de dominio del remitente vs dominio de URL
                if dominio_remitente:
                    try:
                        parsed_url_msg = urlparse(url_msg)
                        dominio_url_msg = parsed_url_msg.netloc.lower()
                        if dominio_url_msg and dominio_remitente not in dominio_url_msg and dominio_url_msg not in dominio_remitente:
                            # Evitar falsos positivos con subdominios o dominios de acortadores genéricos
                            # Esta lógica puede necesitar refinamiento
                            if not any(acortador_comun in dominio_url_msg for acortador_comun in ["bit.ly", "t.co", "tinyurl.com"]):
                                indicadores.append(f"⚠️ Discrepancia de dominio: Remitente ({dominio_remitente}) vs URL ({dominio_url_msg}). (Peso: 4)")
                                puntuacion_sospecha += 4
                    except Exception as e:
                        print(f"Error al parsear URL para comparación de dominio: {e}")

            else: # Error en el análisis de la URL (ej. formato inválido)
                 urls_encontradas_info.append({
                    "URL": url_msg,
                    "Clasificación": "Error de análisis",
                    "Prob. Maliciosa (%)": "N/A"
                })
    
    # Interpretación de la puntuación
    nivel_riesgo = "Bajo"
    if puntuacion_sospecha >= 10:
        nivel_riesgo = "Alto"
    elif puntuacion_sospecha >= 5:
        nivel_riesgo = "Medio"

    if not indicadores and not urls_encontradas_info:
        indicadores.append("✅ El texto no presenta indicadores obvios de phishing basados en el análisis actual (palabras clave y URLs). Sin embargo, siempre mantente alerta.")
    elif not indicadores and urls_encontradas_info: # Solo se encontraron URLs, pero no otras palabras clave
        indicadores.append("ℹ️ No se detectaron palabras clave sospechosas, pero se encontraron URLs. Revisa el análisis de las URLs para determinar el riesgo.")

    return indicadores, urls_encontradas_info, puntuacion_sospecha, nivel_riesgo

# --- Funciones para el Dashboard de Instagram (si se necesitan fuera del bloque principal) ---
# `convertir_numero` y `generate_predictions` se importan arriba.

# --- CONFIGURACIÓN DE PÁGINA (Debe ser el primer comando de Streamlit) ---
st.set_page_config(
    layout="wide",
    page_title="Protección Digital", # Título actualizado para la pestaña del navegador
    page_icon="🛡️" # Icono para la pestaña del navegador
)

# --- Interfaz de Usuario con Streamlit ---
def main_app():
    # --- Selección de Tema ---
    # Ya no hay selección de tema, se usa directamente "Teal Profundo y Blanco"
    # if 'selected_background_color' not in st.session_state:
    #     st.session_state.selected_background_color = "Teal Profundo y Blanco" # Nuevo tema por defecto

    # background_options = ["Teal Profundo y Blanco", "Verde Aqua"]
    # selected_background_from_ui = st.sidebar.radio(
    #     "🎨 Selecciona un Color de Fondo:",
    #     background_options,
    #     index=background_options.index(st.session_state.selected_background_color),
    #     key="background_color_selector"
    # )
    # if selected_background_from_ui != st.session_state.selected_background_color:
    #     st.session_state.selected_background_color = selected_background_from_ui
    #     st.rerun()

    # Definir colores fijos del tema "Teal Profundo y Blanco"
    APP_BG_COLOR = "#009288"                # Verde azulado oscuro (solicitado)
    PRIMARY_TEXT_COLOR = "#FFFFFF"          # Blanco (para texto sobre APP_BG_COLOR)
    COMPONENT_BG_COLOR = "#FFFFFF"          # Blanco (para inputs, sidebar, cards)
    COMPONENT_TEXT_COLOR = "#212529"        # Negro/Gris oscuro (para texto sobre COMPONENT_BG_COLOR)
    COMPONENT_PLACEHOLDER_COLOR = "#6c757d" # Gris medio (para placeholders sobre COMPONENT_BG_COLOR)
    COMPONENT_BORDER_COLOR = "#ced4da"      # Gris claro (para bordes de componentes)
    ACCENT_COLOR = "#007a70"                # Un teal ligeramente más oscuro o diferente para acentos
    HOVER_BG_COLOR_ON_COMPONENT = "#f8f9fa" # Gris muy claro para hover sobre componentes blancos

    # --- Estilos Específicos para Gráficas (Independientes del Tema de la App) ---
    # Estos aseguran que las gráficas siempre tengan un fondo claro y colores de datos distinguibles.
    GRAPH_TEMPLATE = "plotly_white"  # Siempre usar un template claro para las gráficas
    INSTA_GRAPH_BAR_COLOR = ['#1f77b4']  # Azul oscuro para barras (color por defecto de Plotly)
    INSTA_GRAPH_LINE_PRIMARY = '#1f77b4'    # Azul oscuro para líneas primarias
    INSTA_GRAPH_LINE_SECONDARY = "#ffffff"  # Gris oscuro para líneas secundarias

    # Colores para alertas (fondos claros, texto oscuro consistente con COMPONENT_TEXT_COLOR)
    ALERT_INFO_BG = COMPONENT_BG_COLOR    # Fondo blanco para alerta info
    ALERT_SUCCESS_BG = COMPONENT_BG_COLOR # Fondo blanco para alerta success
    ALERT_WARNING_BG = COMPONENT_BG_COLOR # Fondo blanco para alerta warning
    ALERT_ERROR_BG = COMPONENT_BG_COLOR   # Fondo blanco para alerta error

    # Estilos CSS dinámicos para la aplicación general
    st.markdown(
        f"""
        <style>
            /* Tema General */
            .stApp {{
                background-color: {APP_BG_COLOR} !important;
            }}
            /* Color de texto principal y elementos comunes */
            body, .stApp, .stMarkdown,
            h1, h2, h3, h4, h5, h6, p, li, label,
            .stTextInput > div > div > input,
            .stTextArea > div > div > textarea,
            .stSelectbox > label, .stMultiSelect > label, .stRadio > label, .stDateInput > label,
            .stFileUploader > label,
            .stDownloadButton > button > div > p, /* Texto del botón de descarga */
            div[data-testid="stCaptionContainer"] /* st.caption */
            {{  
                color: {PRIMARY_TEXT_COLOR} !important;
            }}

            /* Text elements inside tab content should use COMPONENT_TEXT_COLOR for better readability on white tab background */
            div[data-testid="stTabContent"] p,
            div[data-testid="stTabContent"] li,
            div[data-testid="stTabContent"] h1,
            div[data-testid="stTabContent"] h2,
            div[data-testid="stTabContent"] h3,
            div[data-testid="stTabContent"] h4,
            div[data-testid="stTabContent"] h5,
            div[data-testid="stTabContent"] h6,
            div[data-testid="stTabContent"] label, /* General labels inside tabs */
            /* More specific for markdown containers within tabs */
            div[data-testid="stTabContent"] div[data-testid="stMarkdownContainer"] p,
            div[data-testid="stTabContent"] div[data-testid="stMarkdownContainer"] li,
            div[data-testid="stTabContent"] div[data-testid="stMarkdownContainer"] h1,
            div[data-testid="stTabContent"] div[data-testid="stMarkdownContainer"] h2,
            div[data-testid="stTabContent"] div[data-testid="stMarkdownContainer"] h3,
            div[data-testid="stTabContent"] div[data-testid="stMarkdownContainer"] h4,
            div[data-testid="stTabContent"] div[data-testid="stMarkdownContainer"] h5,
            div[data-testid="stTabContent"] div[data-testid="stMarkdownContainer"] h6,
            div[data-testid="stTabContent"] div[data-testid="stCaptionContainer"], /* For st.caption inside tabs */
            div[data-testid="stTabContent"] .stMarkdown /* General stMarkdown class inside tabs */
            {{
                color: {COMPONENT_TEXT_COLOR} !important;
            }}
            /* Inputs, Selects, TextAreas - Fondo y Borde */
            .stTextInput > div > div > input,
            .stTextArea > div > div > textarea,
            .stDateInput > div > div input, /* Input del date_input */
            div[data-baseweb="select"] /* Contenedor principal de st.selectbox y st.multiselect */
            {{
                background-color: {COMPONENT_BG_COLOR} !important;
                color: {COMPONENT_TEXT_COLOR} !important;
                border: 1px solid {COMPONENT_BORDER_COLOR} !important;
            }}
            /* Específicamente para el contenido DENTRO de Selectbox/Multiselect (tags, valor seleccionado, placeholder) */
            /* Esto asegura que el texto dentro del control sea oscuro y el fondo del área de contenido sea blanco */
            div[data-baseweb="select"] > div {{ /* Div que contiene el valor/tags/placeholder */
                background-color: {COMPONENT_BG_COLOR} !important; /* Fondo blanco para el área interna */
                color: {COMPONENT_TEXT_COLOR} !important; /* Texto oscuro para el contenido */
            }}
            /* Para el texto del input de búsqueda dentro de un multiselect */
            div[data-baseweb="select"] input[type="text"] {{
                color: {COMPONENT_TEXT_COLOR} !important; /* Asegura que el texto que escribes sea oscuro */
            }}
            .stTextInput input::placeholder, .stTextArea textarea::placeholder {{
                color: {COMPONENT_PLACEHOLDER_COLOR} !important;
            }}
            /* Dropdown menu (popover) de Selectbox/Multiselect */
            div[data-baseweb="popover"] div[data-baseweb="menu"] {{
                background-color: {COMPONENT_BG_COLOR} !important;
            }}
            div[data-baseweb="popover"] div[data-baseweb="menu"] li {{
                color: {COMPONENT_TEXT_COLOR} !important;
            }}
            div[data-baseweb="popover"] div[data-baseweb="menu"] li:hover {{
                background-color: {HOVER_BG_COLOR_ON_COMPONENT} !important;
            }}

            /* Estilos específicos de la app */
            .big-font {{ font-size:32px !important; font-weight: bold; color: {PRIMARY_TEXT_COLOR} !important; }}
            .metric-label {{ font-size:18px; color: {PRIMARY_TEXT_COLOR} !important; opacity: 0.85; }}
            .block-container {{ padding-top: 2.5rem; }}

            /* Botones */
            .stButton>button {{ 
                background-color: {COMPONENT_BG_COLOR};
                /* El color del texto se definirá más abajo para los elementos <p> internos */
                border: 1px solid {COMPONENT_BORDER_COLOR};
            }}
            /* Texto para el elemento botón en sí (si el texto está directamente en él) */
            .stButton > button {{
                color: {COMPONENT_TEXT_COLOR} !important;
            }}
            /* Texto para elementos comunes DENTRO de los botones de Streamlit */
            .stButton > button p,
            .stButton > button span,
            .stButton > button div {{
                color: {COMPONENT_TEXT_COLOR} !important;
            }}

            /* Estilo específico para el BOTÓN QUE ACTIVA st.popover (ej. "ℹ️ Sobre los Autores") */
            /* Este botón tiene data-testid="stPopoverButton" según el HTML proporcionado. */
            button[data-testid="stPopoverButton"] {{
                background-color: {COMPONENT_BG_COLOR} !important; /* Fondo blanco */
                border: 1px solid {COMPONENT_BORDER_COLOR} !important; /* Borde normal */
            }}
            /* Texto DENTRO del botón que activa el st.popover */
            button[data-testid="stPopoverButton"] p,
            button[data-testid="stPopoverButton"] div, /* Cubre el div con stMarkdownContainer */
            button[data-testid="stPopoverButton"] span {{ /* Por si acaso hay spans */
                color: {COMPONENT_TEXT_COLOR} !important;
            }}
            /* El :hover debería ser manejado por la regla general .stButton:hover */

            /* Toast */
            .stToast {{ 
                background-color: {COMPONENT_BG_COLOR} !important; /* Fondo blanco */
                border: 1px solid {COMPONENT_BORDER_COLOR} !important;
            }}
            /* Forzar color de texto oscuro para el contenido dentro del toast */
            .stToast, .stToast p, .stToast div {{
                color: {COMPONENT_TEXT_COLOR} !important;
            }}
            /* Emotion */
            .st-emotion-cache-ktz07o {{ 
                background-color: {COMPONENT_BG_COLOR} !important;
                color: {COMPONENT_TEXT_COLOR};
                border: 1px solid {COMPONENT_BORDER_COLOR};
            }}
            /* Emotion-pop up */
            #bui3, #bui3 > div > div > div {{ 
                background-color: {COMPONENT_BG_COLOR} !important;
                color: {COMPONENT_TEXT_COLOR};
                border: 0px solid {COMPONENT_BORDER_COLOR};
            }}

            .stButton>button:hover {{
                border-color: {ACCENT_COLOR} !important; 
                background-color: {HOVER_BG_COLOR_ON_COMPONENT} !important;
            }}
            .stDownloadButton > button {{ 
                background-color: {COMPONENT_BG_COLOR} !important; 
                border: 1px solid {COMPONENT_BORDER_COLOR} !important; 
            }}
            .stDownloadButton > button:hover {{ 
                border-color: {ACCENT_COLOR} !important; 
                background-color: {HOVER_BG_COLOR_ON_COMPONENT} !important; 
            }}
            .stDownloadButton > button > div > p {{ color: {COMPONENT_TEXT_COLOR} !important; }}

            /* st.metric */
            div[data-testid="stMetric"], div[data-testid="stMetricValue"], div[data-testid="stMetricLabel"], div[data-testid="stMetricDelta"] {{ color: {PRIMARY_TEXT_COLOR} !important; }}
            div[data-testid="stMetricDelta"] svg {{ fill: {PRIMARY_TEXT_COLOR} !important; }}

            /* --- Estilos Mejorados para st.tabs --- */

            /* Contenedor de las pestañas (para el borde inferior general) */
            div[data-testid="stTabs"] {{
                border-bottom: 1px solid {COMPONENT_BORDER_COLOR} !important;
                margin-bottom: 0px; /* Ajustar si es necesario más espacio antes del contenido */
            }}

            /* Botón de Pestaña General (Activa e Inactiva) */
            button[data-baseweb="tab"] {{
                font-family: 'Source Sans Pro', sans-serif;
                padding: 10px 18px !important;
                margin-right: 1px !important;
                margin-bottom: -1px !important; /* Superponer al borde del contenedor */
                border: 1px solid transparent !important;
                border-bottom: none !important;
                border-radius: 6px 6px 0 0 !important;
                transition: background-color 0.2s ease-in-out, color 0.2s ease-in-out, border-color 0.2s ease-in-out !important;
                position: relative;
                outline: none !important;
            }}

            /* Pestaña Inactiva */
            button[data-baseweb="tab"]:not([aria-selected="true"]) {{
                background-color: #f0f2f5 !important; /* Gris muy claro, ligeramente diferente a HOVER_BG_COLOR_ON_COMPONENT */
                color: #5a5a5a !important; /* Texto gris oscuro para inactivas */
                border-color: {COMPONENT_BORDER_COLOR} !important;
            }}

            /* Pestaña Inactiva - Hover */
            button[data-baseweb="tab"]:not([aria-selected="true"]):hover {{
                background-color: #e9ecef !important;
                color: {COMPONENT_TEXT_COLOR} !important; /* Texto más oscuro en hover */
                border-color: #adb5bd !important;
            }}

            /* Pestaña Activa */
            button[data-baseweb="tab"][aria-selected="true"] {{
                background-color: {COMPONENT_BG_COLOR} !important; /* Fondo blanco */
                color: {ACCENT_COLOR} !important; /* Texto con color de acento */
                font-weight: 600 !important;
                border-color: {COMPONENT_BORDER_COLOR} {COMPONENT_BORDER_COLOR} {COMPONENT_BG_COLOR} !important;
                border-width: 1px !important;
                border-style: solid !important;
                z-index: 1; /* Para asegurar que esté por encima */
            }}

            /* Texto dentro de los botones de pestaña (para asegurar herencia correcta) */
            button[data-baseweb="tab"] div, button[data-baseweb="tab"] span, button[data-baseweb="tab"] p {{ color: inherit !important; }}


            /* Contenedor del contenido de la pestaña */
            div[data-testid="stTabContent"] {{
                background-color: {COMPONENT_BG_COLOR} !important;
                padding: 20px !important; /* Más padding para el contenido */
                border: 1px solid {COMPONENT_BORDER_COLOR} !important;
                border-top: none !important;
                border-radius: 0 0 6px 6px !important; /* Redondear esquinas inferiores */
                margin-top: 0px; /* Eliminar cualquier margen superior que pueda causar un espacio */
            }}

            /* --- Estilos para Popovers de BaseWeb (usados por st.select, st.multiselect, st.date_input, st.popover) --- */

            /* Contenido del st.popover (ej. "ℹ️ Sobre los Autores") */
            /* Usamos data-testid para ser específicos para el componente st.popover de Streamlit */
            div[data-testid="stPopover"] div[data-baseweb="popover"] > div > div {{ /* Contenedor del contenido */
                background-color: {COMPONENT_BG_COLOR} !important;
                color: {COMPONENT_TEXT_COLOR} !important;
            }}
            div[data-testid="stPopover"] div[data-baseweb="popover"] > div > div * {{ /* Todos los hijos dentro del st.popover */
                color: {COMPONENT_TEXT_COLOR} !important; /* Asegurar que todo el texto sea oscuro */
            }}

            /* Dropdown de st.selectbox y st.multiselect */
            /* El div[role="listbox"] es el contenedor del menú desplegable */
            div[data-baseweb="popover"] > div[role="listbox"] {{
                background-color: {COMPONENT_BG_COLOR} !important;
                border: 1px solid {COMPONENT_BORDER_COLOR} !important;
                border-radius: 0.25rem; /* Opcional: para darle bordes redondeados */
            }}
            /* El menú dentro del listbox */
            div[data-baseweb="popover"] > div[role="listbox"] div[data-baseweb="menu"] {{
                background-color: {COMPONENT_BG_COLOR} !important; /* Fondo blanco para el menú */
            }}
            /* Items de la lista en el menú */
            div[data-baseweb="popover"] > div[role="listbox"] div[data-baseweb="menu"] li {{
                color: {COMPONENT_TEXT_COLOR} !important; /* Texto oscuro */
                background-color: transparent !important; /* Sin fondo propio por defecto */
            }}
            div[data-baseweb="popover"] > div[role="listbox"] div[data-baseweb="menu"] li:hover {{
                background-color: {HOVER_BG_COLOR_ON_COMPONENT} !important; /* Fondo claro en hover */
                color: {COMPONENT_TEXT_COLOR} !important; /* Texto oscuro en hover */
            }}
            /* Texto de "No results" o similar dentro del listbox */
            div[data-baseweb="popover"] > div[role="listbox"] div:not([data-baseweb="menu"]) /* Cualquier div que no sea el menú */
            {{
                 color: {COMPONENT_TEXT_COLOR} !important; /* Texto oscuro */
                 background-color: {COMPONENT_BG_COLOR} !important; /* Fondo blanco */
            }}

            /* Encabezado del calendario: Mes, Año y flechas de navegación */
            div[data-baseweb="popover"] div[role="dialog"] div[data-baseweb="calendar-header"] {{ /* El header completo */
                background-color: {COMPONENT_BG_COLOR} !important;
            }}
            /* Contenedor principal del calendario (st.date_input dropdown) */
            div[data-baseweb="popover"] > div[role="dialog"] {{ /* El div[role="dialog"] es el contenedor del calendario */
                background-color: {COMPONENT_BG_COLOR} !important;
                border: 1px solid {COMPONENT_BORDER_COLOR} !important; /* Opcional: borde */
                border-radius: 0.5rem; /* Opcional: para que coincida con otros componentes */
            }}
            div[data-baseweb="popover"] div[role="dialog"] div[data-baseweb="calendar-header"] > div, /* Para el texto del Mes y Año */
            div[data-baseweb="popover"] div[role="dialog"] div[data-baseweb="calendar-header"] button svg {{ /* Para las flechas SVG */
                color: {COMPONENT_TEXT_COLOR} !important;
                fill: {COMPONENT_TEXT_COLOR} !important; /* Para los SVG de las flechas */
                background-color: transparent !important; /* Asegurar que el fondo de las flechas no sea oscuro */
            }}

            /* Días de la semana (Mo, Tu, We...) */
            div[data-baseweb="popover"] div[role="dialog"][data-baseweb="calendar"] abbr {{
                color: {COMPONENT_TEXT_COLOR} !important;
            }}

            /* Contenedor de la grilla de días del calendario */
            div[data-baseweb="popover"] div[role="dialog"][data-baseweb="calendar"] div[role="grid"] {{
                background-color: {COMPONENT_BG_COLOR} !important;
            }}

            /* Celdas de los días (números) */
            div[data-baseweb="popover"] div[role="dialog"][data-baseweb="calendar"] div[data-baseweb="day"] {{
                color: {COMPONENT_TEXT_COLOR} !important;
            }}

            /* Estilo para el día seleccionado */
            div[data-baseweb="popover"] div[role="dialog"][data-baseweb="calendar"] div[data-baseweb="day"][aria-selected="true"] {{
                background-color: {ACCENT_COLOR} !important;
                color: #FFFFFF !important; /* Texto blanco sobre fondo de acento */
            }}

            /* Estilo para el hover sobre los días (que no estén deshabilitados) */
            div[data-baseweb="popover"] div[role="dialog"][data-baseweb="calendar"] div[data-baseweb="day"]:not([aria-disabled="true"]):not([aria-selected="true"]):hover {{
                background-color: {HOVER_BG_COLOR_ON_COMPONENT} !important;
            }}
            /* Asegurar que el contenedor del calendario en sí también tenga fondo blanco si es necesario,
               aunque la regla para div[role="dialog"] debería cubrirlo. */
            div[data-baseweb="calendar"] {{
                background-color: {COMPONENT_BG_COLOR} !important;
            }}

            /* st.expander */
            .stExpander header {{ background-color: {COMPONENT_BG_COLOR} !important; color: {COMPONENT_TEXT_COLOR} !important; }}
            .stExpander header:hover {{ background-color: {HOVER_BG_COLOR_ON_COMPONENT} !important; }}
            .stExpander div[role="button"] svg {{ fill: {COMPONENT_TEXT_COLOR} !important; }}

            /* st.code y bloques de código */
            pre, code, .stCodeBlock, div[data-testid="stCodeBlock"] > div {{ 
                background-color: {COMPONENT_BG_COLOR} !important; 
                color: {COMPONENT_TEXT_COLOR} !important; 
            }}
            .stCodeBlock {{ border: 1px solid {COMPONENT_BORDER_COLOR} !important; }}

            /* Alertas (st.info, st.success, st.warning, st.error) */
            div[data-testid="stAlert"] p {{ color: {COMPONENT_TEXT_COLOR} !important; }} /* Texto dentro de alertas */
            div[data-testid="stAlert"][kind="info"] {{ background-color: {ALERT_INFO_BG} !important; }}
            div[data-testid="stAlert"][kind="success"] {{ background-color: {ALERT_SUCCESS_BG} !important; }}
            div[data-testid="stAlert"][kind="warning"] {{ background-color: {ALERT_WARNING_BG} !important; }}
            div[data-testid="stAlert"][kind="error"] {{ background-color: {ALERT_ERROR_BG} !important; }}
            div[data-testid="stAlert"] svg {{ fill: {COMPONENT_TEXT_COLOR} !important; }} /* Iconos de alertas */

            /* Sidebar */
            section[data-testid="stSidebar"] {{ background-color: {COMPONENT_BG_COLOR} !important; }}
            section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
            section[data-testid="stSidebar"] label {{ color: {COMPONENT_TEXT_COLOR} !important; }}
        </style>
        <style>
            /* Forzar color de texto oscuro para elementos de texto dentro de gráficas Plotly */
            /* Esto es para anular la regla general que podría estar poniendo el texto en blanco */
            .plot-container .svg-container text,
            .plot-container .svg-container tspan {{ /* tspan es usado por Plotly para saltos de línea en texto */
                fill: {COMPONENT_TEXT_COLOR} !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("🛡️ Protección Digital: la IA Combate el robo de identidad 🕵️")

    # Cargar modelo y BD para Detector de URLs
    modelo_urls = load_model_url_detector(MODEL_FILENAME_URL_DETECTOR)
    conn_urls = get_db_connection_url_detector(DB_FILENAME_URL_DETECTOR)
    conn_reports = get_db_connection_user_reports(DB_FILENAME_USER_REPORTS) # Conexión a la BD de reportes

    # Cambiamos el orden de los títulos y la asignación de las pestañas
    tab_welcome_title = "👋 Bienvenida" # Nueva pestaña de bienvenida
    tab_instagram_title = "Dashboard de Instagram"
    tab_url_detector_title = "Detector de URLs Maliciosas"
    tab_text_analyzer_title = "🕵️ Analizador de Mensajes" # Nueva pestaña
    tab_phishing_simulator_title = "🎣 Simulador de Phishing" # Nueva pestaña
    tab_info_title = "🛡️ Ciberseguridad y Ayuda" # Renombrada y con icono original

    tab_welcome, tab_instagram, tab_url_detector, tab_text_analyzer, tab_phishing_simulator, tab_info = st.tabs([
        tab_welcome_title,
        tab_instagram_title,
        tab_url_detector_title,
        tab_text_analyzer_title,
        tab_phishing_simulator_title,
        tab_info_title
    ])
    
    # --- PESTAÑA 1 (AHORA DETECTOR DE URLS, PERO SE MOSTRARÁ SEGUNDA) ---
    # La lógica de las pestañas se reordenará para que la bienvenida sea la primera

    # --- PESTAÑA DE BIENVENIDA (NUEVA Y PRIMERA) ---
    with tab_welcome:
        st.header("¡Bienvenido/a a Protección Digital!")
        st.markdown("""
            Esta aplicación combina herramientas impulsadas por Inteligencia Artificial para ayudarte a navegar
            el mundo digital de forma más segura y a entender mejor la dinámica en redes sociales.
        """)

        # --- Consejos Dinámicos ---
        st.markdown("---")
        # st.subheader("💡 Consejo de Seguridad del Día") # El toast lo hará más dinámico
        consejos_seguridad = [
            "Nunca compartas tus contraseñas con nadie, ¡ni siquiera con tu mejor amigo! 🤫",
            "Activa la autenticación de dos factores (2FA) siempre que sea posible. ¡Es como ponerle un doble candado a tu puerta! 🛡️",
            "Desconfía de los mensajes urgentes que te piden datos personales o hacer clic en enlaces extraños. 📨❓",
            "Revisa periódicamente los permisos de las aplicaciones conectadas a tus redes sociales. ⚙️✔️",
            "¡Crea contraseñas únicas y fuertes para cada cuenta! Un gestor de contraseñas puede ser tu gran aliado. 🔑💪",
            "Mantén tu sistema operativo, navegador y antivirus actualizados. ¡Las actualizaciones tapan agujeros de seguridad! 🔄💻",
            "Evita ingresar datos sensibles en redes Wi-Fi públicas no seguras. ¡Los hackers podrían estar escuchando! 📶👂"
        ]
        # st.info(random.choice(consejos_seguridad)) # Reemplazado por st.toast

        # Mostrar el consejo del día como un toast cuando se visita la pestaña de bienvenida
        # Se mostrará una vez por sesión de la app gracias al control con st.session_state en el bloque if __name__ == "__main__":
        # Para que se muestre cada vez que se entra a la pestaña (si ya se mostró antes), se podría quitar la condición de session_state aquí
        # y solo depender del botón "Ver otro consejo".
        if st.button("✨ Ver Consejo de Seguridad del Día", key="ver_consejo_bienvenida"):
            st.toast(random.choice(consejos_seguridad), icon="💡")

        st.subheader("📊 Instagram Analyzer: Actividad y Anomalías")
        st.markdown("""
            Explora las estadísticas de perfiles públicos de Instagram. Visualiza la evolución de seguidores,
            publicaciones, y detecta posibles anomalías en su actividad. Esta herramienta también ofrece
            predicciones básicas sobre el crecimiento de seguidores.
            *   **Cómo usar:** Dirígete a la pestaña "Dashboard de Instagram". Selecciona uno o varios perfiles.
                Puedes filtrar los datos por rango de fechas para un análisis más detallado.
        """)

        st.subheader("🔍 Detector de URLs Maliciosas")
        st.markdown("""
            ¿Dudas sobre la seguridad de un enlace? Ingresa la URL y nuestro modelo de IA la analizará para determinar si es potencialmente peligrosa.
            También puedes analizar una lista de URLs en la sección de "Análisis en Lote".
            *   **Cómo usar:** Ve a la pestaña "Detector de URLs Maliciosas", ingresa la URL completa (ej. `https://www.ejemplo.com`) y presiona "Analizar URL", o usa el área de texto para análisis en lote.
        """)


        st.subheader("🕵️ Analizador de Mensajes Sospechosos")
        st.markdown("""
            ¿Recibiste un mensaje o correo que te parece extraño? Pega el texto aquí. Analizaremos su contenido
            en busca de palabras clave comunes en phishing, evaluaremos cualquier URL que contenga y, si proporcionas
            el correo del remitente, verificaremos la coherencia de los dominios.
            *   **Cómo usar:** Ve a la pestaña "Analizador de Mensajes", pega el texto del mensaje, opcionalmente el correo del remitente, y presiona "Analizar Mensaje".
        """)
        # st.info("Este proyecto ha sido desarrollado por Carlos Daniel López Gordillo y Andrea Hernández de la Cruz como parte de un proyecto universitario para la Universidad Nacional Rosario Castellanos.") # Movido a popover

        st.markdown("---")
        with st.popover("ℹ️ Sobre los Autores", use_container_width=False): # use_container_width=False para un popover más pequeño
            st.markdown("""
                Este proyecto ha sido desarrollado por **Carlos Daniel López Gordillo** y **Andrea Hernández de la Cruz** 
                como parte de un proyecto universitario para la Universidad Nacional Rosario Castellanos. ¡Gracias por usar nuestra herramienta! 😊
            """)
    
    # --- PESTAÑA SIMULADOR DE PHISHING ---
    with tab_phishing_simulator:
        st.header(tab_phishing_simulator_title)
        st.markdown("""
            ¡Pon a prueba tus habilidades para detectar intentos de phishing! Te presentaremos algunos escenarios.
            Analiza la información y responde las preguntas para ver si puedes identificar las señales de alerta.
        """)
        st.markdown("---")

        # Definir escenarios de phishing
        escenarios_phishing = [
            {
                "id": 1,
                "titulo": "Escenario 1: Correo del 'Banco'",
                "descripcion": "Recibes el siguiente correo electrónico:",
                "contenido_mensaje": """
                **De:** Soporte Banco XYZ <soporte@banco-xyz-seguridad.com>
                **Asunto:** ALERTA DE SEGURIDAD URGENTE: Actividad sospechosa en su cuenta

                Estimado Cliente,

                Hemos detectado actividad inusual en su cuenta No. ****1234. Por su seguridad, hemos suspendido temporalmente el acceso.
                Para reactivar su cuenta y verificar su identidad, por favor haga clic en el siguiente enlace y complete el formulario:
                [http://banco-xyz-seguridad.com/validacion-cuenta?id=abc123xyz](http://banco-xyz-seguridad.com/validacion-cuenta?id=abc123xyz)

                Si no completa este proceso en las próximas 24 horas, su cuenta será bloqueada permanentemente.

                Gracias,
                Departamento de Seguridad
                Banco XYZ
                """,
                "preguntas": [
                    {"q": "El dominio del remitente 'banco-xyz-seguridad.com' parece legítimo para Banco XYZ.", "opciones": ["Verdadero", "Falso"], "respuesta_correcta": "Falso", "explicacion": "Los bancos suelen usar sus dominios principales (ej. bancoxyz.com). Subdominios largos o con guiones como 'banco-xyz-seguridad.com' son sospechosos."},
                    {"q": "La URL del enlace [http://banco-xyz-seguridad.com/...] es segura porque empieza con 'http'.", "opciones": ["Verdadero", "Falso"], "respuesta_correcta": "Falso", "explicacion": "HTTPS (con 'S') indica una conexión segura, pero no garantiza que el sitio sea legítimo. Además, el dominio en sí es sospechoso."},
                    {"q": "El tono de urgencia ('URGENTE', '24 horas', 'bloqueada permanentemente') es una táctica común de phishing.", "opciones": ["Verdadero", "Falso"], "respuesta_correcta": "Verdadero", "explicacion": "Los atacantes crean un falso sentido de urgencia para que actúes sin pensar."},
                    {"q": "Solicitar que hagas clic en un enlace para 'verificar tu identidad' es un procedimiento estándar de los bancos.", "opciones": ["Verdadero", "Falso"], "respuesta_correcta": "Falso", "explicacion": "Los bancos legítimos raramente te pedirán verificar tu identidad completa o ingresar credenciales a través de un enlace en un correo no solicitado. Es mejor ir directamente al sitio oficial del banco escribiendo la URL en el navegador."}
                ]
            },
            {
                "id": 2,
                "titulo": "Escenario 2: Mensaje de 'Premio Ganado'",
                "descripcion": "Recibes este mensaje de texto en tu celular:",
                "contenido_mensaje": """
                ¡FELICIDADES! Has sido SELECCIONADO para recibir un iPhone 15 Pro GRATIS! 🎁
                Solo tienes que pagar una pequeña tarifa de envío.
                Reclama tu premio aquí: [http://premios-gratis-ya.info/iphone15?claim=xyz789](http://premios-gratis-ya.info/iphone15?claim=xyz789)
                ¡Oferta válida solo por hoy! No te lo pierdas.
                """,
                "preguntas": [
                    {"q": "Ganar un premio costoso sin haber participado en un sorteo es algo común y confiable.", "opciones": ["Verdadero", "Falso"], "respuesta_correcta": "Falso", "explicacion": "Las ofertas que parecen demasiado buenas para ser verdad suelen serlo. Es muy raro ganar premios importantes sin participación previa."},
                    {"q": "La URL 'premios-gratis-ya.info' suena como un sitio oficial para reclamar premios.", "opciones": ["Verdadero", "Falso"], "respuesta_correcta": "Falso", "explicacion": "Dominios genéricos con palabras como 'gratis', 'premios', y TLDs como '.info' o '.biz' son frecuentemente usados en estafas."},
                    {"q": "Pedir una 'pequeña tarifa de envío' para un premio 'gratis' es una señal de alerta.", "opciones": ["Verdadero", "Falso"], "respuesta_correcta": "Verdadero", "explicacion": "Esta es una táctica común para obtener tus datos de pago o simplemente robarte esa 'pequeña tarifa'."}
                ]
            }
            # Puedes añadir más escenarios aquí
        ]

        # Manejo del estado del simulador
        if 'current_scenario_index' not in st.session_state:
            st.session_state.current_scenario_index = 0
            st.session_state.user_answers = {}
            st.session_state.show_feedback = False

        current_index = st.session_state.current_scenario_index

        if current_index < len(escenarios_phishing):
            escenario_actual = escenarios_phishing[current_index]
            st.subheader(escenario_actual["titulo"])
            st.markdown(escenario_actual["descripcion"])
            st.code(escenario_actual["contenido_mensaje"], language="text")

            respuestas_escenario_actual = {}
            for i, pregunta_obj in enumerate(escenario_actual["preguntas"]):
                key = f"q_{escenario_actual['id']}_{i}"
                respuesta_usuario = st.radio(
                    pregunta_obj["q"],
                    options=pregunta_obj["opciones"],
                    key=key,
                    index=None # Para que no haya selección por defecto
                )
                respuestas_escenario_actual[key] = respuesta_usuario
            
            if st.button("Verificar Respuestas", key=f"verify_{escenario_actual['id']}"):
                st.session_state.user_answers[current_index] = respuestas_escenario_actual
                st.session_state.show_feedback = True
                st.rerun() # Volver a ejecutar para mostrar feedback

            if st.session_state.show_feedback and current_index in st.session_state.user_answers:
                st.markdown("---")
                st.subheader("🔍 Retroalimentación:")
                num_correctas = 0
                for i, pregunta_obj in enumerate(escenario_actual["preguntas"]):
                    key = f"q_{escenario_actual['id']}_{i}"
                    respuesta_dada = st.session_state.user_answers[current_index].get(key)
                    es_correcta = respuesta_dada == pregunta_obj["respuesta_correcta"]
                    if es_correcta:
                        num_correctas += 1
                        # st.success(f"**Pregunta:** {pregunta_obj['q']}\n**Tu respuesta:** {respuesta_dada} (¡Correcto! ✅)\n**Explicación:** {pregunta_obj['explicacion']}")
                        st.markdown(
                            f"""
                            <div style="background-color: #28a745; color: white; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                                <strong>Pregunta:</strong> {pregunta_obj['q']}<br>
                                <strong>Tu respuesta:</strong> {respuesta_dada} (¡Correcto! ✅)<br>
                                <strong>Explicación:</strong> {pregunta_obj['explicacion']}
                            </div>
                            """, unsafe_allow_html=True
                        )
                    else:
                        # st.error(f"**Pregunta:** {pregunta_obj['q']}\n**Tu respuesta:** {respuesta_dada} (Incorrecto ❌)\n**Respuesta correcta:** {pregunta_obj['respuesta_correcta']}\n**Explicación:** {pregunta_obj['explicacion']}")
                        st.markdown(
                            f"""
                            <div style="background-color: #dc3545; color: white; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                                <strong>Pregunta:</strong> {pregunta_obj['q']}<br>
                                <strong>Tu respuesta:</strong> {respuesta_dada} (Incorrecto ❌)<br>
                                <strong>Respuesta correcta:</strong> {pregunta_obj['respuesta_correcta']}<br>
                                <strong>Explicación:</strong> {pregunta_obj['explicacion']}
                            </div>
                            """, unsafe_allow_html=True
                        )
                st.info(f"Obtuviste {num_correctas} de {len(escenario_actual['preguntas'])} respuestas correctas en este escenario.") # Mantenemos st.info para el resumen general

                if st.session_state.current_scenario_index < len(escenarios_phishing) - 1:
                    if st.button("Siguiente Escenario ➡️", key=f"next_{escenario_actual['id']}"):
                        st.session_state.current_scenario_index += 1
                        st.session_state.show_feedback = False
                        st.session_state.user_answers = {} # Limpiar respuestas para el nuevo escenario
                        st.rerun()
                else:
                    st.balloons()
                    st.success("¡Felicidades! Has completado todos los escenarios del simulador. 🎉")

                if st.button("Reiniciar Simulador", key="reset_simulator_phishing"):
                    st.session_state.current_scenario_index = 0
                    st.session_state.user_answers = {}
                    st.session_state.show_feedback = False
                    st.rerun()
        else: # Se completaron todos los escenarios (esto es redundante si el botón de siguiente ya lo maneja)
            st.success("¡Has completado todos los escenarios del simulador! Esperamos que hayas aprendido mucho. 👍")
            if st.button("Reiniciar Simulador desde el final", key="reset_from_end_phishing"):
                st.session_state.current_scenario_index = 0
                st.session_state.user_answers = {}
                st.session_state.show_feedback = False
                st.rerun()

    # --- PESTAÑA ANALIZADOR DE MENSAJES ---
    with tab_text_analyzer:
        st.header(tab_text_analyzer_title)
        st.markdown("""
            Pega el contenido de un correo electrónico o mensaje directo que te parezca sospechoso.
            Analizaremos el texto en busca de señales comunes de phishing y evaluaremos cualquier URL que contenga.
        """)
        remitente_email_input = st.text_input("Correo electrónico del remitente (Opcional):", key="remitente_email_input", placeholder="ejemplo@dominio.com")
        mensaje_input = st.text_area("Pega aquí el mensaje sospechoso:", height=250, key="mensaje_sospechoso_area",
                                     placeholder="Ej: Estimado cliente, hemos detectado actividad inusual en su cuenta. Por favor, verifique sus datos en https://sitio-falso.com/login para evitar la suspensión.")

        if st.button("Analizar Mensaje", key="analizar_mensaje_button"):
            if mensaje_input:
                with st.spinner("Analizando mensaje..."):
                    indicadores_texto, urls_info, puntuacion, riesgo = analizar_texto_sospechoso(
                        mensaje_input, remitente_email_input.strip(), modelo_urls, conn_urls
                    )
                
                st.subheader(f"Evaluación General del Mensaje:")
                st.metric(label="Nivel de Riesgo Estimado", value=riesgo, delta=f"{puntuacion} Puntos de Sospecha",
                          delta_color="inverse" if riesgo == "Alto" else ("normal" if riesgo == "Medio" else "off"))
                st.subheader("Resultados del Análisis del Texto:")
                for indicador in indicadores_texto:
                    if "⚠️" in indicador:
                        st.warning(indicador)
                    elif "✅" in indicador:
                        st.success(indicador)
                    else:
                        st.info(indicador)
                if not indicadores_texto: # Si la lista de indicadores está vacía después del análisis
                        st.info(indicador)

                if urls_info:
                    st.subheader("Análisis de URLs encontradas en el mensaje:")
                    df_urls_mensaje = pd.DataFrame(urls_info)
                    st.dataframe(df_urls_mensaje, use_container_width=True)
            else:
                st.warning("Por favor, ingresa un mensaje para analizar.")
            
            st.markdown("---")
            with st.expander("📬 Reportar este mensaje como sospechoso (para revisión interna)"):
                st.caption("Este reporte es anónimo y nos ayuda a mejorar la herramienta. No es un reporte oficial a autoridades.")
                comentario_reporte_msg = st.text_area("Comentario adicional (opcional):", key="report_msg_comment")
                if st.button("Enviar Reporte del Mensaje", key="send_report_msg_button"):
                    if mensaje_input: # Solo reportar si hay un mensaje analizado
                        guardar_reporte_usuario(conn_reports, "Mensaje", mensaje_input, comentario_reporte_msg)
                        st.success("¡Gracias! Tu reporte ha sido enviado para revisión interna.")
                    else:
                        st.warning("No hay mensaje para reportar. Por favor, analiza un mensaje primero.")

    # --- PESTAÑA DETECTOR DE URLS ---
    with tab_url_detector:
        if not modelo_urls:
            st.error("El detector de URLs no puede funcionar sin su modelo. Verifica el archivo " + MODEL_FILENAME_URL_DETECTOR)
        else:
            st.header(tab_url_detector_title) # <--- CORRECCIÓN AQUÍ
            st.markdown("Introduce una URL para determinar si es potencialmente segura o maliciosa.")
            url_input = st.text_input("Ingresa la URL a analizar:", placeholder="Ej: https://www.ejemplo.com", key="url_detector_input")
            if st.button("Analizar URL", key="analyze_url_button"):
                if url_input:
                    with st.spinner("Analizando URL..."):
                        prob, clasificacion, explicacion = analizar_y_registrar_url(url_input, modelo_urls, conn_urls)
                    if prob is not None:
                        st.subheader("Resultado del Análisis:")
                        prob_porcentaje = prob * 100
                        if clasificacion == "maliciosa":
                            # st.error(f"**Clasificación:** {clasificacion.capitalize()} (Probabilidad: {prob_porcentaje:.2f}%)")
                            # Replace st.error with custom HTML
                            st.markdown(f"""
                            <div style="background: white; color: black; padding: 12px; border: 1px solid #ccc; border-radius: 4px; margin: 10px 0;">
                                <strong>Clasificación:</strong> {clasificacion.capitalize()} (Probabilidad: {prob_porcentaje:.2f}%)
                            </div>
                            """, unsafe_allow_html=True)
                            
                            with st.expander("🚨 ¡URL Peligrosa! ¿Qué hacer ahora?", expanded=True):
                                st.markdown("""
                                *   **NO hagas clic** en el enlace si aún no lo has hecho.
                                *   **NO ingreses información personal** o credenciales en ese sitio.
                                *   Si recibiste este enlace por mensaje o correo, **no respondas** y considera **bloquear al remitente**.
                                *   Puedes **reportar el enlace** a plataformas como [Google Safe Browsing](https://safebrowsing.google.com/safebrowsing/report_phish/) o al servicio donde lo encontraste.
                                *   Si ya interactuaste con el sitio, **cambia tus contraseñas** inmediatamente, especialmente si usaste alguna en ese sitio. Monitorea tus cuentas por actividad sospechosa.
                                """)
                        else: 
                            # Replace st.success with custom HTML
                            st.markdown(f"""
                            <div style="background: white; color: black; padding: 12px; border: 1px solid #ccc; border-radius: 4px; margin: 10px 0;">
                                <strong>Clasificación:</strong> {clasificacion.capitalize()} (Probabilidad: {prob_porcentaje:.2f}%)
                            </div>
                            """, unsafe_allow_html=True)
                        
                        st.markdown("**Detalles:**")
                        if explicacion: # Asegurarse de que explicacion no sea None o esté vacía
                            for item in explicacion:
                                tooltip_text = item.get("tooltip")
                                if "⚠️" in item["text"]:
                                    st.warning(item["text"])
                                else:
                                    st.success(item["text"])
                                
                                if tooltip_text: # Si hay tooltip, mostrarlo como caption
                                    st.caption(tooltip_text)
                    else:
                        for item in explicacion: st.warning(item)
                else:
                    st.warning("Por favor, ingresa una URL.")
            st.markdown("---")
            st.subheader("🔬 Análisis en Lote de URLs")
            urls_batch_input = st.text_area("Ingresa múltiples URLs (una por línea):", height=150, key="urls_batch_area")
            if st.button("Analizar Lote de URLs", key="analyze_batch_urls_button"):
                if urls_batch_input:
                    urls_to_analyze = [url.strip() for url in urls_batch_input.split("\n") if url.strip()]
                    if urls_to_analyze:
                        results_batch = []
                        with st.spinner(f"Analizando {len(urls_to_analyze)} URLs..."):
                            for single_url in urls_to_analyze:
                                prob, clasificacion, _ = analizar_y_registrar_url(single_url, modelo_urls, conn_urls) # Ignoramos la explicación detallada para el resumen
                                if prob is not None:
                                    results_batch.append({
                                        "URL": single_url,
                                        "Clasificación": clasificacion.capitalize(),
                                        "Prob. Maliciosa (%)": round(prob * 100, 2)
                                    })
                                else:
                                    results_batch.append({
                                        "URL": single_url,
                                        "Clasificación": "Error de análisis",
                                        "Prob. Maliciosa (%)": "N/A"
                                    })
                        st.dataframe(pd.DataFrame(results_batch))
                    else:
                        st.warning("No se ingresaron URLs válidas para el análisis en lote.")
                else:
                    st.warning("Por favor, ingresa una URL.")
            
            st.markdown("---")
            with st.expander("📬 Reportar URL analizada como sospechosa (para revisión interna)"):
                st.caption("Este reporte es anónimo y nos ayuda a mejorar la herramienta. No es un reporte oficial a autoridades.")
                url_a_reportar = st.text_input("URL a reportar (si es diferente a la última analizada individualmente):", value=url_input if url_input else "", key="report_url_input")
                comentario_reporte_url = st.text_area("Comentario adicional (opcional):", key="report_url_comment")
                if st.button("Enviar Reporte de URL", key="send_report_url_button"):
                    if url_a_reportar:
                        guardar_reporte_usuario(conn_reports, "URL", url_a_reportar, comentario_reporte_url)
                        st.success("¡Gracias! Tu reporte ha sido enviado para revisión interna.")
                    else:
                        st.warning("Por favor, ingresa una URL para reportar.")
            st.markdown("---")
            col_hist, col_sum = st.columns(2)
            with col_hist:
                st.subheader("Historial Reciente (URLs)")
                historial_data = obtener_historial_urls(conn_urls)
                if historial_data:
                    df_historial = pd.DataFrame(historial_data, columns=["URL", "Clasificación", "Prob. Maliciosa", "Fecha"])
                    df_historial["Prob. Maliciosa"] = (df_historial["Prob. Maliciosa"] * 100).map('{:.2f}%'.format)
                    st.dataframe(df_historial, height=300, use_container_width=True)
                else: st.info("No hay historial de URLs.")
            with col_sum:
                st.subheader("Resumen Clasificaciones (URLs)")
                resumen_data = obtener_resumen_clasificacion_urls(conn_urls)
                if resumen_data:
                    df_resumen = pd.DataFrame(resumen_data, columns=["Clasificación", "Cantidad"])
                    st.dataframe(df_resumen, use_container_width=True)
                    if INSTAGRAM_MODULES_LOADED: # Reutilizar plotly si está cargado
                        fig = px.pie(df_resumen, names='Clasificación', values='Cantidad', title='Distribución de Clasificaciones de URLs', hole=.3)
                        # Asegurar fondo blanco explícitamente para esta gráfica
                        fig.update_layout(paper_bgcolor='white', plot_bgcolor='white')
                        fig.update_layout(
                            template=GRAPH_TEMPLATE, # Usar template de gráfica (siempre claro)
                            font_color=COMPONENT_TEXT_COLOR, 
                            legend_font_color=COMPONENT_TEXT_COLOR,
                            title_font_color=COMPONENT_TEXT_COLOR, # Asegurar color del título
                            xaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR), # Ejes
                            yaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR)  # Ejes
                        )
                        # Para el texto DENTRO de los slices, blanco puede ser mejor sobre colores oscuros
                        fig.update_traces(textposition='inside', textinfo='percent+label', textfont_color=PRIMARY_TEXT_COLOR, 
                                          marker=dict(line=dict(color=COMPONENT_TEXT_COLOR, width=1))) # Borde para los slices
                        st.plotly_chart(fig, use_container_width=True)
                else: st.info("No hay datos para el resumen.")

        # El Aviso de Privacidad se moverá al final de la app, fuera de las pestañas.
    # --- PESTAÑA DASHBOARD DE INSTAGRAM ---
    with tab_instagram:
        # st.header(tab_instagram_title) # Eliminamos esta línea

        if not INSTAGRAM_MODULES_LOADED:
            st.error(f"No se pudieron cargar los módulos necesarios para el Dashboard de Instagram: {INSTAGRAM_IMPORT_ERROR}")
            st.warning("Asegúrate de que la carpeta 'instagram_analyzer' esté presente y que todas las dependencias (incluyendo 'statsmodels') estén instaladas desde 'requirements.txt'.")
            st.stop()

        # st.sidebar.image(LOGO_PATH_INSTAGRAM, width=150, caption="Instagram Analyzer") # Logo eliminado
        # st.sidebar.markdown("---") # Eliminamos el único elemento que quedaba en la sidebar

        st.markdown("<div class='big-font'>📊 Instagram Analyzer: Actividad y Anomalías</div>", unsafe_allow_html=True)
        st.markdown("Análisis visual de perfiles públicos: publicaciones, seguidores y seguidos.")

        # --- CARGA DE DATOS (del dashboard de Instagram) ---
        try:
            conn_insta = sqlite3.connect(DB_PATH_INSTAGRAM)
            # Asegúrate de seleccionar las nuevas columnas
            df_insta = pd.read_sql_query("""
                SELECT id, usuario, fecha, publicaciones, seguidores, seguidos, 
                       anomalia_descripcion, evaluacion_riesgo_desc, evaluacion_riesgo_nivel 
                FROM estadisticas
            """, conn_insta)
            conn_insta.close()
        except Exception as e:
            st.error(f"Error al conectar o leer la base de datos de Instagram ({DB_PATH_INSTAGRAM}): {e}")
            st.warning("Asegúrate de que el archivo de base de datos exista y sea accesible. Ejecuta el scraper si es necesario.")
            st.stop()


        if df_insta.empty:
            st.warning("⚠️ No hay datos en la base de datos de Instagram. Ejecuta el scraper primero.")
            st.stop()

        # --- Procesamiento de datos de Instagram ---
        cols_to_process_insta = ["publicaciones", "seguidores", "seguidos"]
        for col_name in cols_to_process_insta:
            if col_name in df_insta.columns:
                # Si la columna ya es numérica (porque generate_synthetic_data.py la limpió),
                # simplemente asegúrate de que sea de tipo int.
                if pd.api.types.is_numeric_dtype(df_insta[col_name]):
                    df_insta[col_name] = df_insta[col_name].fillna(0).astype(int) # Rellenar NaNs con 0 antes de convertir a int
                # Si es de tipo string (datos originales del scraper o si generate_synthetic_data no se ejecutó/falló),
                # entonces aplica la función `convertir_numero` que se supone maneja formatos como '1.2k', '150 seguidores', etc.
                elif pd.api.types.is_string_dtype(df_insta[col_name]):
                    df_insta[col_name] = df_insta[col_name].apply(convertir_numero).fillna(0).astype(int)
                # Si es de tipo 'object' pero no string (podría ser una mezcla o contener NaNs),
                # intenta convertir a string primero y luego aplicar `convertir_numero`.
                # Esto es para cubrir casos donde la columna es 'object' pero no estrictamente 'string'.
                else:
                    df_insta[col_name] = df_insta[col_name].astype(str).apply(convertir_numero).fillna(0).astype(int)
            else: # Si la columna no existe, crearla con ceros para evitar errores posteriores
                df_insta[col_name] = 0
        
        df_insta["fecha"] = pd.to_datetime(df_insta["fecha"])
        
        df_insta_latest = df_insta.sort_values("fecha").groupby("usuario").tail(1)

        # Inicializar variables que podrían ser definidas en la sidebar
        # para que existan incluso si la sección de la sidebar no se renderiza.
        usuario_insta = None
        perfil_df_insta = pd.DataFrame()
        perfil_df_insta_filtered = pd.DataFrame()
        date_range_val_insta = None # Inicializar para resolver UnboundLocalError

        # --- SIDEBAR (elementos del dashboard de Instagram) --- 
        # Los elementos de la sidebar se han movido dentro de la pestaña.
        # Aquí solo mantenemos la lógica de la sidebar que no es específica de Instagram, si la hubiera.
        # Por ahora, la sidebar solo tiene el markdown "---" si los módulos de Instagram no están cargados.
        # Si los módulos están cargados, los filtros se mostrarán DENTRO de la pestaña.

        # --- FILTROS DENTRO DE LA PESTAÑA DE INSTAGRAM ---
        if INSTAGRAM_MODULES_LOADED and not df_insta.empty:
            col_filtro1, col_filtro2 = st.columns(2) # Columnas parejas para organizar los filtros
            with col_filtro1:
                available_users_insta = df_insta_latest["usuario"].unique()
                selected_users_insta = st.multiselect( # Cambiado a multiselect
                    "👤 Selecciona Perfil(es) de Instagram:",
                    available_users_insta,
                    default=list(available_users_insta[:1]) if available_users_insta.any() else [], # Selecciona el primero por defecto si hay
                    key="sb_select_user_insta"
                )
                usuario_insta = selected_users_insta[0] if selected_users_insta else None # Para mantener compatibilidad con lógica existente de un solo perfil

            # La lógica para definir perfil_df_insta y perfil_df_insta_filtered
            # se basa en usuario_insta, que se define aquí dentro de la pestaña.
            if usuario_insta: # Solo proceder si se seleccionó un usuario
                perfil_df_insta = df_insta[df_insta["usuario"] == usuario_insta].sort_values("fecha")
                if not perfil_df_insta.empty:
                    perfil_df_insta["ratio_seguidores_seguidos"] = perfil_df_insta.apply(
                        lambda row: row["seguidores"] / row["seguidos"] if row["seguidos"] > 0 else 0, axis=1
                    )
                    # Establecer un valor inicial para date_range_val_insta basado en el perfil actual
                    min_date_profile_insta = perfil_df_insta["fecha"].min().date()
                    max_date_profile_insta = perfil_df_insta["fecha"].max().date()
                    date_range_val_insta = (min_date_profile_insta, max_date_profile_insta)

                    with col_filtro2: # Colocar el date_input en la segunda columna
                        # st.markdown("#### 📅 Rango de Fechas") # Título opcional, la etiqueta del date_input puede ser suficiente
                        # min_date_profile_insta y max_date_profile_insta ya están definidos arriba

                        if len(perfil_df_insta) < 2 or min_date_profile_insta == max_date_profile_insta:
                            st.info("Mostrando todos los datos (rango no aplicable).")
                            perfil_df_insta_filtered = perfil_df_insta
                        else:
                            date_range_val_insta = st.date_input(
                                "📅 Rango de fechas:", # Etiqueta ajustada y con icono
                                value=date_range_val_insta, # Usar el rango completo del perfil como valor inicial
                                min_value=min_date_profile_insta,
                                max_value=max_date_profile_insta,
                                key=f"date_range_insta_{usuario_insta}" # Clave única
                            )
                            # La variable date_range_val_insta ahora contiene la selección del usuario
                            # o el valor por defecto si el input no devuelve algo válido (raro para date_input)

                        # Filtrar perfil_df_insta_filtered basado en el date_range_val_insta final
                        if date_range_val_insta and len(date_range_val_insta) == 2:
                            start_date_dt_insta = pd.to_datetime(date_range_val_insta[0])
                            end_date_dt_insta = pd.to_datetime(date_range_val_insta[1]).replace(hour=23, minute=59, second=59)
                            perfil_df_insta_filtered = perfil_df_insta[
                                (perfil_df_insta["fecha"] >= start_date_dt_insta) & (perfil_df_insta["fecha"] <= end_date_dt_insta)
                            ]
                        else:
                            # Si date_range_val_insta no es válido (no debería pasar con la lógica actual),
                            # mostrar todos los datos del perfil.
                            perfil_df_insta_filtered = perfil_df_insta
                else: # perfil_df_insta está vacío
                    perfil_df_insta_filtered = perfil_df_insta # También será vacío
                    # Si el perfil individual no tiene datos, pero hay datos globales, usar el rango global
                    if not df_insta.empty:
                        date_range_val_insta = (df_insta["fecha"].min().date(), df_insta["fecha"].max().date()) # Corrected indent for the block below
                        if date_range_val_insta and len(date_range_val_insta) == 2:
                            start_date_dt_insta = pd.to_datetime(date_range_val_insta[0])
                            end_date_dt_insta = pd.to_datetime(date_range_val_insta[1]).replace(hour=23, minute=59, second=59)
                            perfil_df_insta_filtered = df_insta[
                                (df_insta["fecha"] >= start_date_dt_insta) & (df_insta["fecha"] <= end_date_dt_insta)
                            ]
        
        # else:
            # Si INSTAGRAM_MODULES_LOADED es False o df_insta está vacío,
            # usuario_insta, perfil_df_insta, y perfil_df_insta_filtered
            # mantendrán sus valores inicializados (None y DataFrames vacíos).

        if usuario_insta is None : # Si no hay usuarios o no se seleccionó
             st.warning("Por favor, selecciona al menos un perfil de Instagram para ver el análisis.")
             st.stop()
        if not selected_users_insta or perfil_df_insta.empty and len(selected_users_insta) == 1: # Ajustar condición para multiselect
            st.warning(f"⚠️ No hay datos históricos para el/los perfil(es) seleccionado(s) o no se seleccionó ninguno.")
            st.stop()

        # --- KPIs Y CAMBIOS (Instagram) ---
        st.markdown(f"### 📌 Últimos datos y cambios para: @{usuario_insta}")
        latest_data_insta = perfil_df_insta.iloc[-1]
        previous_data_insta = perfil_df_insta.iloc[-2] if len(perfil_df_insta) > 1 else None
        
        # Los KPIs se mostrarán solo si se selecciona un único perfil, para simplificar.
        if len(selected_users_insta) == 1:
            col1_i, col2_i, col3_i, col4_i = st.columns(4)
            pub_delta_i = int(latest_data_insta["publicaciones"] - previous_data_insta["publicaciones"]) if previous_data_insta is not None else None
            seg_delta_i = int(latest_data_insta["seguidores"] - previous_data_insta["seguidores"]) if previous_data_insta is not None else None
            segdos_delta_i = int(latest_data_insta["seguidos"] - previous_data_insta["seguidos"]) if previous_data_insta is not None else None
            ratio_actual_i = latest_data_insta["ratio_seguidores_seguidos"]
            ratio_anterior_i = previous_data_insta["ratio_seguidores_seguidos"] if previous_data_insta is not None else None
            ratio_delta_i = (ratio_actual_i - ratio_anterior_i) if previous_data_insta is not None else None

            col1_i.metric("Publicaciones", int(latest_data_insta["publicaciones"]), delta=pub_delta_i, delta_color="normal" if pub_delta_i is None else ("inverse" if pub_delta_i < 0 else "normal"))
            col2_i.metric("Seguidores", int(latest_data_insta["seguidores"]), delta=seg_delta_i, delta_color="normal" if seg_delta_i is None else ("inverse" if seg_delta_i < 0 else "normal"))
            col3_i.metric("Seguidos", int(latest_data_insta["seguidos"]), delta=segdos_delta_i, delta_color="normal" if segdos_delta_i is None else ("inverse" if segdos_delta_i < 0 else "normal"))
            col4_i.metric("Ratio Sgs/Sdos", f"{ratio_actual_i:.2f}", delta=f"{ratio_delta_i:.2f}" if ratio_delta_i is not None else None, delta_color="normal" if ratio_delta_i is None else ("inverse" if ratio_delta_i < 0 else "normal"))
        else:
            st.info("Selecciona un único perfil para ver los KPIs detallados y cambios.")

        # --- GRÁFICAS (Instagram) ---
        if selected_users_insta:
            st.markdown(f"### 📈 Evolución histórica para @{', @'.join(selected_users_insta)}")
            
            # Gráfico comparativo de seguidores
            fig_followers_comparison = go.Figure()

            # Determinar el rango de fechas para el gráfico comparativo
            filter_start_date_comp, filter_end_date_comp = None, None

            if date_range_val_insta and len(date_range_val_insta) == 2:
                filter_start_date_comp = pd.to_datetime(date_range_val_insta[0])
                filter_end_date_comp = pd.to_datetime(date_range_val_insta[1]).replace(hour=23, minute=59, second=59)
            elif not df_insta.empty: # Fallback al rango global de df_insta
                filter_start_date_comp = pd.to_datetime(df_insta["fecha"].min())
                filter_end_date_comp = pd.to_datetime(df_insta["fecha"].max()).replace(hour=23, minute=59, second=59)

            if filter_start_date_comp is None or filter_end_date_comp is None:
                st.warning("No se pudo determinar el rango de fechas para el gráfico comparativo.")
            else:
                for user_to_plot in selected_users_insta:
                    # Usar un nombre de variable diferente para el DataFrame filtrado aquí para evitar confusiones
                    user_comp_df_filtered = df_insta[
                        (df_insta["usuario"] == user_to_plot) &
                        (df_insta["fecha"] >= filter_start_date_comp) &
                        (df_insta["fecha"] <= filter_end_date_comp)
                    ].sort_values("fecha")

                    if not user_comp_df_filtered.empty and len(user_comp_df_filtered) >= 1:
                        trace_config = {
                            "x": user_comp_df_filtered["fecha"],
                            "y": user_comp_df_filtered["seguidores"],
                            "mode": 'lines+markers',
                            "name": f"Seguidores @{user_to_plot}",
                            "hovertemplate": '<b>Fecha</b>: %{x|%Y-%m-%d}<br><b>Seguidores @'+user_to_plot+'</b>: %{y:,.0f}<extra></extra>',
                        }
                        if len(selected_users_insta) == 1:
                            trace_config['line'] = dict(color=INSTA_GRAPH_LINE_PRIMARY)
                        fig_followers_comparison.add_trace(go.Scatter(**trace_config))
                
                if fig_followers_comparison.data: # Solo mostrar si se añadieron trazas
                    fig_followers_comparison.update_layout(
                        title_text="Comparativa de Evolución de Seguidores",
                        template=GRAPH_TEMPLATE,
                        paper_bgcolor='white',
                        plot_bgcolor='white',
                        font_color=COMPONENT_TEXT_COLOR,
                        legend_font_color=COMPONENT_TEXT_COLOR,
                        title_font_color=COMPONENT_TEXT_COLOR, # Asegurar color del título
                        hoverlabel=dict(bgcolor="white", font=dict(color=COMPONENT_TEXT_COLOR)),
                        showlegend=True, 
                        hovermode='x unified',
                        xaxis_title="Fecha",
                        xaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR),
                        yaxis_title="Nº de Seguidores",
                        yaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR)
                    )
                    st.plotly_chart(fig_followers_comparison, use_container_width=True)
                else:
                    st.info("No hay datos para mostrar en el gráfico comparativo con los filtros y rango de fechas actuales.")

            # Si solo se selecciona un perfil, mostrar los gráficos detallados como antes
            if len(selected_users_insta) == 1 and not perfil_df_insta_filtered.empty and len(perfil_df_insta_filtered) > 1:
                # (Aquí iría el código de los subplots que tenías para un solo perfil,
                #  asegurándote de que usa perfil_df_insta_filtered)
                st.markdown(f"#### Detalles de Evolución para @{selected_users_insta[0]}")
                
                # Subplots para Publicaciones, Seguidos, Ratio
                metrics_to_plot_i = ["publicaciones", "seguidos", "ratio_seguidores_seguidos"]
                ylabels_i = ["Nº Publicaciones", "Nº Seguidos", "Ratio Seguidores/Seguidos"]
                fig_subplots = make_subplots(
                    rows=len(metrics_to_plot_i), cols=1, 
                    subplot_titles=[f"Evolución de {m.replace('_', ' ').capitalize()}" for m in metrics_to_plot_i], 
                    vertical_spacing=0.1
                )

                for i, metric in enumerate(metrics_to_plot_i):
                    fig_subplots.add_trace(
                        go.Scatter(
                            x=perfil_df_insta_filtered["fecha"], 
                            y=perfil_df_insta_filtered[metric], 
                            mode='lines+markers', 
                            name=metric.replace('_', ' ').capitalize(),
                            line=dict(color=INSTA_GRAPH_LINE_PRIMARY),
                            hovertemplate='<b>Fecha</b>: %{x|%Y-%m-%d}<br><b>'+metric.replace('_', ' ').capitalize()+'</b>: %{y:,.2f}<extra></extra>'
                        ), 
                        row=i+1, col=1
                    )
                    fig_subplots.update_yaxes(title_text=ylabels_i[i], row=i+1, col=1, title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR)
                    fig_subplots.update_xaxes(row=i+1, col=1, tickfont_color=COMPONENT_TEXT_COLOR)

                fig_subplots.update_layout(
                    height=300 * len(metrics_to_plot_i), 
                    title_text=f"Métricas de Evolución Detallada para @{selected_users_insta[0]}", 
                    showlegend=False, 
                    template=GRAPH_TEMPLATE, 
                    font_color=COMPONENT_TEXT_COLOR,
                    title_font_color=COMPONENT_TEXT_COLOR,
                    paper_bgcolor='white',
                    plot_bgcolor='white',
                    hoverlabel=dict(bgcolor="white", font=dict(color=COMPONENT_TEXT_COLOR))
                )
                st.plotly_chart(fig_subplots, use_container_width=True)

                # Gráfica de Crecimiento Diario de Seguidores
                perfil_df_insta_filtered['crecimiento_diario_seguidores'] = perfil_df_insta_filtered['seguidores'].diff().fillna(0)
                fig_daily_growth = px.bar(
                    perfil_df_insta_filtered, 
                    x='fecha', 
                    y='crecimiento_diario_seguidores',
                    title=f"Crecimiento Diario de Seguidores para @{selected_users_insta[0]}",
                    labels={'fecha': 'Fecha', 'crecimiento_diario_seguidores': 'Cambio en Seguidores'},
                    color_discrete_sequence=[INSTA_GRAPH_LINE_PRIMARY]
                )
                fig_daily_growth.update_layout(template=GRAPH_TEMPLATE, font_color=COMPONENT_TEXT_COLOR, title_font_color=COMPONENT_TEXT_COLOR, paper_bgcolor='white', plot_bgcolor='white', xaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR), yaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR), hoverlabel=dict(bgcolor="white", font=dict(color=COMPONENT_TEXT_COLOR)))
                st.plotly_chart(fig_daily_growth, use_container_width=True)

            elif len(selected_users_insta) > 1:  # Si hay más de un perfil seleccionado
                st.info("Para ver la evolución detallada de publicaciones, seguidos y ratio, selecciona un único perfil.")

        elif not selected_users_insta:
            st.info("Selecciona al menos un perfil para ver la evolución histórica.")

        # --- COMPARATIVA ENTRE PERFILES (Instagram) ---
        st.markdown("### 📊 Comparativa entre perfiles de Instagram (último registro)")
        metric_to_compare_options_i = ("seguidores", "publicaciones", "seguidos")
        metric_to_compare_i = st.selectbox("Selecciona la métrica para comparar (Instagram):", metric_to_compare_options_i, key="compare_metric_insta")
        fig_compare_i = px.bar(
            df_insta_latest.sort_values(metric_to_compare_i, ascending=False),
            x="usuario",
            y=metric_to_compare_i,
            title=f"{metric_to_compare_i.capitalize()} por perfil",
            labels={'usuario': 'Perfil', metric_to_compare_i: f"Nº de {metric_to_compare_i}"},
            color_discrete_sequence=INSTA_GRAPH_BAR_COLOR,  # Usar color de barra para gráficas
            text_auto=True)
        fig_compare_i.update_layout(
            template=GRAPH_TEMPLATE, # Usar template de gráfica (siempre claro)
            paper_bgcolor='white',
            plot_bgcolor='white',
            font_color=COMPONENT_TEXT_COLOR,
            title_font_color=COMPONENT_TEXT_COLOR,
            legend_font_color=COMPONENT_TEXT_COLOR,
            hoverlabel=dict(bgcolor="white", font=dict(color=COMPONENT_TEXT_COLOR)), 
            xaxis_title="Perfil",
            xaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR),
            yaxis_title=f"Nº de {metric_to_compare_i.capitalize()}",
            yaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR),
            showlegend=False
        )
        fig_compare_i.update_xaxes(tickangle=45)
        fig_compare_i.update_traces(textfont_color=COMPONENT_TEXT_COLOR) # Para los números en las barras (text_auto=True)
        st.plotly_chart(fig_compare_i, use_container_width=True)

        # --- TABLA FINAL (Instagram) ---
        if len(selected_users_insta) == 1: # Mostrar tabla y descarga solo para un perfil
            st.markdown(f"### 📋 Tabla completa de registros para @{usuario_insta}")
            st.dataframe(perfil_df_insta.style.format({"publicaciones": "{:.0f}", "seguidores": "{:.0f}", "seguidos": "{:.0f}", "ratio_seguidores_seguidos": "{:.2f}"}).set_properties(**{"text-align": "left"}).hide(axis="index"), use_container_width=True)
            csv_data_i = perfil_df_insta_filtered.to_csv(index=False).encode('utf-8')
            st.download_button(label=f"📥 Descargar datos de @{usuario_insta} (CSV)", data=csv_data_i, file_name=f"{usuario_insta}_instagram_data.csv", mime="text/csv", key=f"download_insta_{usuario_insta}")

        # --- SECCIÓN DE ANOMALÍAS (Instagram) ---
        if len(selected_users_insta) == 1: # Mostrar anomalías solo para un perfil
            st.markdown(f"### ⚠️ Registros con Anomalías Detectadas para @{usuario_insta}")
            
            # Preparar DataFrame para mostrar anomalías y evaluación de riesgo
            # Tomamos el registro más reciente del perfil filtrado para mostrar la última evaluación de riesgo
            latest_profile_record_filtered = perfil_df_insta_filtered.sort_values(by="fecha", ascending=False).head(1)
            
            riesgo_desc_mostrar = "No disponible"
            riesgo_nivel_mostrar = "No evaluado"
            if not latest_profile_record_filtered.empty:
                riesgo_desc_mostrar = latest_profile_record_filtered['evaluacion_riesgo_desc'].iloc[0]
                riesgo_nivel_mostrar = latest_profile_record_filtered['evaluacion_riesgo_nivel'].iloc[0]

            st.info(f"**Evaluación de Riesgo del Perfil (@{usuario_insta}):** Nivel **{riesgo_nivel_mostrar}**. {riesgo_desc_mostrar}")

            # Mostrar anomalías en métricas (si las hay)
            anomalies_display_df_i = perfil_df_insta_filtered[perfil_df_insta_filtered['anomalia_descripcion'].notna()].copy() # Usar .copy() para evitar SettingWithCopyWarning
            if not anomalies_display_df_i.empty:
                st.dataframe(anomalies_display_df_i[['fecha', 'publicaciones', 'seguidores', 'seguidos', 'anomalia_descripcion']].sort_values(by="fecha", ascending=False).reset_index(drop=True), use_container_width=True)
            else:
                st.info(f"No se detectaron anomalías para @{usuario_insta} en el rango de fechas seleccionado.")
            
            if not anomalies_display_df_i.empty: # Si hubo anomalías
                with st.expander("⚠️ Se detectaron anomalías. ¿Qué considerar?", expanded=False):
                    st.markdown(f"""
                    Las anomalías pueden tener diversas causas, desde un crecimiento orgánico rápido hasta actividad inusual que podría indicar:
                    *   **Compra de seguidores/interacción falsa:** Cambios abruptos y no sostenidos.
                    *   **Cuenta comprometida (hackeada):** Cambios drásticos en el tipo de contenido (si se pudiera analizar), frecuencia de publicación o en la biografía/nombre (no analizado aquí).
                    *   **Campaña de marketing o evento viral.**
                    Si sospechas que una cuenta es falsa o está comprometida, puedes **reportarla directamente a Instagram** a través de su aplicación o sitio web. No interactúes con contenido sospechoso.
                    """)

            # Histograma de Cambios Diarios de Seguidores (Movido aquí, dentro de la condición de un solo perfil)
            if 'crecimiento_diario_seguidores' in perfil_df_insta_filtered.columns and len(perfil_df_insta_filtered['crecimiento_diario_seguidores']) > 1:
                # Excluir el primer valor si es 0 y fue resultado de .diff().fillna(0) en un solo dato.
                growth_data_for_hist = perfil_df_insta_filtered['crecimiento_diario_seguidores']
                if perfil_df_insta_filtered.iloc[0]['crecimiento_diario_seguidores'] == 0 and len(perfil_df_insta_filtered) > 1:
                    growth_data_for_hist = growth_data_for_hist.iloc[1:]

                if not growth_data_for_hist.empty and not (growth_data_for_hist == 0).all(): # Solo si hay datos y no son todos cero
                    fig_hist_growth = px.histogram(
                        growth_data_for_hist, nbins=20, title=f"Distribución del Cambio Diario de Seguidores para @{usuario_insta}"
                    )
                    fig_hist_growth.update_layout(template=GRAPH_TEMPLATE, font_color=COMPONENT_TEXT_COLOR, title_font_color=COMPONENT_TEXT_COLOR, paper_bgcolor='white', plot_bgcolor='white', xaxis_title="Cambio Diario de Seguidores", yaxis_title="Frecuencia", xaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR), yaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR), hoverlabel=dict(bgcolor="white", font=dict(color=COMPONENT_TEXT_COLOR)))
                    st.plotly_chart(fig_hist_growth, use_container_width=True)

        # --- SECCIÓN DE PREDICCIONES (Instagram) ---
        st.markdown("### 🔮 Predicciones de Seguidores (Statsmodels ARIMA)")
        historical_seguidores_full_i = perfil_df_insta.set_index('fecha')['seguidores'].sort_index()
        if len(selected_users_insta) == 1 and len(historical_seguidores_full_i) >= 10: # Predicciones solo para un perfil
            predictions_table_data_i = generate_predictions(historical_seguidores_full_i, n_future_steps=7)
            if not predictions_table_data_i.empty:
                st.write(f"Predicción de seguidores para @{usuario_insta} en los próximos 7 días:")
                predictions_df_display_i = predictions_table_data_i.reset_index(); predictions_df_display_i.columns = ['Fecha Predicha', 'Seguidores Predichos']
                predictions_df_display_i['Seguidores Predichos'] = predictions_df_display_i['Seguidores Predichos'].astype(int)
                st.dataframe(predictions_df_display_i.style.format({'Fecha Predicha': '{:%Y-%m-%d}', "Seguidores Predichos": "{:,.0f}"}), hide_index=True, use_container_width=True)
                
                # Gráfico de predicciones
                fig_pred = go.Figure()
                fig_pred.add_trace(go.Scatter(x=historical_seguidores_full_i.index, y=historical_seguidores_full_i.values, mode='lines', name='Histórico', line=dict(color=INSTA_GRAPH_LINE_PRIMARY)))
                fig_pred.add_trace(go.Scatter(x=predictions_table_data_i.index, y=predictions_table_data_i.values, mode='lines+markers', name='Predicción', line=dict(color=INSTA_GRAPH_LINE_PRIMARY, dash='dash')))
                fig_pred.update_layout(
                    title_text=f"Predicción de Seguidores para @{usuario_insta}",
                    template=GRAPH_TEMPLATE,
                    paper_bgcolor='white',
                    plot_bgcolor='white',
                    font_color=COMPONENT_TEXT_COLOR,
                    legend_font_color=COMPONENT_TEXT_COLOR,
                    title_font_color=COMPONENT_TEXT_COLOR,
                    hoverlabel=dict(bgcolor="white", font=dict(color=COMPONENT_TEXT_COLOR)),
                    xaxis_title="Fecha",
                    xaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR),
                    yaxis_title="Seguidores",
                    yaxis=dict(title_font_color=COMPONENT_TEXT_COLOR, tickfont_color=COMPONENT_TEXT_COLOR)
                )
                st.plotly_chart(fig_pred, use_container_width=True)

            else: st.info(f"No se pudieron generar predicciones para @{usuario_insta} (modelo no cargado o datos insuficientes).")
        else: st.info(f"No hay suficientes datos históricos para @{usuario_insta} para generar predicciones.")
        
        # El Aviso de Privacidad se moverá al final de la app, fuera de las pestañas.
        
    # --- PESTAÑA CIBERSEGURIDAD Y AYUDA ---
    with tab_info:
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
        *   🔄 **Software Siempre Actualizado:** Mantén tu sistema operativo, navegador y la app de Instagram al día. ¡Las actualizaciones tapan agujeros de seguridad!
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
                https://www.gob.mx/gncertmx/articulos/ciberseguridad-ciudadana-263949#:~:text=La%20Guardia%20Nacional%2C%20a%20trav%C3%A9s,Suplantaci%C3%B3n%20de%20identidad
        *   **CONDUSEF (Comisión Nacional para la Protección y Defensa de los Usuarios de Servicios Financieros):** Útil si el robo de identidad involucra fraudes financieros.
                    https://www.gob.mx/condusef
        *   **Fiscalía General de la República (FGR) o Fiscalías Estatales:** Para realizar una denuncia formal.
                    https://fgr.org.mx/ 
        """)

    # --- AVISO DE PRIVACIDAD Y LICENCIA (Fuera de las pestañas, al final de la app) ---
    st.markdown("---") 
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
            *   **Licencia:** Este proyecto se distribuye bajo una licencia educativa/académica.
        """)

if __name__ == "__main__":
    if not os.path.exists(MODEL_FILENAME_URL_DETECTOR):
        st.error(f"Error Crítico: El archivo del modelo '{MODEL_FILENAME_URL_DETECTOR}' no se encuentra.")
    else:
        # Inicializar el estado de sesión para el control del toast del consejo
        if 'welcome_toast_shown' not in st.session_state:
            st.session_state.welcome_toast_shown = False

        if not st.session_state.welcome_toast_shown:
            # Definir la lista aquí también o hacerla global si es muy larga para no duplicar
            consejos_para_toast_inicial = ["¡Bienvenido/a a Protección Digital! Recuerda revisar tus configuraciones de privacidad regularmente. 🛡️"] # Puedes usar la lista completa también
            st.toast(random.choice(consejos_para_toast_inicial), icon="👋")
            st.session_state.welcome_toast_shown = True
        main_app()