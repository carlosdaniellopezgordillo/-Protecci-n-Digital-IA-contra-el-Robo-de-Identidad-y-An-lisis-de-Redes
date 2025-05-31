from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
import time # Necesario para time.sleep en los reintentos

# ================================
# FUNCIONES PRINCIPALES
# ================================

def crear_driver(edge_path, headless=False):
    service = Service(edge_path)
    options = webdriver.EdgeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--start-maximized")
    return webdriver.Edge(service=service, options=options)

def iniciar_sesion(driver, usuario, contraseña):
    print("🔐 Iniciando sesión...")
    driver.get("https://www.instagram.com/accounts/login/")
    
    # Esperar que el campo de usuario esté presente y escribir el usuario
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.NAME, "username"))
    ).send_keys(usuario)
    
    # Escribir la contraseña y enviar (simulando Enter)
    driver.find_element(By.NAME, "password").send_keys(contraseña + "\n")

    # Manejar popup "Guardar información de inicio de sesión"
    # Intenta hacer clic en "Ahora no" si aparece el popup.
    # Instagram puede usar diferentes elementos/textos, estos son algunos comunes.
    save_info_not_now_xpaths = [
        "//button[text()='Ahora no']",
        "//div[@role='button'][text()='Ahora no']",
        "//button[contains(text(),'Ahora no')]"
    ]
    popup_handled = False
    for xpath_expr in save_info_not_now_xpaths:
        try:
            WebDriverWait(driver, 7).until( # Espera más corta para este popup específico
                EC.element_to_be_clickable((By.XPATH, xpath_expr))
            ).click()
            print("ℹ️ Popup 'Guardar información de inicio de sesión' cerrado con 'Ahora no'.")
            popup_handled = True
            break 
        except:
            continue 
    if not popup_handled:
        print("ℹ️ No se encontró o no se pudo cerrar el popup 'Guardar información de inicio de sesión' (puede que no haya aparecido).")

    # Manejar popup "Activar notificaciones"
    # Este popup suele aparecer después del de "Guardar información".
    try:
        WebDriverWait(driver, 7).until( # Espera más corta
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Ahora no')]"))
        ).click()
        print("ℹ️ Popup 'Activar notificaciones' cerrado con 'Ahora no'.")
    except:
        print("ℹ️ No se encontró o no se pudo cerrar el popup 'Activar notificaciones' (puede que no haya aparecido o ya se haya manejado).")

    # Confirmación final: Esperar a que un elemento clave de la página de inicio esté presente.
    home_page_indicators = [
        (By.XPATH, "//*[local-name()='svg'][@aria-label='Inicio']"), # Icono de Inicio (SVG)
        (By.XPATH, "//input[@placeholder='Buscar']") # Barra de búsqueda
    ]
    logged_in_successfully = False
    for indicator_type, indicator_value in home_page_indicators:
        try:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((indicator_type, indicator_value)))
            print(f"✅ Sesión iniciada correctamente y página principal cargada (Indicador: {indicator_value}).")
            logged_in_successfully = True
            break
        except:
            continue
    
    if not logged_in_successfully:
        print(f"⚠️ No se pudo confirmar la carga de la página principal después del login. El scraping podría fallar.")
        # Considerar lanzar una excepción si el login es crítico:
        # raise Exception("Fallo en el inicio de sesión o la página principal no cargó correctamente.")

def obtener_estadisticas(driver, perfil):
    url = f"https://www.instagram.com/{perfil}/"
    MAX_REINTENTOS = 3
    ESPERA_ENTRE_REINTENTOS_SEGUNDOS = 5

    for intento in range(MAX_REINTENTOS):
        print(f"\n📥 Analizando perfil: {perfil} (Intento {intento + 1}/{MAX_REINTENTOS})")
        try:
            driver.get(url)
            
            # Esperar a que el header del perfil (que contiene las estadísticas) esté presente
            header_xpath = "//header"
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, header_xpath))
            )
            # Una pequeña pausa opcional para asegurar que todo el contenido dinámico cargue
            time.sleep(2) 

            # XPaths para los datos. Estos pueden necesitar ajustes si Instagram cambia su estructura.
            # El XPath para publicaciones es el más propenso a cambiar si el orden de los `li` varía.
            publicaciones_xpath = f"//header//ul/li[1]//span | //header//li[1]//span[@data-bloks-name='bk.components.Text']" # Intenta ser más general
            # Para seguidores y seguidos, buscar por el enlace que los contiene es más robusto
            seguidores_xpath = f"//a[contains(@href, '/{perfil}/followers/')]/span/span | //a[contains(@href, '/{perfil}/followers/')]/span[@title] | //header//ul/li[2]//span"
            seguidos_xpath = f"//a[contains(@href, '/{perfil}/following/')]/span/span | //a[contains(@href, '/{perfil}/following/')]/span | //header//ul/li[3]//span"

            # Esperar a que cada elemento específico esté presente antes de extraer el texto
            publicaciones_element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, publicaciones_xpath)))
            publicaciones = publicaciones_element.text.strip()
            
            seguidores_element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, seguidores_xpath)))
            # A veces el número de seguidores está en el atributo 'title' para números grandes (ej. "1,234,567 seguidores")
            seguidores = seguidores_element.get_attribute("title") or seguidores_element.text.strip()

            seguidos_element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, seguidos_xpath)))
            seguidos = seguidos_element.text.strip()

            print(f"📊 Perfil: {perfil} - Publicaciones: {publicaciones}, Seguidores: {seguidores}, Seguidos: {seguidos}")

            return {
                "usuario": perfil,
                "publicaciones": publicaciones,
                "seguidores": seguidores,
                "seguidos": seguidos,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        except (TimeoutException, NoSuchElementException) as e:
            print(f"⚠️ Error al extraer estadísticas de {perfil} (Intento {intento + 1}): {type(e).__name__}. Reintentando...")
            if intento + 1 == MAX_REINTENTOS:
                print(f"❌ Fallo final al extraer estadísticas de {perfil} después de {MAX_REINTENTOS} intentos.")
                return None
            time.sleep(ESPERA_ENTRE_REINTENTOS_SEGUNDOS)
        except Exception as e: # Captura cualquier otra excepción inesperada
            print(f"🚨 Error inesperado y grave al extraer estadísticas de {perfil}: {e}")
            return None # No reintentar en errores genéricos desconocidos
    return None # Si todos los intentos fallan
