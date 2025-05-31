# Protección Digital: IA contra el Robo de Identidad y Análisis de Redes

**Autores:** Carlos Daniel López Gordillo, Andrea Hernández de la Cruz
**Institución:** Universidad Nacional Rosario Castellanos (UNRC), Plantel Magdalena Contreras
**Propósito:** Proyecto académico para desarrollar una herramienta multifuncional de ciberseguridad y análisis de datos en redes sociales, utilizando técnicas de Inteligencia Artificial.

## 📜 Descripción General

Este proyecto integra varias herramientas diseñadas para ayudar a los usuarios a navegar el mundo digital de forma más segura y a comprender la dinámica de perfiles en redes sociales (específicamente Instagram). Combina el análisis de datos, la detección de anomalías, la evaluación de riesgos de perfiles, la predicción de tendencias, un detector de URLs maliciosas basado en Machine Learning, un analizador de mensajes sospechosos y un simulador de phishing interactivo.

La aplicación principal está construida con Streamlit, ofreciendo una interfaz de usuario intuitiva para acceder a todas las funcionalidades.

## ✨ Características Principales

1.  **Dashboard de Instagram:**
    *   **Scraping de Datos:** Recopila datos públicos de perfiles de Instagram (publicaciones, seguidores, seguidos, biografía) utilizando Selenium.
    *   **Visualización de Métricas:** Muestra KPIs, gráficos de evolución histórica y comparativas entre perfiles.
    *   **Detección de Anomalías:** Identifica cambios inusuales en las métricas de los perfiles que podrían indicar actividad irregular.
    *   **Evaluación de Riesgo de Perfil:** Analiza características de los perfiles para estimar un nivel de riesgo (Bajo, Medio, Alto) asociado a cuentas falsas o bots.
    *   **Predicción de Seguidores:** Utiliza un modelo ARIMA (a través de `statsmodels`) para predecir la tendencia futura de seguidores.
2.  **Detector de URLs Maliciosas:**
    *   **Modelo de Machine Learning:** Utiliza un modelo XGBoost pre-entrenado (`modelo_xgboost_urls.pkl`) para clasificar URLs como seguras o maliciosas.
    *   **Análisis Individual y en Lote:** Permite analizar una URL individual o una lista de URLs.
    *   **Explicación de Características:** Proporciona detalles sobre por qué una URL podría ser considerada sospechosa (uso de acortadores, TLDs sospechosos, etc.).
    *   **Historial y Resumen:** Guarda un historial de URLs analizadas y muestra un resumen de las clasificaciones.
3.  **Analizador de Mensajes Sospechosos:**
    *   **Detección de Palabras Clave:** Identifica frases y palabras comúnmente usadas en intentos de phishing.
    *   **Análisis de URLs Embebidas:** Extrae y analiza cualquier URL presente en el mensaje utilizando el Detector de URLs.
    *   **Verificación de Dominio del Remitente:** Compara el dominio del correo del remitente (si se proporciona) con los dominios de las URLs en el mensaje.
    *   **Puntuación de Sospecha:** Asigna una puntuación y un nivel de riesgo general al mensaje.
4.  **Simulador de Phishing:**
    *   **Escenarios Interactivos:** Presenta al usuario ejemplos de correos y mensajes de phishing.
    *   **Educación Práctica:** Permite al usuario identificar señales de alerta y recibe retroalimentación inmediata sobre sus respuestas.
5.  **Reporte de Incidentes por Usuarios:**
    *   Permite a los usuarios reportar URLs o mensajes que consideren sospechosos para una revisión interna (simulada, para fines del proyecto).
6.  **Consejos de Ciberseguridad:**
    *   Ofrece información y recomendaciones para prevenir el robo de identidad y proteger cuentas en línea.

## 🛠️ Tecnologías Utilizadas

*   **Lenguaje de Programación:** Python 3.x
*   **Interfaz de Usuario Web:** Streamlit
*   **Web Scraping:** Selenium (con Microsoft Edge Driver)
*   **Análisis de Datos y Manipulación:** Pandas, NumPy
*   **Machine Learning (Detector de URLs):** XGBoost, Scikit-learn (Joblib para cargar el modelo)
*   **Modelado Estadístico (Predicciones Instagram):** Statsmodels (ARIMA)
*   **Visualización de Datos:** Plotly Express, Plotly Graph Objects
*   **Base de Datos:** SQLite3
*   **Manejo de Entorno:** `python-dotenv` para variables de entorno

## ⚙️ Estructura del Proyecto y Procesos de Elaboración

El proyecto se organiza en varios módulos y scripts, cada uno con una responsabilidad específica:

