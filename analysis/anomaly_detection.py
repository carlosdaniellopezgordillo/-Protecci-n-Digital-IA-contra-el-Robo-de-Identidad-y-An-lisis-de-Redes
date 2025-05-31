import sqlite3
import pandas as pd
import numpy as np
import os

# Ajustar la ruta si es necesario para que coincida con la de db_handler.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Raíz del proyecto
DB_PATH = os.path.join(BASE_DIR, "data", "analisis_instagram.db")

def calcular_limites_iqr(series):
    """Calcula los límites superior e inferior para la detección de outliers usando IQR."""
    Q1 = series.quantile(0.25)
    Q3 = series.quantile(0.75)
    IQR = Q3 - Q1
    limite_inferior = Q1 - 1.5 * IQR
    limite_superior = Q3 + 1.5 * IQR
    return limite_inferior, limite_superior

def detectar_anomalias_para_metrica(df_usuario, metrica):
    """
    Detecta anomalías para una métrica específica en el DataFrame de un usuario.
    Devuelve un diccionario con los IDs de las estadísticas anómalas y su descripción.
    """
    anomalias_detectadas = {}
    if len(df_usuario) < 3: # Necesitamos al menos 3 puntos para calcular diferencias y luego IQR de forma robusta
        return anomalias_detectadas

    # Asegurarse de que la métrica es numérica
    df_usuario[metrica] = pd.to_numeric(df_usuario[metrica], errors='coerce')
    df_usuario = df_usuario.dropna(subset=[metrica]) # Eliminar NaNs si la conversión falla

    if df_usuario[metrica].isnull().all() or len(df_usuario) < 3:
        return anomalias_detectadas

    # Calcular diferencias diarias
    # El primer diff será NaN, el segundo diff es el cambio del día 2 vs día 1, asociado al día 2.
    diff_metrica = df_usuario[metrica].diff().fillna(0) # Rellenar el primer NaN con 0 o manejarlo

    if len(diff_metrica) < 2: # No suficientes diferencias para IQR
        return anomalias_detectadas

    limite_inferior, limite_superior = calcular_limites_iqr(diff_metrica.iloc[1:]) # Excluir el primer diff (que es 0 o NaN)

    for i in range(1, len(df_usuario)): # Empezar desde el segundo registro para tener una diferencia
        cambio_actual = diff_metrica.iloc[i]
        id_estadistica = df_usuario['id'].iloc[i]
        
        if cambio_actual < limite_inferior or cambio_actual > limite_superior:
            signo = "+" if cambio_actual > 0 else ""
            descripcion = f"{metrica.capitalize()}: {signo}{cambio_actual:,.0f}"
            anomalias_detectadas[id_estadistica] = anomalias_detectadas.get(id_estadistica, "") + descripcion + "; "
            
    return anomalias_detectadas

def detectar_anomalias():
    """
    Detecta anomalías en los datos de la tabla 'estadisticas' y actualiza
    la columna 'anomalia_descripcion'.
    """
    print("\n🔍 Iniciando detección de anomalías...")
    if not os.path.exists(DB_PATH):
        print(f"❌ Error: La base de datos no se encuentra en {DB_PATH}")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Limpiar descripciones de anomalías previas
    cursor.execute("UPDATE estadisticas SET anomalia_descripcion = NULL")
    conn.commit()

    df_total = pd.read_sql_query("SELECT id, usuario, fecha, publicaciones, seguidores, seguidos FROM estadisticas ORDER BY usuario, fecha", conn)
    
    if df_total.empty:
        print("ℹ️ No hay datos en la tabla 'estadisticas' para analizar.")
        conn.close()
        return

    usuarios = df_total['usuario'].unique()
    metricas = ['seguidores', 'publicaciones', 'seguidos']
    
    actualizaciones_anomalias = {} # {id_estadistica: "descripcion completa"}

    for usuario in usuarios:
        df_usuario = df_total[df_total['usuario'] == usuario].copy()
        df_usuario['fecha'] = pd.to_datetime(df_usuario['fecha'])
        df_usuario = df_usuario.sort_values(by='fecha')

        for metrica in metricas:
            anomalias_metricas = detectar_anomalias_para_metrica(df_usuario, metrica)
            for id_stat, desc in anomalias_metricas.items():
                actualizaciones_anomalias[id_stat] = actualizaciones_anomalias.get(id_stat, "") + desc

    # Actualizar la base de datos
    if actualizaciones_anomalias:
        for id_stat, desc_completa in actualizaciones_anomalias.items():
            cursor.execute("UPDATE estadisticas SET anomalia_descripcion = ? WHERE id = ?", (desc_completa.strip().rstrip(';'), id_stat))
        conn.commit()
        print(f"✅ Detección de anomalías completada. {len(actualizaciones_anomalias)} registros actualizados.")
    else:
        print("ℹ️ No se detectaron nuevas anomalías.")
        
    conn.close()

if __name__ == '__main__':
    # Para probar el script directamente
    detectar_anomalias()