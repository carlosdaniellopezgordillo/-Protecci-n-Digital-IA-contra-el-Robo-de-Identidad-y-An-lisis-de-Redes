from scraping.scraper import iniciar_sesion, obtener_estadisticas, crear_driver
from database.db_handler import guardar_estadisticas, DB_PATH as APP_DB_PATH # Importar DB_PATH
from analysis.anomaly_detection import detectar_anomalias # Esta es la función que acabamos de crear/modificar

# --- Añadir importación para la nueva evaluación de riesgo ---
import sys
import os
# Añadir el directorio raíz del proyecto a sys.path para encontrar 'analysis'
APP_ROOT_DIR_MAIN = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT_DIR_MAIN not in sys.path:
    sys.path.append(APP_ROOT_DIR_MAIN)
from analysis.risk_assessment import evaluar_riesgo_perfil
# --- Fin de la adición ---
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

EDGE_DRIVER_PATH = r"C:\Users\gfdc\Downloads\edgedriver_win64\msedgedriver.exe"
# Obtener credenciales desde variables de entorno
INSTAGRAM_USUARIO = os.getenv("INSTAGRAM_USER")
INSTAGRAM_CONTRASEÑA = os.getenv("INSTAGRAM_PASS")

perfiles = ["tako_de_bistek69"]

def main():
    if not INSTAGRAM_USUARIO or not INSTAGRAM_CONTRASEÑA:
        print("❌ Error: Las credenciales de Instagram (INSTAGRAM_USER, INSTAGRAM_PASS) no están configuradas en el archivo .env o como variables de entorno.")
        return

    driver = crear_driver(EDGE_DRIVER_PATH)
    try:
        iniciar_sesion(driver, INSTAGRAM_USUARIO, INSTAGRAM_CONTRASEÑA)
        # Aquí podrías añadir una verificación más explícita del éxito del login si `iniciar_sesion`
        # devolviera un booleano o si se comprueba la URL actual, etc.
        # Por ahora, se asume que si `iniciar_sesion` no lanza una excepción grave, procede.
        for perfil in perfiles:
            datos = obtener_estadisticas(driver, perfil)
            if datos:
                # --- INICIO: Modificación para simular bot en 'tako_de_bistek69' ---
                if perfil == "tako_de_bistek69":
                    print(f"⚠️  Modificando datos para @{perfil} para simular perfil de riesgo...")
                    datos['publicaciones'] = "2 publicaciones"  # Muy pocas publicaciones
                    datos['seguidores'] = "650 seguidores"    # Seguidores moderados
                    datos['seguidos'] = "13500 seguidos"      # Sigue a muchísimas cuentas
                    datos['biografia'] = "gana dinero rapido online! visita mi link! http://sitio-sospechoso.tk" # Bio sospechosa con URL
                    print(f"   Nuevos datos para @{perfil}: Pubs: {datos['publicaciones']}, Sgs: {datos['seguidores']}, Sdos: {datos['seguidos']}")
                # --- FIN: Modificación ---

                # --- Evaluar riesgo del perfil ---
                desc_riesgo, nivel_riesgo = evaluar_riesgo_perfil(datos)
                datos['evaluacion_riesgo_desc'] = desc_riesgo
                datos['evaluacion_riesgo_nivel'] = nivel_riesgo
                # --- Fin evaluación ---
                guardar_estadisticas(datos) # db_handler se encarga de la ruta a la BD
                print(f"ℹ️ Datos y evaluación de riesgo para @{perfil} guardados. Nivel: {nivel_riesgo}")
    except Exception as e:
        print(f"🚨 Error general en la ejecución principal: {e}")
    finally:
        if 'driver' in locals() and driver: # Asegurarse que driver existe antes de llamar a quit
            driver.quit()

    detectar_anomalias() # Esta función ahora usa el DB_PATH definido en su propio módulo

if __name__ == "__main__":
    main()