1.  **`streamlit_combined_app.py` (Aplicación Principal):**
    *   **Proceso:** Es el punto de entrada para la interfaz de usuario. Utiliza Streamlit para crear una aplicación web multi-pestaña.
    *   **Elaboración:** Se diseñó una estructura de pestañas para separar las diferentes funcionalidades (Bienvenida, Dashboard de Instagram, Detector de URLs, Analizador de Mensajes, Simulador de Phishing, Información de Ciberseguridad).
    *   Carga los modelos de ML, establece conexiones a las bases de datos SQLite y coordina la interacción del usuario con los módulos de backend.
    *   Implementa la lógica de visualización de datos (gráficos, tablas, métricas) y la presentación de resultados de los análisis.
    *   Se aplicó un diseño visual consistente con CSS personalizado para mejorar la experiencia de usuario.

2.  **Módulo de Scraping (`scraping/scraper.py`):**
    *   **Proceso:** Automatiza la navegación en Instagram para recopilar datos públicos de perfiles.
    *   **Elaboración:**
        *   Utiliza `selenium` para controlar un navegador web (Microsoft Edge).
        *   Implementa funciones para iniciar sesión en Instagram (requiere credenciales de usuario).
        *   Navega a los perfiles especificados y extrae información como número de publicaciones, seguidores, seguidos y la biografía utilizando selectores CSS y XPath.
        *   Maneja esperas implícitas y explícitas para la carga de elementos dinámicos de la página.

3.  **Módulo de Base de Datos (`database/db_handler.py`):**
    *   **Proceso:** Gestiona la persistencia de los datos recopilados y generados.
    *   **Elaboración:**
        *   Utiliza `sqlite3` para interactuar con bases de datos locales.
        *   Define esquemas para varias tablas:
            *   `estadisticas` (en `analisis_instagram.db`): Almacena los datos históricos de perfiles de Instagram, incluyendo métricas, biografía, descripción de anomalías y evaluación de riesgo.
            *   `historial_urls` (en `urls.db`): Guarda las URLs analizadas, su clasificación y probabilidad de ser maliciosas.
            *   `reported_incidents` (en `user_reports.db`): Almacena reportes de URLs y mensajes enviados por los usuarios.
        *   Proporciona funciones para inicializar las bases de datos (`init_db`) y guardar/recuperar datos.

4.  **Módulo de Análisis (`analysis/`):**
    *   **`risk_assessment.py`:**
        *   **Proceso:** Evalúa el riesgo de un perfil de Instagram basándose en heurísticas.
        *   **Elaboración:** Define una función `evaluar_riesgo_perfil` que toma los datos de un perfil y aplica reglas (ej., ratio seguidores/seguidos, número de publicaciones, palabras clave en la biografía) para asignar una puntuación y un nivel de riesgo (Bajo, Medio, Alto).
    *   **`anomaly_detection.py`:**
        *   **Proceso:** Detecta anomalías en las series temporales de las métricas de Instagram.
        *   **Elaboración:** Compara los valores actuales de las métricas con valores anteriores, identificando cambios significativos o desviaciones de patrones esperados (ej., caídas o aumentos bruscos de seguidores).
    *   **`predictor.py` (para Dashboard de Instagram):**
        *   **Proceso:** Genera predicciones a corto plazo para la métrica de seguidores.
        *   **Elaboración:** Utiliza modelos ARIMA de la librería `statsmodels` para ajustarse a los datos históricos de seguidores y proyectar valores futuros.
    *   **Funciones de análisis en `streamlit_combined_app.py` (para Detector de URLs y Analizador de Mensajes):**
        *   `extraer_caracteristicas_url()`: Convierte una URL en un vector de características numéricas (longitud, número de dígitos, presencia de HTTPS, etc.) que el modelo de ML puede entender.
        *   `analizar_y_registrar_url()`: Utiliza el modelo XGBoost cargado para predecir la probabilidad de que una URL sea maliciosa y registra el resultado.
        *   `analizar_texto_sospechoso()`: Procesa un texto en busca de palabras clave de phishing, extrae URLs para su análisis y evalúa la coherencia del dominio del remitente.

5.  **Script de Orquestación del Scraper (`main.py`):**
    *   **Proceso:** Coordina el proceso de scraping de Instagram, la evaluación de riesgo y la detección de anomalías.
    *   **Elaboración:**
        *   Carga credenciales de Instagram desde variables de entorno (`.env`).
        *   Inicializa el driver de Selenium.
        *   Itera sobre una lista de perfiles a scrapear.
        *   Para cada perfil, llama a `obtener_estadisticas()`, luego a `evaluar_riesgo_perfil()`, y guarda los resultados en la base de datos.
        *   Incluye una modificación *ad-hoc* para simular un perfil de riesgo ("tako_de_bistek69") con fines de demostración.
        *   Finalmente, ejecuta `detectar_anomalias()` sobre los datos almacenados.

