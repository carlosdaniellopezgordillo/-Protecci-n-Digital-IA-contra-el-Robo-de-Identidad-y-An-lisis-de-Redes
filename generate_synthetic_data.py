import sqlite3
import os
import random
from datetime import datetime, timedelta
import pandas as pd

# --- CONFIGURACIÓN ---
APP_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH_INSTAGRAM = os.path.join(APP_ROOT_DIR, "data", "analisis_instagram.db")

# Cuántos días de historial MÁS ANTIGUO generar para cada perfil existente
NUM_DAYS_TO_ADD_BACKWARDS = 90  # Por ejemplo, añadir 3 meses de datos más antiguos

# Parámetros para la generación de datos hacia atrás (ajusta según necesites)
# Estos valores son *decrementos* diarios promedio cuando se va hacia atrás en el tiempo.
AVG_FOLLOWER_CHANGE_BACKWARDS = 50  # Cuántos seguidores menos tenía en promedio el día anterior
RANDOM_FOLLOWER_RANGE_BACKWARDS = 30 # Variación aleatoria sobre ese promedio
AVG_POSTS_CHANGE_BACKWARDS = 0.1 # Probabilidad de que hubiera un post menos (0.1 = 1 post menos cada 10 días aprox)
AVG_FOLLOWING_CHANGE_BACKWARDS = 1 # Cuántos seguidos menos/más podría tener

MIN_FOLLOWERS_THRESHOLD = 100 # No dejar que los seguidores bajen de este umbral
MIN_POSTS_THRESHOLD = 10      # No dejar que las publicaciones bajen de este umbral
MIN_FOLLOWING_THRESHOLD = 10  # No dejar que los seguidos bajen de este umbral


