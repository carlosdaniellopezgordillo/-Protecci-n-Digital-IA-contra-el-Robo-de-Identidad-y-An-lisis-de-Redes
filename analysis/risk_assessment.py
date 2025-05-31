import re

def convertir_numero_simple(valor_str):
    """
    Una versión simple para convertir cadenas como '1.2k', '100 seguidores' a int.
    Devuelve 0 si la conversión falla o el tipo no es manejable.
    """
    if isinstance(valor_str, (int, float)):
        return int(valor_str)
    if not isinstance(valor_str, str):
        return 0
    
    valor_limpio = str(valor_str).lower().split(' ')[0] # Tomar solo la parte numérica
    valor_limpio = valor_limpio.replace(',', '').replace('.', '') # Quitar comas y puntos (para '1.234' o '1,234')
                                                        # Esto puede ser problemático si el punto es decimal para k/m
                                                        # Simplificamos asumiendo que k/m ya manejan decimales si es necesario

    if 'k' in valor_limpio:
        try:
            return int(float(valor_limpio.replace('k', '')) * 1000)
        except ValueError:
            return 0
    if 'm' in valor_limpio:
        try:
            return int(float(valor_limpio.replace('m', '')) * 1000000)
        except ValueError:
            return 0
    try:
        # Intentar extraer solo dígitos si aún hay texto (ej. '154seguidores' -> '154')
        solo_numeros = ''.join(filter(str.isdigit, valor_limpio))
        if solo_numeros:
            return int(solo_numeros)
        return 0 # No se pudieron extraer números
    except ValueError:
        return 0

def evaluar_riesgo_perfil(datos_perfil):
    """
    Evalúa preliminarmente el riesgo de un perfil basado en sus datos públicos.
    'datos_perfil' es el diccionario devuelto por obtener_estadisticas.
    Devuelve: (descripcion_del_riesgo, nivel_de_riesgo_str)
    """
    riesgos = []
    puntuacion_riesgo = 0

    publicaciones = convertir_numero_simple(datos_perfil.get('publicaciones', '0'))
    seguidores = convertir_numero_simple(datos_perfil.get('seguidores', '0'))
    seguidos = convertir_numero_simple(datos_perfil.get('seguidos', '0'))
    biografia = datos_perfil.get('biografia', "")

    if publicaciones < 5 and seguidores > 500:
        riesgos.append("Muy pocas publicaciones para el número de seguidores.")
        puntuacion_riesgo += 3
    elif publicaciones < 20 and seguidores > 5000:
        riesgos.append("Relativamente pocas publicaciones para el número de seguidores.")
        puntuacion_riesgo += 2

    if seguidos > 0 and seguidores > 50 and (seguidores / seguidos < 0.05): # Sigue a muchísimos más de los que le siguen
        riesgos.append("Sigue a muchas más cuentas de las que le siguen (ratio bajo).")
        puntuacion_riesgo += 2
    if seguidos > 4000: # Umbral alto para seguimiento masivo
        riesgos.append("Sigue a un número muy alto de cuentas (posible bot de seguimiento).")
        puntuacion_riesgo += 2
    
    if publicaciones == 0 and (seguidores > 10 or seguidos > 10):
        riesgos.append("Sin publicaciones pero con actividad de seguimiento/seguidores.")
        puntuacion_riesgo += 1

    if biografia:
        biografia_lower = biografia.lower()
        palabras_clave_bio_sospechosas = ["gana dinero", "crypto", "inversión", "regalo", "gratis", "seguidores ya", "click aquí", "oferta limitada", "soporte técnico", "enlace en mi bio para"]
        for palabra in palabras_clave_bio_sospechosas:
            if palabra in biografia_lower:
                riesgos.append(f"Biografía contiene término potencialmente arriesgado: '{palabra}'.")
                puntuacion_riesgo += 2
                break
        url_pattern = r'http[s]?://' # Simple check for any URL
        if re.search(url_pattern, biografia_lower):
            riesgos.append("Biografía contiene URL(s). Verificar manualmente su seguridad.")
            puntuacion_riesgo += 1

    nivel_riesgo_str = "Bajo"
    if puntuacion_riesgo >= 5: nivel_riesgo_str = "Alto"
    elif puntuacion_riesgo >= 3: nivel_riesgo_str = "Medio"

    if not riesgos: return "Riesgo bajo (según heurísticas básicas).", nivel_riesgo_str
    return f"Posibles indicadores: {'; '.join(riesgos)}.", nivel_riesgo_str