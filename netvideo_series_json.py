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
    """Verifica disponibilidad del póster (Lógica de tu M3U)"""
    if not url: return False
    try:
        r = session.head(url, timeout=2, allow_redirects=True)
        return r.status_code == 200
    except:
        return False

def extraer_metadatos_inteligentes(html):
    """Extrae Nombre y Categoría (NET-Género) evitando nombres asiáticos"""
    match_p1 = re.search(r'<h2.*?>.*?</h2>\s*<p>(.*?)</p>', html, re.DOTALL)
    match_p2 = re.search(r'<h2.*?>.*?</h2>\s*<p>.*?</p>\s*<p>(.*?)</p>', html, re.DOTALL)
    
    nombre_final = ""
    categoria_final = "NET-Series"
    
    # 1. Lógica para el NOMBRE (Busca español, si no limpia h2)
    if match_p1:
        candidato = match_p1.group(1).strip()
        if not any(k in candidato.lower() for k in KEYWORDS_GENEROS):
            nombre_final = candidato

    if not nombre_final:
        h2_match = re.search(r'<h2.*?>(.*?)</h2>', html)
        if h2_match:
            h2_raw = h2_match.group(1).strip()
            nombre_final = re.sub(r'[^\x00-\x7F]+', '', h2_raw).strip() or h2_raw

    # 2. Lógica para la CATEGORÍA (Opción B: NET-Género)
    texto_generos = ""
    if match_p2 and any(k in match_p2.group(1).lower() for k in KEYWORDS_GENEROS):
        texto_generos = match_p2.group(1).strip()
    elif match_p1 and any(k in match_p1.group(1).lower() for k in KEYWORDS_GENEROS):
        texto_generos = match_p1.group(1).strip()

    if texto_generos:
        # Tomamos el primer género antes de coma o &
        solo_uno = re.split(r'[,&]', texto_generos)[0].strip()
        categoria_final = f"NET-{solo_uno}"

    return nombre_final, categoria_final

def corregir_video_y_cloud(enlace_b64):
    """Decodifica Base64 y cambia cloud_a/b por cloud_1/2"""
    try:
        url_dec = base64.b64decode(enlace_b64).decode('utf-8')
        return url_dec.replace("/cloud_a/", "/cloud_1/").replace("/cloud_b/", "/cloud_2/")
    except:
        return ""

# --- DENTRO DEL FLUJO PRINCIPAL ---

# 1. Obtener metadatos limpios
nombre_serie, categoria_serie = extraer_metadatos_inteligentes(html)

# 2. Lógica de Póster de 2 niveles (w410i -> original)
id_serie_match = re.search(r'watch=(\d+)', url_serie)
id_serie = id_serie_match.group(1) if id_serie_match else "default"

poster_w410_i = f"{SERVIDOR}/poster/w410/{id_serie}i.jpg"
poster_original = f"{SERVIDOR}/poster/original/{id_serie}.jpg"

# Si el póster HD existe, lo usa. Si no, salta directo al original.
if verificar_url_existe(poster_w410_i):
    poster_final = poster_w410_i
else:
    poster_final = poster_original

# 3. Al procesar episodios (Dentro de tu loop de capítulos):
# url_final = corregir_video_y_cloud(enlace_b64_capitulo)
