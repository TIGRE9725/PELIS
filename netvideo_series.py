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

print("--- NETVIDEO SERIES V10 (TOKENS & CLEAN GROUPS) ---")
print(f"Servidor: {SERVIDOR}")

contenido_m3u = ["#EXTM3U"]
total_capitulos = 0
series_visitadas = set()

session = requests.Session()
session.headers.update(HEADERS)

def limpiar_texto_html(texto):
    if not texto: return ""
    return texto.replace("&amp;", "&").replace("&#038;", "&").strip()

def extraer_nombre_del_archivo(url):
    """
    Limpia el nombre del archivo ignorando el token.
    Ej: .../The.Witcher.S01E01.mp4?token=XYZ -> The Witcher
    """
    try:
        # 1. Quitamos el token y parámetros (?...) para analizar el nombre
        url_limpia = url.split('?')[0]
        
        # 2. Obtener solo el nombre del archivo
        nombre = url_limpia.split('/')[-1]
        
        # 3. Quitar extensión (.mp4, .mkv, etc)
        nombre = re.sub(r'\.(mp4|mkv|avi|ts)$', '', nombre, flags=re.IGNORECASE)
        
        # 4. Cortar antes de la temporada (S01, S1, TEMPORADA)
        # Busca patrones como .S01, _S01,  S01, .TEMPORADA, .rev, etc.
        patron_corte = r'[\._\s-](S\d+|SEASON|TEMPORADA|CAPITULO|E\d+|rev\.)'
        partes = re.split(patron_corte, nombre, flags=re.IGNORECASE)
        
        nombre_limpio = partes[0]
        
        # 5. Reemplazar puntos y guiones bajos por espacios
        nombre_limpio = nombre_limpio.replace('.', ' ').replace('_', ' ')
        
        # 6. Validación final
        if len(nombre_limpio) < 2: return None
        
        return nombre_limpio.strip().title()
    except:
        return None

def obtener_nombre_web(html, id_serie):
    """Saca el nombre del HTML como respaldo"""
    # Intento 1: Title
    match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
    if match:
        titulo = match.group(1).replace(" - Series", "").strip()
        if titulo and "Watch" not in titulo: return limpiar_texto_html(titulo)
    
    # Intento 2: H2
    match = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)
    if match: return limpiar_texto_html(match.group(1))

    return f"Serie {id_serie}"

def decodificar_json(data_json, nombre_web, nombre_temp_label, poster):
    global total_capitulos
    caps_count = 0
    
    try:
        data_json.sort(key=lambda x: int(x.get('number', 0)))
    except: pass

    for ep in data_json:
        try:
            num_ep = ep.get('number', 0)
            
            # Buscar enlace con prioridad
            b64 = ep.get('mp4_spa') or ep.get('mp4_sub') or ep.get('stream') or ep.get('hls_spa')
            
            if b64:
                # Decodificar Base64
                b64 = b64.replace('\\/', '/')
                link = base64.b64decode(b64).decode('utf-8').replace("\\/", "/").strip()
                
                if not link.startswith("http"): link = SERVIDOR + link
                
                # --- LÓGICA DE NOMBRE ---
                nombre_archivo = extraer_nombre_del_archivo(link)
                
                # Preferimos el nombre del archivo si se pudo limpiar, sino el de la web
                nombre_final_serie = nombre_archivo if nombre_archivo else nombre_web

                # Formato final: "Wonderful World S01E01"
                ep_str = f"E{int(num_ep):02d}"
                titulo_cap = f"{nombre_final_serie} {nombre_temp_label}{ep_str}"
                
                # --- GRUPO LIMPIO (SIN "SERIES -") ---
                grupo = nombre_final_serie
                
                # Guardar en M3U (El link lleva el token completo si lo tenía)
                entry = f'#EXTINF:-1 tvg-id="" tvg-logo="{poster}" group-title="{grupo}",{titulo_cap}\n{link}'
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
                
                nombre_web = obtener_nombre_web(html_serie, id_serie)
                
                match_poster = re.search(r'src="(\.\./poster/[^"]+)"', html_serie)
                poster = SERVIDOR + match_poster.group(1).replace("..", "") if match_poster else ""

                print(f"  📺 {nombre_web}...", end="", flush=True)

                ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', html_serie)))
                extracted_total = 0

                if ids_temporadas:
                    ids_temporadas.sort()
                    for id_temp in ids_temporadas:
                        url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                        r_temp = session.get(url_temp, timeout=10)
                        
                        nombre_temp_label = "Sxx"
                        match_temp_name = re.search(r'(?:Temporada|Season)\s+(\d+)', r_temp.text, re.IGNORECASE)
                        if match_temp_name:
                            nombre_temp_label = f"S{int(match_temp_name.group(1)):02d}"
                        
                        # ID Temporada -> Watch
                        n = procesar_bloque_completo(id_temp, url_temp, nombre_web, nombre_temp_label, poster)
                        extracted_total += n
                else:
                    # CASO DIRECTO: Buscar ID oculto o botones
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
                        # Fallback al ID de la serie
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

print(f"\n✅ FINALIZADO. {total_capitulos} episodios guardados.")
