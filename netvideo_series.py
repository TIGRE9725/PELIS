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

print("--- GENERADOR NETVIDEO SERIES V3 (FIX REGEX) ---")
print(f"Servidor: {SERVIDOR}")

contenido_m3u = ["#EXTM3U"]
total_capitulos = 0
series_visitadas = set()

session = requests.Session()
session.headers.update(HEADERS)

def obtener_link_final(id_watch, num_ep, referer_url):
    """Descifra el enlace Base64 del episodio"""
    url_watch = f"{SERVIDOR}/?watch={id_watch}&episode"
    headers_watch = HEADERS.copy()
    headers_watch["Referer"] = referer_url
    
    try:
        r_watch = session.get(url_watch, headers=headers_watch, timeout=8)
        # Buscar variable JSON 'var videos = [...]'
        match_json = re.search(r'var\s+videos\s*=\s*(\[.*?\]);', r_watch.text, re.DOTALL)
        
        if match_json:
            data_eps = json.loads(match_json.group(1))
            
            # Buscar por nombre "Episode X"
            target_name = f"Episode {num_ep}"
            episodio_data = next((x for x in data_eps if target_name in x.get("name", "")), None)
            
            # Si no encuentra por nombre, intentar por posición
            if not episodio_data and len(data_eps) >= int(num_ep):
                episodio_data = data_eps[int(num_ep)-1]
            
            if episodio_data:
                b64 = episodio_data["stream"].replace('\\/', '/')
                return base64.b64decode(b64).decode('utf-8').replace("\\/", "/")
    except:
        pass
    return None

# ==========================================
# 1. OBTENER SERIES
# ==========================================
urls_series = [f"{SERVIDOR}/?series"]
for i in range(1, 40): 
    urls_series.append(f"{SERVIDOR}/?series&page={i}")

for url_pagina in urls_series:
    print(f"\n📄 Página: {url_pagina}")
    
    try:
        r = session.get(url_pagina, timeout=10)
        
        # CORRECCIÓN IMPORTANTE: Regex más flexible
        # Antes buscaba href="./?item...", ahora busca cualquier ?item=...&serie
        ids_series = list(set(re.findall(r'[?&]item=([0-9]+)&serie', r.text)))
        
        if not ids_series:
            print("   (Sin series en esta página)")
        
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
                
                # Nombre
                match_titulo = re.search(r'<h2 class="post-title">([^<]+)</h2>', html_serie)
                nombre_serie = match_titulo.group(1).strip() if match_titulo else f"Serie {id_serie}"
                
                # Poster
                match_poster = re.search(r'src="(\.\./poster/[^"]+)"', html_serie)
                poster = SERVIDOR + match_poster.group(1).replace("..", "") if match_poster else ""

                print(f"  📺 {nombre_serie}...", end="", flush=True)

                # --- LÓGICA HÍBRIDA (Temporadas vs Directo) ---
                
                # Buscamos IDs de temporadas
                ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', html_serie)))
                
                episodios_encontrados = [] 

                if ids_temporadas:
                    # CASO 1: TIENE TEMPORADAS
                    for id_temp in ids_temporadas:
                        url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                        r_temp = session.get(url_temp, timeout=8)
                        html_temp = r_temp.text
                        
                        # Nombre Temp (S01, S02...)
                        nombre_temp_label = "Sxx"
                        match_temp_name = re.search(r'Season\s+(\d+)', html_temp, re.IGNORECASE)
                        if match_temp_name:
                            nombre_temp_label = f"S{int(match_temp_name.group(1)):02d}"
                        
                        # Buscar episodios
                        raw_eps = re.findall(r'[?&]watch=([0-9]+)&episode#([0-9]+)', html_temp)
                        
                        for id_watch, num_ep in raw_eps:
                            link = obtener_link_final(id_watch, num_ep, url_temp)
                            if link:
                                ep_str = f"E{int(num_ep):02d}"
                                titulo_cap = f"{nombre_serie} {nombre_temp_label}{ep_str}"
                                episodios_encontrados.append((titulo_cap, link))

                else:
                    # CASO 2: DIRECTO (Sin temporadas, asumimos S01)
                    raw_eps = re.findall(r'[?&]watch=([0-9]+)&episode#([0-9]+)', html_serie)
                    
                    for id_watch, num_ep in raw_eps:
                        link = obtener_link_final(id_watch, num_ep, url_serie) 
                        if link:
                            ep_str = f"E{int(num_ep):02d}"
                            titulo_cap = f"{nombre_serie} S01{ep_str}"
                            episodios_encontrados.append((titulo_cap, link))

                # Guardar
                if episodios_encontrados:
                    grupo = f"SERIES - {nombre_serie}"
                    for tit, lnk in episodios_encontrados:
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
