import requests
import re
import base64
import json
import os
import urllib.parse
import time

# --- CONFIGURACIÓN ---
COOKIE = "setLenguaje=spa"
SERVIDOR = os.environ.get("URL_SERVIDOR")
ARCHIVO_SALIDA = "netvideo_series.json"

HEADERS = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": SERVIDOR
}

# Keywords exactas de tu M3U para identificar géneros
KEYWORDS_GENEROS = [
    'acción', 'accion', 'aventura', 'adventura', 'drama', 'comedia', 
    'animación', 'animacion', 'sci-fi', 'fantasía', 'fantasia', 'terror', 
    'suspenso', 'romance', 'crimen', 'documental', 'western', 'familia'
]

session = requests.Session()
session.headers.update(HEADERS)

def verificar_url_existe(url):
    """Lógica de tu M3U para verificar póster con 'i'"""
    if not url: return False
    try:
        r = session.head(url, timeout=2, allow_redirects=True)
        return r.status_code == 200
    except:
        return False

def extraer_metadatos_inteligentes(html):
    """Extrae Nombre y Categoría (NET-Género) evitando nombres asiáticos"""
    # 1. Intentar capturar el nombre en el primer <p> tras el <h2>
    match_p1 = re.search(r'<h2.*?>.*?</h2>\s*<p>(.*?)</p>', html, re.DOTALL)
    match_p2 = re.search(r'<h2.*?>.*?</h2>\s*<p>.*?</p>\s*<p>(.*?)</p>', html, re.DOTALL)
    
    nombre_final = ""
    categoria_final = "NET-Series"
    
    # Lógica para el NOMBRE
    if match_p1:
        candidato = match_p1.group(1).strip()
        if not any(k in candidato.lower() for k in KEYWORDS_GENEROS):
            nombre_final = candidato

    if not nombre_final:
        h2_raw = re.search(r'<h2.*?>(.*?)</h2>', html).group(1).strip()
        # Limpieza ASCII para borrar Coreano/Chino/Japonés
        nombre_final = re.sub(r'[^\x00-\x7F]+', '', h2_raw).strip() or h2_raw

    # Lógica para la CATEGORÍA (Opción B: NET-Género)
    # Buscamos el párrafo que SI contenga los géneros
    texto_generos = ""
    if match_p2 and any(k in match_p2.group(1).lower() for k in KEYWORDS_GENEROS):
        texto_generos = match_p2.group(1).strip()
    elif match_p1 and any(k in match_p1.group(1).lower() for k in KEYWORDS_GENEROS):
        texto_generos = match_p1.group(1).strip()

    if texto_generos:
        # Tomamos el primer género (antes de coma o &)
        solo_uno = re.split(r'[,&]', texto_generos)[0].strip()
        categoria_final = f"NET-{solo_uno}"

    return nombre_final, categoria_final

def extraer_diccionario_visual(html):
    """Mantiene tu lógica de iconos por episodio"""
    vis_dict = {}
    matches = re.findall(r"['\"](.*?)['\"]\s*:\s*['\"](.*?)['\"]", html)
    for k, v in matches:
        if "/cloud/" in k or "base64" in k or len(k) > 50:
            vis_dict[k] = v
    return vis_dict

def procesar_temporada(id_a, url_serie, nombre_serie, num_temp, vis_dict, poster):
    """Procesa capítulos aplicando el cambio de Cloud"""
    eps_list = []
    # (Aquí va tu lógica de descarga de la tabla de capítulos)
    # Al obtener el enlace_b64 de cada capítulo:
    # video_dec = base64.b64decode(enlace_b64).decode('utf-8')
    # video_final = video_dec.replace("/cloud_a/", "/cloud_1/").replace("/cloud_b/", "/cloud_2/")
    # icon = vis_dict.get(enlace_b64, poster)
    return eps_list

def ejecutar():
    catalogo = []
    # Loop de navegación...
    # html = session.get(url_serie).text
    
    nombre_serie, categoria_serie = extraer_metadatos_inteligentes(html)
    
    # Lógica de Póster
    id_serie = re.search(r'watch=(\d+)', url_serie).group(1)
    p_normal = f"{SERVIDOR}/images/posters/{id_serie}.jpg"
    p_i = f"{SERVIDOR}/images/posters/{id_serie}i.jpg"
    poster_final = p_i if verificar_url_existe(p_i) else p_normal

    serie_obj = {
        "name": nombre_serie,
        "category": categoria_serie,
        "info": {
            "poster": poster_final,
            "plot": "...", # Tu extracción de sinopsis
            "genres": [categoria_serie.replace("NET-", "")]
        },
        "seasons": []
    }
    # ... resto del flujo de temporadas ...

if __name__ == "__main__":
    print("🚀 Iniciando Netvideo Series...")
    # ejecutar()
