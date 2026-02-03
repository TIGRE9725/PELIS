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
ARCHIVO_SALIDA = "netvideo.series.m3u"

HEADERS = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": SERVIDOR
}

print("--- NETVIDEO SERIES V18 (VERIFIED POSTER) ---")
print(f"Servidor: {SERVIDOR}")

contenido_m3u = ["#EXTM3U"]
total_capitulos = 0
series_visitadas = set()

session = requests.Session()
session.headers.update(HEADERS)

def limpiar_texto_html(texto):
    if not texto: return ""
    txt = texto.replace("&amp;", "&").replace("&#038;", "&").replace("&quot;", '"')
    return txt.strip()

def limpiar_nombre_grupo(nombre_sucio):
    """Limpia el nombre para agrupar en TiviMate"""
    if not nombre_sucio: return "Series Varias"
    
    nombre = urllib.parse.unquote(nombre_sucio)
    nombre = nombre.replace('_', ' ').replace('-', ' ').replace('.', ' ')
    
    # Quitar patrones técnicos
    nombre = re.sub(r'\bS\d+\s*E\d+\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\b\d+x\d+\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\s+\d+\s+\d+$', '', nombre) 
    nombre = re.sub(r'\b(480|720|1080)[p]?\b', '', nombre, flags=re.IGNORECASE)
    
    nombre = re.sub(r'\s+', ' ', nombre).strip()
    
    if len(nombre) < 2: return nombre_sucio
    return nombre

def extraer_nombre_del_archivo(url):
    """Analiza el nombre del archivo SIN token"""
    try:
        url_limpia = url.split('?')[0]
        nombre = url_limpia.split('/')[-1]
        nombre = re.sub(r'\.(mp4|mkv|avi|ts)$', '', nombre, flags=re.IGNORECASE)
        
        patron_corte = r'[\._\s-](S\d+|SEASON|TEMPORADA|CAPITULO|E\d+|rev\.)'
        partes = re.split(patron_corte, nombre, flags=re.IGNORECASE)
        nombre_limpio = partes[0]
        nombre_limpio = nombre_limpio.replace('.', ' ').replace('_', ' ')
        
        if len(nombre_limpio) < 2: return None
        return nombre_limpio.strip().title()
    except:
        return None

def es_lista_de_generos(texto):
    """Detecta si el texto son géneros para no usarlo como título"""
    if not texto: return False
    texto_lower = texto.lower()
    keywords = [
        'acción', 'accion', 'aventura', 'adventura', 'drama', 'comedia', 
        'animación', 'animacion', 'sci-fi', 'fantasía', 'fantasia', 'terror', 
        'suspenso', 'romance', 'crimen', 'documental', 'western', 'familia'
    ]
    matches = 0
    for k in keywords:
        if k in texto_lower: matches += 1
            
    if ("," in texto or "&" in texto) and matches >= 1: return True
    if matches >= 2: return True
    if texto_lower.strip() in keywords: return True
    return False

def verificar_url_existe(url):
    """
    Verifica si una imagen existe realmente (Status 200).
    Usa HEAD para ser ultrarrápido y no descargar la imagen.
    """
    if not url: return False
    try:
        # Timeout corto (2s) para no alentar el script
        r = session.head(url, timeout=2, allow_redirects=True)
        return r.status_code == 200
    except:
        return False

def analizar_html_serie(html, id_serie):
    """
    Lógica Maestra V18:
    1. Nombre Latino Inteligente.
    2. Poster Vertical VERIFICADO (Si falla, usa el horizontal original).
    """
    nombre_final = f"Serie {id_serie}"
    poster_final = ""

    # --- 1. NOMBRE ---
    match_bloque = re.search(r'<h2[^>]*>(.*?)</h2>\s*<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    
    if match_bloque:
        texto_h2 = limpiar_texto_html(match_bloque.group(1))
        texto_p = limpiar_texto_html(match_bloque.group(2))
        
        if es_lista_de_generos(texto_p):
            nombre_final = texto_h2
        else:
            nombre_final = texto_p
    else:
        match_h2 = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)
        if match_h2: nombre_final = limpiar_texto_html(match_h2.group(1))

    # --- 2. POSTER (Lógica de Verificación) ---
    match_bg = re.search(r'background-image:\s*url\(([^)]+)\)', html, re.IGNORECASE)
    
    if match_bg:
        bg_url_raw = match_bg.group(1).replace('"', '').replace("'", "").strip()
        # Limpieza básica de la URL relativa
        if not bg_url_raw.startswith("http"):
            bg_url_raw = SERVIDOR + bg_url_raw.replace("..", "")
            
        # URL 1: ORIGINAL (Horizontal - Seguro que funciona)
        poster_original = bg_url_raw
        
        # URL 2: HACK (Vertical - Puede fallar)
        # Transformamos .../original/...p.jpg  -->  .../w410/...i.jpg
        poster_hack = bg_url_raw.replace('/original/', '/w410/')
        poster_hack = re.sub(r'p(\.(jpg|png|jpeg))$', r'i\1', poster_hack, flags=re.IGNORECASE)
        
        # VERIFICACIÓN DEL HACK
        if verificar_url_existe(poster_hack):
            poster_final = poster_hack # ¡Éxito! Usamos el vertical.
        else:
            poster_final = poster_original # Falló (404), usamos el horizontal.
            
    else:
        # Fallback si no hay background
        match_fallback = re.search(r'src="(\.\./poster/w410/[^"]+)"', html)
        if match_fallback:
            poster_final = SERVIDOR + match_fallback.group(1).replace("..", "")

    return nombre_final, poster_final

