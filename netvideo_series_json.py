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

print("--- NETVIDEO SERIES JSON (LÓGICA ORIGINAL RESTAURADA) ---")

session = requests.Session()
session.headers.update(HEADERS)

# =======================================================
# LÓGICAS ORIGINALES RESTAURADAS EXACTAMENTE COMO LAS TENÍAS
# =======================================================
def limpiar_texto_html(texto):
    if not texto: return ""
    txt = texto.replace("&amp;", "&").replace("&#038;", "&").replace("&quot;", '"')
    return txt.strip()

def limpiar_nombre_grupo(nombre_sucio):
    """Limpia el nombre para agrupar (Lógica Original)"""
    if not nombre_sucio: return "Series Varias"
    nombre = urllib.parse.unquote(nombre_sucio)
    nombre = nombre.replace('_', ' ').replace('-', ' ').replace('.', ' ')
    nombre = re.sub(r'\bS\d+\s*E\d+\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\b\d+x\d+\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\s+\d+\s+\d+$', '', nombre) 
    nombre = re.sub(r'\b(480|720|1080)[p]?\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\s+', ' ', nombre).strip()
    if len(nombre) < 2: return nombre_sucio
    return nombre

def extraer_nombre_del_archivo(url):
    """Analiza el nombre del archivo SIN token (Lógica Original)"""
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
    if not texto: return False
    texto_lower = texto.lower()
    keywords = ['acción', 'accion', 'aventura', 'adventura', 'drama', 'comedia', 'animación', 'animacion', 'sci-fi', 'fantasía', 'fantasia', 'terror', 'suspenso', 'romance', 'crimen', 'documental', 'western', 'familia']
    matches = sum(1 for k in keywords if k in texto_lower)
    if ("," in texto or "&" in texto) and matches >= 1: return True
    if matches >= 2: return True
    if texto_lower.strip() in keywords: return True
    return False

def verificar_url_existe(url):
    if not url: return False
    try:
        return session.head(url, timeout=2, allow_redirects=True).status_code == 200
    except: return False