6.  **Generador de Datos Sintéticos (`generate_synthetic_data.py`):**
    *   **Proceso:** Crea datos históricos sintéticos para perfiles de Instagram, permitiendo tener un historial más largo para demostraciones y pruebas.
    *   **Elaboración:**
        *   Lee los datos existentes de la base de datos.
        *   Para cada perfil, toma el registro más antiguo y genera datos para días anteriores, simulando una disminución gradual de seguidores y publicaciones.
        *   Recrea la tabla `estadisticas` y la rellena con la combinación de datos originales y sintéticos.

7.  **Modelo de Machine Learning (`modelo_xgboost_urls.pkl`):**
    *   **Proceso:** Es un archivo binario que contiene el modelo XGBoost pre-entrenado para la clasificación de URLs.
    *   **Elaboración (externa al código principal del proyecto, pero crucial):** Este modelo se entrenó previamente con un dataset de URLs etiquetadas como seguras o maliciosas, utilizando las características definidas en `extraer_caracteristicas_url()`.

## 🚀 Configuración y Ejecución

1.  **Prerrequisitos:**
    *   Python 3.8 o superior.
    *   `pip` (gestor de paquetes de Python).
    *   Microsoft Edge y el `msedgedriver.exe` correspondiente a tu versión de Edge. Descárgalo aquí y actualiza la ruta en `main.py` (`EDGE_DRIVER_PATH`).

2.  **Clonar el Repositorio (si aplica):**
    ```bash
    git clone <URL_DEL_REPOSITORIO>
    cd <NOMBRE_DEL_REPOSITORIO>
    ```

3.  **Crear un Entorno Virtual (Recomendado):**
    ```bash
    python -m venv venv
    # En Windows
    venv\Scripts\activate
    # En macOS/Linux
    source venv/bin/activate
    ```

4.  **Instalar Dependencias:**
    ```bash
    pip install -r requirements.txt
    ```
    (Asegúrate de tener un archivo `requirements.txt` con todas las librerías: streamlit, pandas, numpy, scikit-learn, xgboost, selenium, python-dotenv, plotly, statsmodels, joblib).

5.  **Configurar Variables de Entorno:**
    *   Crea un archivo llamado `.env` en el directorio raíz del proyecto (`instagram_analyzer`).
    *   Añade tus credenciales de Instagram (se recomienda una cuenta de prueba):
        ```env
        INSTAGRAM_USER="tu_usuario_instagram"
        INSTAGRAM_PASS="tu_contraseña_instagram"
        ```

6.  **Ejecutar el Scraper de Instagram (Opcional, si necesitas datos frescos):**
    *   Este script recopilará datos de los perfiles listados en `main.py` y los guardará en `data/analisis_instagram.db`.
    *   También realizará la evaluación de riesgo y detección de anomalías.
    ```bash
    python main.py
    ```

7.  **Generar Datos Sintéticos (Opcional, para tener más historial):**
    *   Este script tomará los datos existentes (o creará una base vacía si no hay) y añadirá historial sintético.
    ```bash
    python generate_synthetic_data.py
    ```
    *   **Nota:** Este script recrea la tabla `estadisticas`.

8.  **Ejecutar la Aplicación Streamlit:**
    ```bash
    streamlit run streamlit_combined_app.py
    ```
    Esto abrirá la aplicación en tu navegador web.

## 📂 Estructura de Archivos (Simplificada)

```
instagram_analyzer/
├── .env                  # Variables de entorno (CREAR MANUALMENTE)
├── modelo_xgboost_urls.pkl # Modelo de ML para URLs
├── urls.db               # Base de datos para historial de URLs (se crea automáticamente)
├── user_reports.db       # Base de datos para reportes de usuarios (se crea automáticamente)
├── main.py               # Script principal para scraping y análisis de Instagram
├── streamlit_combined_app.py # Aplicación web Streamlit
├── generate_synthetic_data.py # Script para generar datos sintéticos
├── requirements.txt      # Dependencias del proyecto (CREAR)
├── analysis/
│   ├── __init__.py
│   ├── anomaly_detection.py
│   ├── predictor.py
│   └── risk_assessment.py
├── data/
│   └── analisis_instagram.db # Base de datos de Instagram (se crea automáticamente)
├── database/
│   ├── __init__.py
│   └── db_handler.py
├── scraping/
│   ├── __init__.py
│   └── scraper.py
└── utils/
    ├── __init__.py
    └── converters.py
```

## 💡 Posibles Mejoras Futuras

*   Modelos de Machine Learning más avanzados para detección de anomalías y riesgo.
*   Análisis de contenido de publicaciones (texto e imágenes) para una evaluación de riesgo más profunda.
*   Integración con APIs oficiales (si estuvieran disponibles y fueran viables para el alcance).
*   Mejoras en la interfaz de usuario y experiencia (UI/UX).
*   Más opciones de personalización para los análisis.
*   Despliegue de la aplicación en una plataforma en la nube.

## ⚖️ Licencia
Este proyecto se distribuye bajo una licencia educativa/académica con fines de aprendizaje y demostración.