def get_db_connection(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    return conn

def limpiar_y_convertir_a_int(valor):
    """
    Limpia una cadena como '154 seguidores' o '1.2k' y la convierte a un entero.
    """
    if isinstance(valor, (int, float)):
        return int(valor)
    if isinstance(valor, str):
        valor_limpio = valor.lower().replace('mil', 'k') # Estandarizar "mil" a "k"
        # Quitar puntos de miles si los hubiera (ej. 1.234 -> 1234)
        valor_limpio = valor_limpio.replace('.', '')
        
        # Extraer solo los dígitos iniciales antes de cualquier letra (excepto 'k' o 'm' al final)
        solo_numeros = ''.join(filter(str.isdigit, valor_limpio.split(' ')[0]))
        if solo_numeros:
            return int(solo_numeros)
    return 0 # Valor por defecto si no se puede convertir o es None

def setup_database(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS estadisticas")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS estadisticas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL,
        fecha TEXT NOT NULL,
        publicaciones INTEGER,
        seguidores INTEGER,
        seguidos INTEGER,
        biografia TEXT, -- Añadido para que coincida con db_handler.py
        anomalia_descripcion TEXT,
        evaluacion_riesgo_desc TEXT, 
        evaluacion_riesgo_nivel TEXT 
    )
    """)
    conn.commit()
    print("✅ Base de datos reconfigurada (tabla 'estadisticas' recreada).")

def generate_older_data_for_profile(earliest_record_df_row, num_days_to_add):
    """
    Genera datos sintéticos MÁS ANTIGUOS para un perfil, basándose en su primer registro conocido.
    """
    synthetic_older_data = []
    
    usuario = earliest_record_df_row['usuario']
    # Asegurarse de que la fecha es un objeto datetime
    earliest_date = pd.to_datetime(earliest_record_df_row['fecha'])
    
    # Empezamos con los valores del registro más antiguo conocido
    current_followers = int(earliest_record_df_row['seguidores'])
    current_posts = int(earliest_record_df_row['publicaciones'])
    current_following = int(earliest_record_df_row['seguidos'])

    print(f"   Generando {num_days_to_add} días de historial antiguo para @{usuario}, terminando antes de {earliest_date.strftime('%Y-%m-%d')}.")

    # Iteramos hacia atrás desde el día ANTERIOR al primer registro conocido
    for i in range(num_days_to_add):
        # La fecha sintética actual es `i+1` días ANTES de la `earliest_date`
        synthetic_date = earliest_date - timedelta(days=(i + 1))
        
        # Simular valores para el día anterior (synthetic_date)
        # Seguidores: generalmente menos en el pasado
        follower_decrease = AVG_FOLLOWER_CHANGE_BACKWARDS + random.randint(-RANDOM_FOLLOWER_RANGE_BACKWARDS, RANDOM_FOLLOWER_RANGE_BACKWARDS // 2) # Menos variación al alza
        current_followers -= follower_decrease
        if current_followers < MIN_FOLLOWERS_THRESHOLD:
            current_followers = MIN_FOLLOWERS_THRESHOLD + random.randint(0, 50) # Pequeño rebote si baja mucho

        # Publicaciones: generalmente menos en el pasado
        if random.random() < AVG_POSTS_CHANGE_BACKWARDS and current_posts > MIN_POSTS_THRESHOLD:
            current_posts -= random.randint(0,1) # 0 o 1 post menos
        if current_posts < MIN_POSTS_THRESHOLD:
            current_posts = MIN_POSTS_THRESHOLD
            
        # Seguidos: pueden fluctuar
        following_change = random.randint(-AVG_FOLLOWING_CHANGE_BACKWARDS, AVG_FOLLOWING_CHANGE_BACKWARDS)
        current_following -= following_change # Restamos porque vamos hacia atrás
        if current_following < MIN_FOLLOWING_THRESHOLD:
            current_following = MIN_FOLLOWING_THRESHOLD + random.randint(0,10)
        
        synthetic_older_data.append({
            "usuario": usuario,
            "fecha": synthetic_date.strftime("%Y-%m-%d %H:%M:%S"),
            "publicaciones": int(current_posts),
            "seguidores": int(current_followers),
            "seguidos": int(current_following),
            "biografia": f"Bio sintética para @{usuario} en {synthetic_date.strftime('%Y-%m-%d')}", # Ejemplo de bio
            "anomalia_descripcion": None, # No generamos anomalías para el historial sintético
            "evaluacion_riesgo_desc": "No evaluado (sintético)", # Valor por defecto
            "evaluacion_riesgo_nivel": "Bajo" # Valor por defecto
        })
        
    # Los datos generados están naturalmente en orden cronológico inverso (del más reciente al más antiguo)
    # Los invertimos para que estén en orden cronológico correcto (del más antiguo al más reciente)
    return sorted(synthetic_older_data, key=lambda x: x['fecha'])


def main():
    conn = get_db_connection(DB_PATH_INSTAGRAM)

    # 1. Leer todos los datos originales existentes
    try:
        df_original = pd.read_sql_query("SELECT * FROM estadisticas", conn)
    except pd.io.sql.DatabaseError: # La tabla podría no existir si es la primera vez
        df_original = pd.DataFrame()

    if df_original.empty:
        print("🤷 No hay datos existentes en la base de datos para inflar. Ejecuta el scraper primero o usa la versión anterior del script para generar perfiles desde cero.")
        conn.close()
        return

    print(f"ℹ️ Se encontraron {len(df_original)} registros originales para {df_original['usuario'].nunique()} perfiles.")
    
    # Limpiar las columnas numéricas ANTES de cualquier otra operación
    for col in ['publicaciones', 'seguidores', 'seguidos']:
        if col in df_original.columns:
            df_original[col] = df_original[col].apply(limpiar_y_convertir_a_int)


    # Convertir la columna 'fecha' a datetime objetos para la manipulación
    df_original['fecha'] = pd.to_datetime(df_original['fecha'])

    # 2. Encontrar el primer registro (más antiguo) para cada usuario
    # idx contendrá el índice de la fila con la fecha mínima para cada grupo 'usuario'
    idx = df_original.groupby('usuario')['fecha'].idxmin()
    earliest_records_df = df_original.loc[idx]

    all_generated_older_data = []
    
    print(f"⏳ Generando historial antiguo para {len(earliest_records_df)} perfiles existentes...")
    for _, row in earliest_records_df.iterrows():
        older_data_for_profile = generate_older_data_for_profile(row, NUM_DAYS_TO_ADD_BACKWARDS)
        if older_data_for_profile:
            all_generated_older_data.extend(older_data_for_profile)

    # 3. Preparar la base de datos (vaciarla)
    setup_database(conn) # Esto borra la tabla 'estadisticas' y la recrea

    # 4. Combinar datos sintéticos antiguos y datos originales
    df_synthetic_older = pd.DataFrame(all_generated_older_data)
    
    # Asegurarse de que las columnas y tipos de datos coincidan antes de concatenar
    # (especialmente si df_synthetic_older está vacío)
    if not df_synthetic_older.empty:
        df_combined = pd.concat([df_synthetic_older, df_original.drop(columns=['id'], errors='ignore')], ignore_index=True)
    else: # No se generó ningún dato sintético más antiguo (quizás NUM_DAYS_TO_ADD_BACKWARDS fue 0)
        df_combined = df_original.drop(columns=['id'], errors='ignore')

    # Ordenar por usuario y luego por fecha para asegurar la cronología correcta
    df_combined['fecha'] = pd.to_datetime(df_combined['fecha']) # Asegurar que 'fecha' sea datetime para ordenar
    df_combined = df_combined.sort_values(by=['usuario', 'fecha'])
    
    # Convertir la columna 'fecha' de nuevo a string antes de insertar si es necesario por la BD
    # (to_sql maneja bien los datetime de pandas, pero por consistencia con el formato original)
    df_combined['fecha'] = df_combined['fecha'].dt.strftime("%Y-%m-%d %H:%M:%S")


    # 5. Insertar todos los datos combinados
    if not df_combined.empty:
        try:
            # Excluir la columna 'id' si existe, ya que es AUTOINCREMENT
            columns_to_insert = [col for col in df_combined.columns if col.lower() != 'id']
            df_combined[columns_to_insert].to_sql("estadisticas", conn, if_exists="append", index=False)
            conn.commit()
            print(f"🎉 ¡Datos inflados e insertados en '{DB_PATH_INSTAGRAM}' exitosamente!")
            print(f"   Total de registros ahora en la BD: {len(df_combined)}")
            if not df_synthetic_older.empty:
                 print(f"   Se añadieron {len(df_synthetic_older)} registros de historial sintético.")
        except Exception as e:
            print(f"❌ Error al insertar datos combinados en la base de datos: {e}")
            print("   La tabla 'estadisticas' podría estar vacía o parcialmente llena.")
    else:
        print("🤷 No se generaron ni se insertaron datos.")

    conn.close()

if __name__ == "__main__":
    main()