def decodificar_json(data_json, nombre_web, nombre_temp_label, poster):
    global total_capitulos
    caps_count = 0
    try:
        data_json.sort(key=lambda x: int(x.get('number', 0)))
    except: pass

    grupo_general = limpiar_nombre_grupo(nombre_web)

    for ep in data_json:
        try:
            num_ep = ep.get('number', 0)
            b64 = ep.get('mp4_spa') or ep.get('mp4_sub') or ep.get('stream') or ep.get('hls_spa')
            
            if b64:
                b64 = b64.replace('\\/', '/')
                link_sucio = base64.b64decode(b64).decode('utf-8').replace("\\/", "/").strip()
                if not link_sucio.startswith("http"): link_sucio = SERVIDOR + link_sucio
                
                link_final_m3u = link_sucio 
                nombre_archivo = extraer_nombre_del_archivo(link_sucio)
                nombre_base = nombre_archivo if nombre_archivo else grupo_general

                ep_str = f"E{int(num_ep):02d}"
                titulo_cap = f"{nombre_base} {nombre_temp_label}{ep_str}"
                
                entry = f'#EXTINF:-1 tvg-id="" tvg-logo="{poster}" group-title="{grupo_general}",{titulo_cap}\n{link_final_m3u}'
                contenido_m3u.append(entry)
                caps_count += 1
                total_capitulos += 1
        except: pass
    return caps_count

def procesar_bloque_completo(id_watch, referer_url, nombre_web, nombre_temp_label, poster):
    url_watch = f"{SERVIDOR}/?watch={id_watch}&episode"
    headers_watch = HEADERS.copy()
    headers_watch["Referer"] = referer_url
    try:
        r = session.get(url_watch, headers=headers_watch, timeout=12)
        match_json = re.search(r'var\s+(?:serie|videos|movie)\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
        if match_json:
            data = json.loads(match_json.group(1))
            return decodificar_json(data, nombre_web, nombre_temp_label, poster)
    except: pass
    return 0

# ==========================================
# MOTOR PRINCIPAL
# ==========================================
if __name__ == "__main__":
    if not SERVIDOR:
        print("Falta configurar la variable de entorno URL_SERVIDOR")
    else:
        urls_series = [f"{SERVIDOR}/?series"]
        for i in range(1, 60): 
            urls_series.append(f"{SERVIDOR}/?series&page={i}")

        for url_pagina in urls_series:
            print(f"\n📄 Página: {url_pagina}")
            try:
                r = session.get(url_pagina, timeout=10)
                ids_series = list(set(re.findall(r'[?&]item=([0-9]+)&serie', r.text)))
                
                if not ids_series: print("   (Sin series)")
                
                for id_serie in ids_series:
                    if id_serie in series_visitadas: continue
                    series_visitadas.add(id_serie)
                    
                    url_serie = f"{SERVIDOR}/?item={id_serie}&serie"
                    try:
                        r_serie = session.get(url_serie, timeout=10)
                        html_serie = r_serie.text
                        
                        # --- ANÁLISIS V18 (Verificación de Poster) ---
                        nombre_web, poster = analizar_html_serie(html_serie, id_serie)

                        print(f"  📺 {nombre_web}...", end="", flush=True)

                        ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', html_serie)))
                        extracted_total = 0

                        if ids_temporadas:
                            ids_temporadas.sort()
                            for id_temp in ids_temporadas:
                                url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                                r_temp = session.get(url_temp, timeout=10)
                                match_temp_name = re.search(r'(?:Temporada|Season)\s+(\d+)', r_temp.text, re.IGNORECASE)
                                nombre_temp_label = f"S{int(match_temp_name.group(1)):02d}" if match_temp_name else "Sxx"
                                
                                n = procesar_bloque_completo(id_temp, url_temp, nombre_web, nombre_temp_label, poster)
                                extracted_total += n
                        else:
                            match_id_oculto = re.search(r"location\.href\s*=\s*['\"]\.\./\?watch=(\d+)", html_serie)
                            id_maestro = None
                            if match_id_oculto:
                                id_maestro = match_id_oculto.group(1)
                            else:
                                match_btn = re.search(r"appClick\(['\"](\d+)['\"]", html_serie)
                                if match_btn: id_maestro = match_btn.group(1)
                            
                            if id_maestro:
                                n = procesar_bloque_completo(id_maestro, url_serie, nombre_web, "S01", poster)
                                extracted_total += n
                            else:
                                n = procesar_bloque_completo(id_serie, url_serie, nombre_web, "S01", poster)
                                extracted_total += n

                        if extracted_total > 0:
                            print(f" OK ({extracted_total} caps)")
                        else:
                            print(" (0 caps)")

                    except Exception as e:
                        print(f" [X] Error: {e}")

            except Exception as e:
                print(f"Error pagina: {e}")

        with open(ARCHIVO_SALIDA, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(contenido_m3u))
            
        print(f"\n✅ Generado {ARCHIVO_SALIDA} con {total_capitulos} capitulos.")
