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

print("--- NETVIDEO SERIES V15 (LATIN NAME + TOKENS + VERTICAL POSTER) ---")
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
    """
    Analiza el nombre del archivo SIN token para sacar info del episodio (S01E01).
    NOTA: Esto NO afecta al enlace de reproducción, solo al Título visual.
    """
    try:
        url_limpia = url.split('?')[0] # Quitamos token TEMPORALMENTE para leer
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

def analizar_html_serie(html, id_serie):
    """
    Extrae Nombre Latino (del <p> bajo <h2>) y Poster Vertical (del background hack).
    """
    nombre_final = f"Serie {id_serie}"
    poster_final = ""

    # --- 1. NOMBRE LATINO ---
    # Buscamos: <h2>TITULO JAPONES</h2> seguido (con espacios en medio) de <p>TITULO LATINO</p>
    match_bloque = re.search(r'<h2[^>]*>(.*?)</h2>\s*<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    
    if match_bloque:
        nombre_h2 = limpiar_texto_html(match_bloque.group(1)) # Japonés
        nombre_p = limpiar_texto_html(match_bloque.group(2))  # Latino (Chainsaw Man)
        
        # Validación: Si el <p> tiene comas, son géneros, no título.
        if nombre_p and "," not in nombre_p:
            nombre_final = nombre_p
        else:
            nombre_final = nombre_h2
    else:
        # Fallback normal
        match_h2 = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)
        if match_h2: nombre_final = limpiar_texto_html(match_h2.group(1))

    # --- 2. POSTER HACK (p -> i) ---
    # Buscamos el background-image del banner
    match_bg = re.search(r'background-image:\s*url\(([^)]+)\)', html, re.IGNORECASE)
    
    if match_bg:
        bg_url_raw = match_bg.group(1).replace('"', '').replace("'", "").strip()
        # bg_url_raw es algo como: ../poster/original/1144101676586776p.jpg
        
        # PASO A: Cambiar 'original' por 'w410' (tamaño vertical ideal)
        new_url = bg_url_raw.replace('/original/', '/w410/')
        
        # PASO B: Cambiar la ultima 'p' del nombre por 'i' (indicador vertical)
        # Regex busca: p seguido de .jpg al final
        new_url = re.sub(r'p(\.(jpg|png|jpeg))$', r'i\1', new_url, flags=re.IGNORECASE)
        
        poster_final = SERVIDOR + new_url.replace("..", "")
    else:
        # Fallback: Si no hay banner, buscar cualquier imagen w410
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
                
                # --- AQUÍ ESTÁ LA MAGIA ---
                # 1. LINK CON TOKEN (Lo guardamos para el M3U)
                link_final_m3u = link_sucio 

                # 2. LINK SIN TOKEN (Solo para extraer el nombre S01E01)
                nombre_archivo = extraer_nombre_del_archivo(link_sucio)
                
                # Si el archivo tiene info util (Dom S02E08), úsalo. Si no, usa el nombre de la serie.
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
# MOTOR PRINCIPAL (ROBUSTO - V10 STYLE)
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
                # Buscamos por ID (Método V10) que es el que no falla
                ids_series = list(set(re.findall(r'[?&]item=([0-9]+)&serie', r.text)))
                
                if not ids_series: print("   (Sin series)")
                
                for id_serie in ids_series:
                    if id_serie in series_visitadas: continue
                    series_visitadas.add(id_serie)
                    
                    url_serie = f"{SERVIDOR}/?item={id_serie}&serie"
                    try:
                        r_serie = session.get(url_serie, timeout=10)
                        html_serie = r_serie.text
                        
                        # USAMOS LA LÓGICA V15 (Nombre Latino + Poster Hack)
                        nombre_web, poster = analizar_html_serie(html_serie, id_serie)

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
                                
                                n = procesar_bloque_completo(id_temp, url_temp, nombre_web, nombre_temp_label, poster)
                                extracted_total += n
                        else:
                            # Caso Directo
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

        # Guardar M3U
        with open(ARCHIVO_SALIDA, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(contenido_m3u))
            
        print(f"\n✅ Generado {ARCHIVO_SALIDA} con {total_capitulos} capitulos.")
