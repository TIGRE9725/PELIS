import requests
import re
import base64
import json
import os
import urllib.parse
import time

COOKIE = "setLenguaje=spa"
SERVIDOR = os.environ.get("URL_SERVIDOR")
ARCHIVO_SALIDA = "netvideo_series.json"

HEADERS = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0",
    "Referer": SERVIDOR
}

print("--- NETVIDEO SERIES JSON (SINOPSIS & EPISODE POSTER) ---")
session = requests.Session()
session.headers.update(HEADERS)

def limpiar_texto_html(texto):
    if not texto: return ""
    return texto.replace("&amp;", "&").replace("&#038;", "&").replace("&quot;", '"').strip()

def limpiar_nombre_grupo(nombre_sucio):
    if not nombre_sucio: return "Series Varias"
    nombre = urllib.parse.unquote(nombre_sucio).replace('_', ' ').replace('-', ' ').replace('.', ' ')
    nombre = re.sub(r'\bS\d+\s*E\d+\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\b\d+x\d+\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\s+\d+\s+\d+$', '', nombre) 
    nombre = re.sub(r'\b(480|720|1080)[p]?\b', '', nombre, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', nombre).strip()

def verificar_url_existe(url):
    if not url: return False
    try:
        return session.head(url, timeout=2, allow_redirects=True).status_code == 200
    except: return False

def analizar_html_serie(html, id_serie):
    nombre_final = f"Serie {id_serie}"
    poster_final = ""
    sinopsis_final = "Sin descripción disponible."

    # 1. NOMBRE Y SINOPSIS
    match_bloque = re.search(r'<h2[^>]*>(.*?)</h2>\s*<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if match_bloque:
        texto_h2 = limpiar_texto_html(match_bloque.group(1))
        texto_p = limpiar_texto_html(match_bloque.group(2))
        nombre_final = texto_h2
        # Si el párrafo no son solo géneros, es la sinopsis
        if len(texto_p) > 30 and not ("," in texto_p and len(texto_p) < 60):
            sinopsis_final = texto_p
    
    # Intento 2 para sinopsis (divs de descripción comunes)
    if sinopsis_final == "Sin descripción disponible.":
        match_desc = re.search(r'<div[^>]*class="description"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
        if match_desc:
            sinopsis_final = re.sub('<[^<]+?>', '', match_desc.group(1)).strip()

    # 2. POSTER (Tu lógica V18 intacta)
    match_bg = re.search(r'background-image:\s*url\(([^)]+)\)', html, re.IGNORECASE)
    if match_bg:
        bg_url_raw = match_bg.group(1).replace('"', '').replace("'", "").strip()
        if not bg_url_raw.startswith("http"): bg_url_raw = SERVIDOR + bg_url_raw.replace("..", "")
        poster_original = bg_url_raw
        poster_hack = bg_url_raw.replace('/original/', '/w410/')
        poster_hack = re.sub(r'p(\.(jpg|png|jpeg))$', r'i\1', poster_hack, flags=re.IGNORECASE)
        
        if verificar_url_existe(poster_hack): poster_final = poster_hack
        else: poster_final = poster_original
    else:
        match_fallback = re.search(r'src="(\.\./poster/w410/[^"]+)"', html)
        if match_fallback: poster_final = SERVIDOR + match_fallback.group(1).replace("..", "")

    return nombre_final, poster_final, sinopsis_final

def decodificar_json(data_json, nombre_web, nombre_temp_label, poster_serie):
    episodios = []
    try: data_json.sort(key=lambda x: int(x.get('number', 0)))
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
                
                # --- AQUÍ ESTÁ LA SOLUCIÓN DEL PÓSTER DEL CAPÍTULO ---
                # Buscamos 'poster', 'image' o 'screenshot' en el JSON del episodio. Si no hay, usamos el de la serie.
                img_capitulo = ep.get('poster') or ep.get('image') or ep.get('screenshot') or poster_serie
                if img_capitulo and not img_capitulo.startswith("http"):
                    img_capitulo = SERVIDOR + img_capitulo.replace("..", "")

                ep_str = f"E{int(num_ep):02d}"
                titulo_cap = f"{grupo_general} {nombre_temp_label}{ep_str}"
                
                episodios.append({
                    "title": titulo_cap,
                    "duration": ep.get('duration', '45m'),
                    "img": img_capitulo, # Imagen individual por episodio
                    "mpd": link_sucio,
                    "drm": None
                })
        except: pass
    return episodios

def procesar_bloque_completo(id_watch, referer_url, nombre_web, nombre_temp_label, poster_serie):
    url_watch = f"{SERVIDOR}/?watch={id_watch}&episode"
    headers_watch = HEADERS.copy()
    headers_watch["Referer"] = referer_url
    try:
        r = session.get(url_watch, headers=headers_watch, timeout=12)
        match_json = re.search(r'var\s+(?:serie|videos|movie)\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
        if match_json:
            data = json.loads(match_json.group(1))
            return decodificar_json(data, nombre_web, nombre_temp_label, poster_serie)
    except: pass
    return []

if __name__ == "__main__":
    if not SERVIDOR:
        print("Falta configurar la variable de entorno URL_SERVIDOR")
        exit()

    urls_series = [f"{SERVIDOR}/?series"]
    for i in range(1, 60): urls_series.append(f"{SERVIDOR}/?series&page={i}")

    series_visitadas = set()
    catalogo_series = []

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

                    ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', html_serie)))
                    temporadas_finales = []
                    caps_totales = 0

                    if ids_temporadas:
                        ids_temporadas.sort()
                        for id_temp in ids_temporadas:
                            url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                            r_temp = session.get(url_temp, timeout=10)
                            match_temp_name = re.search(r'(?:Temporada|Season)\s+(\d+)', r_temp.text, re.IGNORECASE)
                            num_temporada = int(match_temp_name.group(1)) if match_temp_name else 1
                            nombre_temp_label = f"S{num_temporada:02d}"
                            
                            eps = procesar_bloque_completo(id_temp, url_temp, nombre_web, nombre_temp_label, poster)
                            if eps:
                                temporadas_finales.append({
                                    "season_number": num_temporada,
                                    "episodes": eps
                                })
                                caps_totales += len(eps)
                    else:
                        match_id_oculto = re.search(r"location\.href\s*=\s*['\"]\.\./\?watch=(\d+)", html_serie)
                        id_maestro = match_id_oculto.group(1) if match_id_oculto else None
                        if not id_maestro:
                            match_btn = re.search(r"appClick\(['\"](\d+)['\"]", html_serie)
                            if match_btn: id_maestro = match_btn.group(1)
                        
                        id_a_procesar = id_maestro if id_maestro else id_serie
                        eps = procesar_bloque_completo(id_a_procesar, url_serie, nombre_web, "S01", poster)
                        if eps:
                            temporadas_finales.append({
                                "season_number": 1,
                                "episodes": eps
                            })
                            caps_totales += len(eps)

                    if caps_totales > 0:
                        catalogo_series.append({
                            "id": nombre_web,
                            "tipo": "NET-Series",
                            "imdbID": f"net_{id_serie}",
                            "sinopsis": sinopsis,
                            "poster": poster,
                            "seasons": temporadas_finales
                        })
                        print(f" OK ({caps_totales} caps)")
                    else:
                        print(" (0 caps)")
                except Exception as e:
                    print(f" [X] Error: {e}")

        except Exception as e:
            print(f"Error pagina: {e}")

    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
        json.dump(catalogo_series, f, indent=4, ensure_ascii=False)
        
    print(f"\n✅ Generado {ARCHIVO_SALIDA} con {len(catalogo_series)} series.")
