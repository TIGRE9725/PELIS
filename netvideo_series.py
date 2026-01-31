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

print("--- NETVIDEO SERIES V5 (JSON BULK EXTRACTOR) ---")
print(f"Servidor: {SERVIDOR}")

contenido_m3u = ["#EXTM3U"]
total_capitulos = 0
series_visitadas = set()

session = requests.Session()
session.headers.update(HEADERS)

def extraer_temporada_completa(url_watch, referer_url, nombre_serie, nombre_temp_label, poster):
    """
    Entra a un episodio, roba el JSON 'var serie' y saca TODOS los caps de la temporada.
    Devuelve la cantidad de episodios encontrados.
    """
    global total_capitulos
    caps_encontrados = 0
    
    headers_watch = HEADERS.copy()
    headers_watch["Referer"] = referer_url
    
    try:
        r = session.get(url_watch, headers=headers_watch, timeout=10)
        
        # BUSCAR LA VARIABLE MÁGICA: var serie = [{...}];
        match_json = re.search(r'var\s+serie\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
        
        if match_json:
            data = json.loads(match_json.group(1))
            # Ordenar por numero de episodio
            data.sort(key=lambda x: int(x.get('number', 0)))
            
            for ep in data:
                try:
                    num_ep = ep.get('number')
                    # Preferencia: Latino (spa) -> Subtitulado (sub)
                    b64 = ep.get('mp4_spa')
                    if not b64: b64 = ep.get('mp4_sub')
                    
                    if b64:
                        # Decodificar
                        b64 = b64.replace('\\/', '/')
                        link = base64.b64decode(b64).decode('utf-8').replace("\\/", "/").strip()
                        
                        if not link.startswith("http"): link = SERVIDOR + link
                        
                        # Formatear
                        ep_str = f"E{int(num_ep):02d}"
                        titulo_cap = f"{nombre_serie} {nombre_temp_label}{ep_str}"
                        grupo = f"SERIES - {nombre_serie}"
                        
                        # Guardar
                        entry = f'#EXTINF:-1 tvg-id="" tvg-logo="{poster}" group-title="{grupo}",{titulo_cap}\n{link}'
                        contenido_m3u.append(entry)
                        caps_encontrados += 1
                        total_capitulos += 1
                except:
                    pass
            
            if caps_encontrados > 0:
                print(f"    -> ¡Éxito! Extraídos {caps_encontrados} episodios de golpe.")
                return True
                
    except Exception as e:
        print(f"    [Error extractor: {e}]")
    
    return False

# ==========================================
# 1. OBTENER SERIES (PAGINACIÓN)
# ==========================================
urls_series = [f"{SERVIDOR}/?series"]
for i in range(1, 50): 
    urls_series.append(f"{SERVIDOR}/?series&page={i}")

for url_pagina in urls_series:
    print(f"\n📄 Página: {url_pagina}")
    
    try:
        r = session.get(url_pagina, timeout=10)
        # Buscar IDs de series
        ids_series = list(set(re.findall(r'[?&]item=([0-9]+)&serie', r.text)))
        
        if not ids_series: print("   (Sin series)")
        
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
                
                # Info Basica
                match_titulo = re.search(r'<h2 class="post-title">([^<]+)</h2>', html_serie)
                nombre_serie = match_titulo.group(1).strip() if match_titulo else f"Serie {id_serie}"
                
                match_poster = re.search(r'src="(\.\./poster/[^"]+)"', html_serie)
                poster = SERVIDOR + match_poster.group(1).replace("..", "") if match_poster else ""

                print(f"  📺 {nombre_serie}...", end="", flush=True)

                # --- LÓGICA DE TEMPORADAS ---
                ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', html_serie)))
                
                extracted_any = False

                if ids_temporadas:
                    # CASO A: TIENE TEMPORADAS
                    print("")
                    ids_temporadas.sort()
                    for id_temp in ids_temporadas:
                        url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                        r_temp = session.get(url_temp, timeout=10)
                        html_temp = r_temp.text
                        
                        # Nombre Temp (S01)
                        nombre_temp_label = "Sxx"
                        match_temp_name = re.search(r'(?:Temporada|Season)\s+(\d+)', html_temp, re.IGNORECASE)
                        if match_temp_name:
                            nombre_temp_label = f"S{int(match_temp_name.group(1)):02d}"
                        
                        # BUSCAR CUALQUIER EPISODIO PARA ENTRAR AL JSON
                        # Buscamos 'appClick' o 'href'
                        match_ep = re.search(r"appClick\(['\"](\d+)['\"]", html_temp)
                        if not match_ep:
                            match_ep = re.search(r'[?&]watch=([0-9]+)&episode', html_temp)
                        
                        if match_ep:
                            id_watch = match_ep.group(1)
                            url_watch = f"{SERVIDOR}/?watch={id_watch}&episode"
                            print(f"    - Procesando {nombre_temp_label}...", end="")
                            if extraer_temporada_completa(url_watch, url_temp, nombre_serie, nombre_temp_label, poster):
                                extracted_any = True
                        else:
                            print(f"    - {nombre_temp_label} vacía o sin enlaces.")

                else:
                    # CASO B: DIRECTO (Sin temporadas, asumimos S01)
                    # Buscamos un episodio en la home de la serie
                    match_ep = re.search(r"appClick\(['\"](\d+)['\"]", html_serie)
                    if not match_ep:
                        match_ep = re.search(r'[?&]watch=([0-9]+)&episode', html_serie)
                    
                    if match_ep:
                        id_watch = match_ep.group(1)
                        url_watch = f"{SERVIDOR}/?watch={id_watch}&episode"
                        print(" [Modo Directo]...", end="")
                        if extraer_temporada_completa(url_watch, url_serie, nombre_serie, "S01", poster):
                            extracted_any = True
                    else:
                        print(" (Sin episodios visibles)")

            except Exception as e:
                print(f" [X] Error: {e}")

    except Exception as e:
        print(f"Error pagina: {e}")

# Guardar M3U
with open(ARCHIVO_SALIDA, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(contenido_m3u))

print(f"\n✅ FINALIZADO. {total_capitulos} episodios guardados en {ARCHIVO_SALIDA}")
