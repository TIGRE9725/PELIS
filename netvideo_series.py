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

print("--- NETVIDEO SERIES V4 (APPCLICK FIX) ---")
print(f"Servidor: {SERVIDOR}")

contenido_m3u = ["#EXTM3U"]
total_capitulos = 0
series_visitadas = set()

session = requests.Session()
session.headers.update(HEADERS)

def obtener_link_final(id_watch, num_ep, referer_url):
    """
    Decodifica el video.
    NOTA: El ID que viene del appClick ('994780') suele ser el ID directo del stream.
    """
    url_watch = f"{SERVIDOR}/?watch={id_watch}&episode"
    headers_watch = HEADERS.copy()
    headers_watch["Referer"] = referer_url
    
    try:
        r_watch = session.get(url_watch, headers=headers_watch, timeout=8)
        
        # Buscamos el JSON 'var videos = [...]' o 'var movie = [...]'
        match_json = re.search(r'var\s+(?:videos|movie)\s*=\s*(\[.*?\]);', r_watch.text, re.DOTALL)
        
        if match_json:
            data_eps = json.loads(match_json.group(1))
            
            # Estrategia 1: Buscar por "Episode X"
            target_name = f"Episode {num_ep}"
            episodio_data = next((x for x in data_eps if target_name in x.get("name", "")), None)
            
            # Estrategia 2: Buscar por "Movie" (si es directo)
            if not episodio_data:
                episodio_data = next((x for x in data_eps if "Movie" in x.get("name", "")), None)

            # Estrategia 3: Si solo hay 1 video en el JSON, es ese.
            if not episodio_data and len(data_eps) == 1:
                episodio_data = data_eps[0]
            
            # Estrategia 4: Por índice numérico (Episode 1 = index 0)
            if not episodio_data and len(data_eps) >= int(num_ep):
                episodio_data = data_eps[int(num_ep)-1]
            
            if episodio_data and "stream" in episodio_data:
                b64 = episodio_data["stream"].replace('\\/', '/')
                link = base64.b64decode(b64).decode('utf-8').replace("\\/", "/")
                return link.strip()
    except Exception as e:
        # print(f"Debug Decode Error: {e}") 
        pass
    return None

# ==========================================
# 1. OBTENER SERIES (PAGINACIÓN)
# ==========================================
# Aumentamos el rango de páginas para sacar todo
urls_series = [f"{SERVIDOR}/?series"]
for i in range(1, 60): 
    urls_series.append(f"{SERVIDOR}/?series&page={i}")

for url_pagina in urls_series:
    print(f"\n📄 Página: {url_pagina}")
    
    try:
        r = session.get(url_pagina, timeout=10)
        
        # Regex para sacar IDs de series (?item=XXXX&serie)
        # Soporta href="./?item..." y href="?item..."
        ids_series = list(set(re.findall(r'item=([0-9]+)&serie', r.text)))
        
        if not ids_series:
            print("   (Fin o sin series)")
            # Si detectamos una página vacía, podríamos romper el bucle, 
            # pero mejor seguimos por si hay huecos.
        
        for id_serie in ids_series:
            if id_serie in series_visitadas: continue
            series_visitadas.add(id_serie)
            
            # ==========================================
            # 2. DENTRO DE LA SERIE
            # ==========================================
            url_serie = f"{SERVIDOR}/?item={id_serie}&serie"
            try:
                r_serie = session.get(url_serie, timeout=10)
                html_serie = r_serie.text
                
                # Nombre Serie
                match_titulo = re.search(r'<h2 class="post-title">([^<]+)</h2>', html_serie)
                nombre_serie = match_titulo.group(1).strip() if match_titulo else f"Serie {id_serie}"
                
                # Poster
                match_poster = re.search(r'src="(\.\./poster/[^"]+)"', html_serie)
                poster = SERVIDOR + match_poster.group(1).replace("..", "") if match_poster else ""

                print(f"  📺 {nombre_serie}...", end="", flush=True)

                # --- LÓGICA DE TEMPORADAS ---
                # Buscamos enlaces a temporadas (?item=XXXX&season)
                ids_temporadas = list(set(re.findall(r'item=([0-9]+)&season', html_serie)))
                
                episodios_encontrados = [] 

                if ids_temporadas:
                    # CASO A: TIENE CARPETAS DE TEMPORADAS
                    ids_temporadas.sort() # Ordenar temp 1, 2, 3...
                    
                    for id_temp in ids_temporadas:
                        url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                        r_temp = session.get(url_temp, timeout=8)
                        html_temp = r_temp.text
                        
                        # Detectar numero temporada (Label)
                        nombre_temp_label = "Sxx"
                        match_temp_name = re.search(r'(?:Temporada|Season)\s+(\d+)', html_temp, re.IGNORECASE)
                        if match_temp_name:
                            nombre_temp_label = f"S{int(match_temp_name.group(1)):02d}"
                        
                        # --- NUEVO REGEX (APPCLICK) ---
                        # Busca: appClick('994780','1')
                        # Captura: Grupo 1 = ID Video, Grupo 2 = Numero Episodio
                        raw_eps = re.findall(r"appClick\(['\"](\d+)['\"],\s*['\"](\d+)['\"]\)", html_temp)
                        
                        for id_watch, num_ep in raw_eps:
                            link = obtener_link_final(id_watch, num_ep, url_temp)
                            if link:
                                ep_str = f"E{int(num_ep):02d}"
                                titulo_cap = f"{nombre_serie} {nombre_temp_label}{ep_str}"
                                episodios_encontrados.append((titulo_cap, link))

                else:
                    # CASO B: DIRECTO (Sin temporadas, buscamos appClick en la home de la serie)
                    raw_eps = re.findall(r"appClick\(['\"](\d+)['\"],\s*['\"](\d+)['\"]\)", html_serie)
                    
                    for id_watch, num_ep in raw_eps:
                        link = obtener_link_final(id_watch, num_ep, url_serie) 
                        if link:
                            ep_str = f"E{int(num_ep):02d}"
                            # Asumimos S01
                            titulo_cap = f"{nombre_serie} S01{ep_str}"
                            episodios_encontrados.append((titulo_cap, link))

                # --- GUARDAR ---
                if episodios_encontrados:
                    grupo = f"SERIES - {nombre_serie}"
                    for tit, lnk in episodios_encontrados:
                        # Si el link no tiene http, agregarlo (a veces pasa)
                        if not lnk.startswith("http"): lnk = SERVIDOR + lnk
                        
                        entry = f'#EXTINF:-1 tvg-id="" tvg-logo="{poster}" group-title="{grupo}",{tit}\n{lnk}'
                        contenido_m3u.append(entry)
                        total_capitulos += 1
                    print(f" OK ({len(episodios_encontrados)} caps)")
                else:
                    print(" (0 caps)")

            except Exception as e:
                print(f" [X] Error serie: {e}")

    except Exception as e:
        print(f"Error pagina: {e}")

# Guardar M3U
with open(ARCHIVO_SALIDA, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(contenido_m3u))

print(f"\n✅ FINALIZADO. {total_capitulos} episodios guardados.")
