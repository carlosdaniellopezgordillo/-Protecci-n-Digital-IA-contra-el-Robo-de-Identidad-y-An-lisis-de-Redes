import os # <--- Asegúrate de que esta línea esté al principio
import sqlite3
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "analisis_instagram.db")
DATA_DIR = os.path.join(BASE_DIR, "data") # Añadido para consistencia con el código anterior

def init_db():
    """Inicializa la base de datos y la tabla si no existen."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estadisticas (
            fecha TEXT,
            usuario TEXT,
            publicaciones TEXT,
            seguidores TEXT,
            seguidos TEXT,
            biografia TEXT, -- Añadida para consistencia con los datos scrapeados
            anomalia_descripcion TEXT, 
            evaluacion_riesgo_desc TEXT, -- Nueva columna para descripción del riesgo
            evaluacion_riesgo_nivel TEXT, -- Nueva columna para nivel de riesgo
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            UNIQUE(usuario, fecha) -- Evitar duplicados exactos
        )
    """)
    conn.commit()
    conn.close()

def guardar_estadisticas(datos):
    """Guarda las estadísticas de un perfil en la base de datos."""
    init_db() # Asegura que la tabla y columnas existan

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO estadisticas (
        fecha, usuario, publicaciones, seguidores, seguidos, biografia, 
        anomalia_descripcion, evaluacion_riesgo_desc, evaluacion_riesgo_nivel
    ) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datos["fecha"], datos["usuario"], datos["publicaciones"],
        datos["seguidores"], datos["seguidos"],
        datos.get("biografia", ""), # Usar .get() por si no siempre está presente
        datos.get("anomalia_descripcion"), # Se actualizará después por detectar_anomalias si es None
        datos.get("evaluacion_riesgo_desc", "No evaluado"), # Valor por defecto
        datos.get("evaluacion_riesgo_nivel", "Bajo") # Valor por defecto
    ))
    # La columna 'id' se autoincrementará. 'anomalia_descripcion' puede ser actualizada luego.

    conn.commit()
    conn.close()
    print(f"✅ Datos de {datos['usuario']} guardados.")

# Llamar a init_db() una vez al importar el módulo para asegurar que la DB está lista.
init_db()
