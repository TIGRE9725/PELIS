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

print("--- NETVIDEO SERIES V8 (ID OCULTO FIX) ---")
print(f"Servidor: {SERVIDOR}")

contenido_m3u = ["#EXTM3U"]
total_capitulos = 0
series_visitadas = set()

session = requests.Session()
session.headers.update(HEADERS)

def limpiar_titulo(texto):
    if not texto: return ""
    # Decodificar entidades HTML y limpiar
    texto = texto.replace("&amp;", "&").replace("&#038;", "&")
    return texto.strip()

def obtener_nombre_serie(html, id_serie):
    """Extrae el nombre real de la serie"""
    # 1. Title tag
    match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
    if match:
        titulo = match.group(1).replace(" - Series", "").strip()
        if titulo and "Watch" not in titulo: return limpiar_titulo(titulo)
    
    # 2. H2 Bold
    match = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)
    if match: return limpiar_titulo(match.group(1))

    return f"Serie {id_serie}"

def decodificar_json(data_json, nombre_serie, nombre_temp_label, poster):
    global total_capitulos
    caps_count = 0
    
    try:
        data_json.sort(key=lambda x: int(x.get('number', 0)))
    except: pass

    for ep in data_json:
        try:
            num_ep = ep.get('number', 0)
            
            # Buscar enlace (spa > sub > stream)
            b64 = ep.get('mp4_spa')
            if not b64: b64 = ep.get('mp4_sub')
            if not b64: b64 = ep.get('stream')
            if not b64: b64 = ep.get('hls_spa')
            
            if b64:
                b64 = b64.replace('\\/', '/')
                link = base64.b64decode(b64).decode('utf-8').replace("\\/", "/").strip()
                if not link.startswith("http"): link = SERVIDOR + link
                
                ep_str = f"E{int(num_ep):02d}"
                titulo_cap = f"{nombre_serie} {nombre_temp_label}{ep_str}"
                grupo = f"SERIES - {nombre_serie}"
                
                entry = f'#EXTINF:-1 tvg-id="" tvg-logo="{poster}" group-title="{grupo}",{titulo_cap}\n{link}'
                contenido_m3u.append(entry)
                caps_count += 1
                total_capitulos += 1
        except: pass
    return caps_count

def procesar_bloque_completo(id_watch_real, referer_url, nombre_serie, nombre_temp_label, poster):
    """Pide el JSON usando el ID correcto (el oculto o el de temporada)"""
    url_watch = f"{SERVIDOR}/?watch={id_watch_real}&episode"
    headers_watch = HEADERS.copy()
    headers_watch["Referer"] = referer_url
    
    try:
        r = session.get(url_watch, headers=headers_watch, timeout=12)
        match_json = re.search(r'var\s+(?:serie|videos|movie)\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
        if match_json:
            data = json.loads(match_json.group(1))
            return decodificar_json(data, nombre_serie, nombre_temp_label, poster)
    except: pass
    return 0

# ==========================================
# MOTOR PRINCIPAL
# ==========================================
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
                
                nombre_serie = obtener_nombre_serie(html_serie, id_serie)
                
                match_poster = re.search(r'src="(\.\./poster/[^"]+)"', html_serie)
                poster = SERVIDOR + match_poster.group(1).replace("..", "") if match_poster else ""

                print(f"  📺 {nombre_serie}...", end="", flush=True)

                # Buscar Temporadas
                ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', html_serie)))
                extracted_total = 0

                if ids_temporadas:
                    # CASO A: Con carpetas de Temporada
                    ids_temporadas.sort()
                    for id_temp in ids_temporadas:
                        url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                        r_temp = session.get(url_temp, timeout=10)
                        
                        nombre_temp_label = "Sxx"
                        match_temp_name = re.search(r'(?:Temporada|Season)\s+(\d+)', r_temp.text, re.IGNORECASE)
                        if match_temp_name:
                            nombre_temp_label = f"S{int(match_temp_name.group(1)):02d}"
                        
                        # ID Temporada -> directo al Watch
                        n = procesar_bloque_completo(id_temp, url_temp, nombre_serie, nombre_temp_label, poster)
                        extracted_total += n
                else:
                    # CASO B: DIRECTO (Sin carpeta de temporada)
                    # ¡AQUÍ ESTÁ EL TRUCO!
                    
                    # 1. Buscamos el ID OCULTO en el javascript 'location.href = ...?watch=XXXX'
                    # El regex busca: ?watch=NUMEROS
                    match_id_oculto = re.search(r"location\.href\s*=\s*['\"]\.\./\?watch=(\d+)", html_serie)
                    
                    id_maestro = None
                    if match_id_oculto:
                        id_maestro = match_id_oculto.group(1)
                        # print(f" [ID Oculto JS: {id_maestro}]", end="")
                    else:
                        # 2. Si no hay script, buscamos el primer botón appClick y sacamos su ID
                        # appClick('5180812','1') -> Usamos 5180812 como intento
                        match_btn = re.search(r"appClick\(['\"](\d+)['\"]", html_serie)
                        if match_btn:
                            id_maestro = match_btn.group(1)
                            # print(f" [ID Botón: {id_maestro}]", end="")
                    
                    if id_maestro:
                        # Intentamos sacar todo con ese ID
                        n = procesar_bloque_completo(id_maestro, url_serie, nombre_serie, "S01", poster)
                        extracted_total += n
                    else:
                        # Ultimo recurso: ID de la serie (raro que funcione aquí pero por si acaso)
                        n = procesar_bloque_completo(id_serie, url_serie, nombre_serie, "S01", poster)
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

print(f"\n✅ FINALIZADO. {total_capitulos} episodios guardados.")
