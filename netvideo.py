import requests
import re
import base64
import json
import os
import time  # Necesario para las pausas entre reintentos

# --- CONFIGURACIÓN ---
COOKIE = "setLenguaje=spa"
SERVIDOR = os.environ.get("URL_SERVIDOR")
ARCHIVO_SALIDA = "netvideo.pelis.m3u"

# --- FUNCIÓN DE REINTENTOS ---
def request_con_reintentos(url, headers, timeout=10, max_intentos=3):
    """
    Intenta descargar una URL varias veces. 
    Si falla, espera un poco y reintenta.
    """
    for i in range(max_intentos):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            # Si el servidor responde pero con error (ej. 500 o 404), intentamos de nuevo si no es 404
            if r.status_code == 404:
                return None 
        except requests.RequestException:
            # Si hay error de conexión (timeout, dns, etc)
            pass
        
        # Si llegamos aquí es que falló. Si no es el último intento, esperamos.
        if i < max_intentos - 1:
            time.sleep(2) # Espera 2 segundos antes de reintentar
            
    return None # Si fallaron todos los intentos

# --- DEFINICIÓN DE CATEGORÍAS ---
CATEGORIAS = [
    {"url": "/?kids", "grupo": "PELISN-KIDS"},
    {"url": "/?movies&genres=Animaci", "grupo": "PELISN-ANIMACION"},
    {"url": "/?movies&genres=Acci", "grupo": "PELISN-ACCION"},
    {"url": "/?movies&genres=Aventur", "grupo": "PELISN-AVENTURA"},
    {"url": "/?movies&genres=Comedi", "grupo": "PELISN-COMEDIA"},
    {"url": "/?movies&genres=Drama", "grupo": "PELISN-DRAMA"},
    {"url": "/?movies&genres=Suspens", "grupo": "PELISN-SUSPENSO"},
    {"url": "/?movies&genres=Terror", "grupo": "PELISN-TERROR"}
]

# Agregamos las 50 paginas extras
for i in range(1, 51):
    CATEGORIAS.append({"url": f"/?movies&page={i}", "grupo": "PELISN-MOVIES"})

HEADERS = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0"
}

print("--- GENERADOR NETVIDEO (CON REINTENTOS) ---")

ids_procesados = set()
contenido_m3u = ["#EXTM3U"]
total_pelis = 0

for idx, cat in enumerate(CATEGORIAS, 1):
    nombre_grupo = cat["grupo"]
    
    raw_url = cat.get("url") or cat.get("Url")
    
    url_rel = raw_url.replace("..", "")
    if not url_rel.startswith("/"): url_rel = "/" + url_rel
    url_final = SERVIDOR + url_rel
    
    if "8532/" not in url_final: url_final = url_final.replace("8532", "8532/")
    
    print(f"[{idx}/{len(CATEGORIAS)}] Analizando: {nombre_grupo}")
    
    # 1. SOLICITUD DE CATEGORÍA CON REINTENTOS
    # Usamos timeout 15 porque listar categorías puede ser lento
    r = request_con_reintentos(url_final, HEADERS, timeout=15)
    
    if not r:
        print(f"   Original: Salteando categoria {nombre_grupo} por error de red.")
        continue

    html = r.text
    ids = re.findall(r'\?item=([0-9]+)&movie', html)
    
    for id_peli in ids:
        if id_peli not in ids_procesados:
            ids_procesados.add(id_peli)
            
            # Obtener datos
            url_item = f"{SERVIDOR}/?item={id_peli}&movie"
            poster = ""
            link_video = ""
            
            try:
                # 2. SOLICITUD DE INFO (POSTER) CON REINTENTOS
                r_item = request_con_reintentos(url_item, HEADERS, timeout=8)
                
                if r_item:
                    match_poster = re.search(r'src="(\.\./poster/[^"]+)"', r_item.text)
                    if match_poster:
                        poster = SERVIDOR + match_poster.group(1).replace("..", "")
                    
                    # 3. SOLICITUD DE VIDEO CON REINTENTOS
                    url_watch = f"{SERVIDOR}/?watch={id_peli}&movie"
                    headers_watch = HEADERS.copy()
                    headers_watch["Referer"] = url_item
                    
                    r_watch = request_con_reintentos(url_watch, headers_watch, timeout=8)
                    
                    if r_watch:
                        # Buscar JSON en JS
                        match_json = re.search(r'(?s)var\s+movie\s*=\s*(\[.*?\]);', r_watch.text)
                        if match_json:
                            data = json.loads(match_json.group(1))
                            # Buscar Latino
                            seleccion = next((x for x in data if "Lat" in x.get("name", "")), None)
                            if not seleccion and data: seleccion = data[0]
                            
                            if seleccion:
                                # Decodificar Base64
                                b64 = seleccion["stream"].replace('\\/', '/')
                                link_video = base64.b64decode(b64).decode('utf-8').replace("\\/", "/")
            except Exception as e:
                # Si algo falla dentro del proceso de regex o json, seguimos
                pass

            if link_video and link_video.startswith("http"):
                # Lógica de titulos
                titulo = f"Pelicula {id_peli}"
                try:
                    nombre_archivo = link_video.split('?')[0].split('/')[-1]
                    # Fix para caracteres URL encoded en el nombre del archivo
                    nombre_archivo = requests.utils.unquote(nombre_archivo)
                    
                    match_nombre = re.match(r'^(.*?)\.(\d{4})', nombre_archivo)
                    if match_nombre:
                        titulo = f"{match_nombre.group(1).replace('.', ' ')} ({match_nombre.group(2)})"
                    else:
                         titulo = re.sub(r'(?i)(\.720p?|\.1080p?|\.480p?|\.lat|\.spa|\.eng|\.sub|\.mp4|\.mkv|\.avi).*$', '', nombre_archivo).replace('.', ' ')
                    titulo = titulo.title()
                except: pass
                
                linea = f'#EXTINF:-1 tvg-id="avi" tvg-logo="{poster}" group-title="{nombre_grupo}",{titulo}\n{link_video}'
                contenido_m3u.append(linea)
                total_pelis += 1
                print("+", end="", flush=True)

# Guardado seguro UTF-8
with open(ARCHIVO_SALIDA, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(contenido_m3u))

print(f"\nGuardado {total_pelis} peliculas en {ARCHIVO_SALIDA}")