# =======================================================
# EXTRACCIÓN HTML Y CONSTRUCCIÓN DE JSON
# =======================================================
def analizar_html_serie(html, id_serie):
    nombre_final = f"Serie {id_serie}"
    poster_final = ""
    sinopsis_final = "Sin descripción disponible."

    match_bloque = re.search(r'<h2[^>]*>(.*?)</h2>\s*<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if match_bloque:
        texto_h2 = limpiar_texto_html(match_bloque.group(1))
        texto_p = limpiar_texto_html(match_bloque.group(2))
        nombre_final = texto_h2 if es_lista_de_generos(texto_p) else texto_p
    else:
        match_h2 = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)
        if match_h2: nombre_final = limpiar_texto_html(match_h2.group(1))

    # Nueva lógica de Sinopsis
    match_desc = re.search(r'<div[^>]*class="[^"]*w3-descripcion[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
    if match_desc:
        sinopsis_final = re.sub(r'<[^<]+?>', '', match_desc.group(1)).strip()

    # Póster (Tu lógica V18)
    match_bg = re.search(r'background-image:\s*url\(([^)]+)\)', html, re.IGNORECASE)
    if match_bg:
        bg_url_raw = match_bg.group(1).replace('"', '').replace("'", "").strip()
        if not bg_url_raw.startswith("http"): bg_url_raw = SERVIDOR + bg_url_raw.replace("..", "")
        poster_original = bg_url_raw
        poster_hack = bg_url_raw.replace('/original/', '/w410/')
        poster_hack = re.sub(r'p(\.(jpg|png|jpeg))$', r'i\1', poster_hack, flags=re.IGNORECASE)
        poster_final = poster_hack if verificar_url_existe(poster_hack) else poster_original
    else:
        match_fallback = re.search(r'src="(\.\./poster/w410/[^"]+)"', html)
        if match_fallback: poster_final = SERVIDOR + match_fallback.group(1).replace("..", "")

    return nombre_final, poster_final, sinopsis_final

def armar_episodios_json(data_json, nombre_web, num_temporada, diccionario_posters, poster_serie):
    """Combina tu lógica de URLs limpias con la estructura JSON de TIGRE+"""
    episodios = []
    try: data_json.sort(key=lambda x: int(x.get('number', 0)))
    except: pass

    grupo_general = limpiar_nombre_grupo(nombre_web)
    nombre_temp_label = f"S{num_temporada:02d}"

    for ep in data_json:
        try:
            num_ep = ep.get('number', 0)
            id_ep_str = str(ep.get('id', ''))
            b64 = ep.get('mp4_spa') or ep.get('mp4_sub') or ep.get('stream') or ep.get('hls_spa')
            
            if b64:
                b64 = b64.replace('\\/', '/')
                link_sucio = base64.b64decode(b64).decode('utf-8').replace("\\/", "/").strip()
                if not link_sucio.startswith("http"): link_sucio = SERVIDOR + link_sucio
                
                # TU LÓGICA ORIGINAL PARA TÍTULOS PERFECTOS
                nombre_archivo = extraer_nombre_del_archivo(link_sucio)
                nombre_base = nombre_archivo if nombre_archivo else grupo_general
                ep_str = f"E{int(num_ep):02d}"
                titulo_cap = f"{nombre_base} {nombre_temp_label}{ep_str}"
                
                # Asignar el póster específico si lo logramos capturar
                img_ep = diccionario_posters.get(id_ep_str, poster_serie)

                episodios.append({
                    "title": titulo_cap.strip(),
                    "duration": "22m", 
                    "img": img_ep,
                    "mpd": link_sucio,
                    "drm": None
                })
        except: pass
    return episodios

# ==========================================
# MOTOR PRINCIPAL
# ==========================================
if __name__ == "__main__":
    if not SERVIDOR:
        print("Falta configurar la variable de entorno URL_SERVIDOR")
        exit()

    urls_series = [f"{SERVIDOR}/?series"]
    for i in range(1, 60): 
        urls_series.append(f"{SERVIDOR}/?series&page={i}")

    series_visitadas = set()
    catalogo_series = []
    total_capitulos = 0

    for url_pagina in urls_series:
        print(f"\n📄 Página: {url_pagina}")
        try:
            r = session.get(url_pagina, timeout=10)
            ids_series = list(set(re.findall(r'[?&]item=([0-9]+)&serie', r.text)))
            
            for id_serie in ids_series:
                if id_serie in series_visitadas: continue
                series_visitadas.add(id_serie)
                
                url_serie = f"{SERVIDOR}/?item={id_serie}&serie"
                try:
                    r_serie = session.get(url_serie, timeout=10)
                    html_serie = r_serie.text
                    
                    nombre_web, poster, sinopsis = analizar_html_serie(html_serie, id_serie)
                    print(f"  📺 {nombre_web}...", end="", flush=True)

                    # --- LÓGICA DE TEMPORADAS MÚLTIPLES ---
                    ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', html_serie)))
                    temporadas_finales = []
                    caps_en_serie = 0

                    if ids_temporadas:
                        ids_temporadas.sort()
                        for id_temp in ids_temporadas:
                            url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                            r_temp = session.get(url_temp, timeout=10)
                            html_temp = r_temp.text
                            
                            # Tu lógica para extraer el número de temporada real
                            match_temp_name = re.search(r'(?:Temporada|Season)\s+(\d+)', html_temp, re.IGNORECASE)
                            num_temporada = int(match_temp_name.group(1)) if match_temp_name else (ids_temporadas.index(id_temp) + 1)
                            
                            # 1. Mapear Pósters de los episodios desde la vista de temporada
                            diccionario_posters = {}
                            bloques_ep = re.findall(r"appClick\('(\d+)'[^>]*>.*?<img src=\"([^\"]+)\"", html_temp, re.DOTALL | re.IGNORECASE)
                            for id_ep, img_path in bloques_ep:
                                full_img = img_path.replace("..", "")
                                if not full_img.startswith("http"): full_img = SERVIDOR + full_img
                                diccionario_posters[id_ep] = full_img

                            # 2. Entrar al primer capítulo para sacar el JSON de todos los episodios
                            primer_cap_id = None
                            match_primer_cap = re.search(r"appClick\('(\d+)'", html_temp)
                            if match_primer_cap: primer_cap_id = match_primer_cap.group(1)
                            
                            if primer_cap_id:
                                url_watch = f"{SERVIDOR}/?watch={primer_cap_id}&episode"
                                headers_watch = HEADERS.copy()
                                headers_watch["Referer"] = url_temp
                                r_watch = session.get(url_watch, headers=headers_watch, timeout=12)
                                
                                # Tu regex original segura
                                match_json = re.search(r'var\s+(?:serie|videos|movie)\s*=\s*(\[.*?\]);', r_watch.text, re.DOTALL)
                                if match_json:
                                    data_json = json.loads(match_json.group(1))
                                    eps = armar_episodios_json(data_json, nombre_web, num_temporada, diccionario_posters, poster)
                                    if eps:
                                        temporadas_finales.append({"season_number": num_temporada, "episodes": eps})
                                        caps_en_serie += len(eps)

                    else:
                        # --- LÓGICA DE TEMPORADA ÚNICA (TU ORIGINAL) ---
                        match_id_oculto = re.search(r"location\.href\s*=\s*['\"]\.\./\?watch=(\d+)", html_serie)
                        id_maestro = match_id_oculto.group(1) if match_id_oculto else None
                        if not id_maestro:
                            match_btn = re.search(r"appClick\(['\"](\d+)['\"]", html_serie)
                            if match_btn: id_maestro = match_btn.group(1)
                        
                        id_a_procesar = id_maestro if id_maestro else id_serie
                        
                        # Al ser temporada única, el JSON de los episodios está directamente ahí
                        url_watch = f"{SERVIDOR}/?watch={id_a_procesar}&episode"
                        headers_watch = HEADERS.copy()
                        headers_watch["Referer"] = url_serie
                        r_watch = session.get(url_watch, headers=headers_watch, timeout=12)
                        
                        match_json = re.search(r'var\s+(?:serie|videos|movie)\s*=\s*(\[.*?\]);', r_watch.text, re.DOTALL)
                        if match_json:
                            data_json = json.loads(match_json.group(1))
                            # Como no tenemos diccionario de pósters, enviamos diccionario vacío y usará el de la serie
                            eps = armar_episodios_json(data_json, nombre_web, 1, {}, poster)
                            if eps:
                                temporadas_finales.append({"season_number": 1, "episodes": eps})
                                caps_en_serie += len(eps)

                    # Guardar si se encontraron episodios
                    if temporadas_finales:
                        catalogo_series.append({
                            "id": nombre_web,
                            "tipo": "NET-Series",
                            "imdbID": f"net_{id_serie}",
                            "sinopsis": sinopsis,
                            "poster": poster,
                            "seasons": temporadas_finales
                        })
                        total_capitulos += caps_en_serie
                        print(f" OK ({caps_en_serie} caps)")
                    else:
                        print(" (0 caps)")

                except Exception as e:
                    print(f" [X] Error: {e}")

        except Exception as e:
            print(f"Error pagina: {e}")

    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
        json.dump(catalogo_series, f, indent=4, ensure_ascii=False)
        
    print(f"\n✅ Generado {ARCHIVO_SALIDA} con {len(catalogo_series)} series y {total_capitulos} episodios.")
