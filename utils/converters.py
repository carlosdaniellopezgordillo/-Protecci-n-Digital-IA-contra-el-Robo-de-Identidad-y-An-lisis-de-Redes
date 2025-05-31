import re

def convertir_numero(texto):
    # Eliminar palabras como 'seguidores', 'seguidos', 'publicaciones'
    texto = texto.lower()
    texto = re.sub(r"[^\d,.kmKM]", "", texto).replace(",", "").strip()

    try:
        if 'k' in texto:
            return float(texto.replace('k', '').replace('K', '')) * 1_000
        elif 'm' in texto:
            return float(texto.replace('m', '').replace('M', '')) * 1_000_000
        return float(texto)
    except ValueError:
        return 0
