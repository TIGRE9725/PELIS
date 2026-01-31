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

print("--- NETVIDEO SERIES V6 (ID MAESTRO) ---")
print(f"Servidor: {SERVIDOR}")

contenido_m3u = ["#EXTM3U"]
total_capitulos = 0
series_visitadas = set()

session = requests.Session()
session.headers.update(HEADERS)

def decodificar_json(data_json, nombre_serie, nombre_temp_label, poster):
    """Procesa el JSON que entrega el servidor con todos los capítulos"""
    global total_capitulos
    caps_count = 0
    
    # Ordenar por número de episodio
    try:
        data_json.sort(key=lambda x: int(x.get('number', 0)))
    except: pass

    for ep in data_json:
        try:
            num_ep = ep.get('number', 0)
            
            # --- BUSCAR EL ENLACE EN LAS LLAVES DISPONIBLES ---
            # Prioridad: mp4_spa (Latino) -> mp4_sub (Sub) -> stream (Generico) -> hls
            b64 = ep.get('mp4_spa')
            if not b64: b64 = ep.get('mp4_sub')
            if not b64: b64 = ep.get('stream')
            if not b64: b64 = ep.get('hls_spa')
            
            if b64:
                # Decodificar Base64
                b64 = b64.replace('\\/', '/')
                link = base64.b64decode(b64).decode('utf-8').replace("\\/", "/").strip()
                
                if not link.startswith("http"): link = SERVIDOR + link
                
                # Crear Título
                ep_str = f"E{int(num_ep):02d}"
                titulo_cap = f"{nombre_serie} {nombre_temp_label}{ep_str}"
                grupo = f"SERIES - {nombre_serie}"
                
                # Guardar
                entry = f'#EXTINF:-1 tvg-id="" tvg-logo="{poster}" group-title="{grupo}",{titulo_cap}\n{link}'
                contenido_m3u.append(entry)
                caps_count += 1
                total_capitulos += 1
        except Exception as e:
            pass
            
    return caps_count

def procesar_bloque_completo(id_contenedor, referer_url, nombre_serie, nombre_temp_label, poster):
    """
    Usa el ID del Contenedor (Temporada o Serie) para sacar todo el JSON.
    URL: ?watch={ID_CONTENEDOR}&episode
    """
    url_watch = f"{SERVIDOR}/?watch={id_contenedor}&episode"
    headers_watch = HEADERS.copy()
    headers_watch["Referer"] = referer_url
    
    try:
        r = session.get(url_watch, headers=headers_watch, timeout=12)
        
        # Buscar variable JSON 'var serie = [...]' o 'var videos = [...]'
        match_json = re.search(r'var\s+(?:serie|videos|movie)\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
        
        if match_json:
            data = json.loads(match_json.group(1))
            return decodificar_json(data, nombre_serie, nombre_temp_label, poster)
    except:
        pass
    return 0

# ==========================================
# 1. BUCLE PRINCIPAL DE PÁGINAS
# ==========================================
urls_series = [f"{SERVIDOR}/?series"]
for i in range(1, 60): 
    urls_series.append(f"{SERVIDOR}/?series&page={i}")

for url_pagina in urls_series:
    print(f"\n📄 Página: {url_pagina}")
    
    try:
        r = session.get(url_pagina, timeout=10)
        # Regex flexible para encontrar series
        ids_series = list(set(re.findall(r'[?&]item=([0-9]+)&serie', r.text)))
        
        if not ids_series: print("   (Sin series)")
        
        for id_serie in ids_series:
            if id_serie in series_visitadas: continue
            series_visitadas.add(id_serie)
            
            # ==========================================
            # 2. ANALIZAR SERIE
            # ==========================================
            url_serie = f"{SERVIDOR}/?item={id_serie}&serie"
            try:
                r_serie = session.get(url_serie, timeout=10)
                html_serie = r_serie.text
                
                # Datos Visuales
                match_titulo = re.search(r'<h2 class="post-title">([^<]+)</h2>', html_serie)
                nombre_serie = match_titulo.group(1).strip() if match_titulo else f"Serie {id_serie}"
                
                match_poster = re.search(r'src="(\.\./poster/[^"]+)"', html_serie)
                poster = SERVIDOR + match_poster.group(1).replace("..", "") if match_poster else ""

                print(f"  📺 {nombre_serie}...", end="", flush=True)

                # ==========================================
                # 3. DETECTAR ESTRUCTURA (TEMPORADAS O DIRECTO)
                # ==========================================
                ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', html_serie)))
                
                extracted_total = 0

                if ids_temporadas:
                    # CASO A: TIENE TEMPORADAS (Extraemos ID de la Temp y lo usamos en WATCH)
                    ids_temporadas.sort()
                    for id_temp in ids_temporadas:
                        # Obtenemos info de la temporada para saber el número (S01, S02...)
                        url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                        r_temp = session.get(url_temp, timeout=10)
                        
                        nombre_temp_label = "Sxx"
                        match_temp_name = re.search(r'(?:Temporada|Season)\s+(\d+)', r_temp.text, re.IGNORECASE)
                        if match_temp_name:
                            nombre_temp_label = f"S{int(match_temp_name.group(1)):02d}"
                        
                        # ¡MAGIA! Usamos el ID de la TEMPORADA (id_temp) directamente
                        # No necesitamos buscar episodios individuales.
                        # El servidor nos dará todos los caps de la temp con este ID.
                        n = procesar_bloque_completo(id_temp, url_temp, nombre_serie, nombre_temp_label, poster)
                        extracted_total += n
                        
                else:
                    # CASO B: DIRECTO (Usamos el ID de la SERIE directamente en WATCH)
                    # Esto cubre el caso de "Serie 615" que sí funcionó
                    n = procesar_bloque_completo(id_serie, url_serie, nombre_serie, "S01", poster)
                    extracted_total += n

                # Reporte final de la serie
                if extracted_total > 0:
                    print(f" OK ({extracted_total} caps)")
                else:
                    print(" (0 caps)")

            except Exception as e:
                print(f" [X] Error: {e}")

    except Exception as e:
        print(f"Error pagina: {e}")

# Guardar M3U
with open(ARCHIVO_SALIDA, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(contenido_m3u))

print(f"\n✅ FINALIZADO. {total_capitulos} episodios guardados.")
