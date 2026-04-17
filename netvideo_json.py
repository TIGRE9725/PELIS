import requests
import re
import base64
import json
import os
import time

# --- CONFIGURACIÓN ---
COOKIE = "setLenguaje=spa"
SERVIDOR = os.environ.get("URL_SERVIDOR")
ARCHIVO_SALIDA = "netvideo_pelis.json"

# Se movieron y completaron los HEADERS aquí arriba
HEADERS = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": SERVIDOR
}

# Se inicia la sesión y se le inyectan los headers correctamente
session = requests.Session()
session.headers.update(HEADERS)

# --- FUNCIÓN DE REINTENTOS ---
def request_con_reintentos(url, headers, timeout=10, max_intentos=3):
    for i in range(max_intentos):
        try:
            r = session.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200: return r
            if r.status_code == 404: return None 
        except requests.RequestException: pass
        if i < max_intentos - 1: time.sleep(2)
    return None

# --- DEFINICIÓN DE CATEGORÍAS ORIGINALES ---
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

for i in range(1, 51):
    CATEGORIAS.append({"url": f"/?movies&page={i}", "grupo": "PELISN-MOVIES"})

def generar_pelis_json():
    print("--- GENERADOR NETVIDEO PELÍCULAS JSON (FORMATO OTV) ---")
    if not SERVIDOR:
        print("❌ Error: URL_SERVIDOR no definida")
        return

    ids_procesados = set()
    lista_final = []

    for idx, cat in enumerate(CATEGORIAS, 1):
        nombre_grupo = cat["grupo"]
        url_rel = cat["url"].replace("..", "")
        if not url_rel.startswith("/"): url_rel = "/" + url_rel
        url_final = SERVIDOR + url_rel
        if "8532/" not in url_final: url_final = url_final.replace("8532", "8532/")
        
        print(f"[{idx}/{len(CATEGORIAS)}] Analizando: {nombre_grupo}")
        
        r = request_con_reintentos(url_final, HEADERS, timeout=15)
        if not r: continue

        ids = re.findall(r'\?item=([0-9]+)&movie', r.text)
        
        for id_peli in ids:
            if id_peli not in ids_procesados:
                ids_procesados.add(id_peli)
                
                url_item = f"{SERVIDOR}/?item={id_peli}&movie"
                poster = ""
                link_video = ""
                sinopsis = "Sin descripción disponible." # Por defecto
                
                try:
                    # Entramos a la página de la película
                    r_item = request_con_reintentos(url_item, HEADERS, timeout=8)
                    if r_item:
                        # 1. Extraer Poster
                        match_poster = re.search(r'src="(\.\./poster/[^"]+)"', r_item.text)
                        if match_poster:
                            poster = SERVIDOR + match_poster.group(1).replace("..", "")
                        
                        # 2. EXTRAER SINOPSIS
                        match_desc = re.search(r'<div[^>]*class="[^"]*w3-descripcion[^"]*"[^>]*>(.*?)</div>', r_item.text, re.DOTALL | re.IGNORECASE)
                        if match_desc:
                            sinopsis = re.sub(r'<[^<]+?>', '', match_desc.group(1)).strip()
                        
                        # 3. Extraer Video
                        url_watch = f"{SERVIDOR}/?watch={id_peli}&movie"
                        headers_watch = HEADERS.copy()
                        headers_watch["Referer"] = url_item
                        r_watch = request_con_reintentos(url_watch, headers_watch, timeout=8)
                        
                        if r_watch:
                            match_json = re.search(r'(?s)var\s+movie\s*=\s*(\[.*?\]);', r_watch.text)
                            if match_json:
                                data = json.loads(match_json.group(1))
                                seleccion = next((x for x in data if "Lat" in x.get("name", "")), None)
                                if not seleccion and data: seleccion = data[0]
                                
                                if seleccion:
                                    b64 = seleccion["stream"].replace('\\/', '/')
                                    link_video = base64.b64decode(b64).decode('utf-8').replace("\\/", "/")
                except: pass

                if link_video and link_video.startswith("http"):
                    titulo = f"Pelicula {id_peli}"
                    try:
                        nombre_archivo = link_video.split('?')[0].split('/')[-1]
                        nombre_archivo = requests.utils.unquote(nombre_archivo)
                        match_nombre = re.match(r'^(.*?)\.(\d{4})', nombre_archivo)
                        if match_nombre:
                            titulo = f"{match_nombre.group(1).replace('.', ' ')} ({match_nombre.group(2)})"
                        else:
                            titulo = re.sub(r'(?i)(\.720p?|\.1080p?|\.480p?|\.lat|\.spa|\.eng|\.sub|\.mp4|\.mkv|\.avi).*$', '', nombre_archivo).replace('.', ' ')
                        titulo = titulo.title()
                    except: pass
                    
                    # MODIFICACIÓN: Estructura compatible con OTT Navigator y TIGRE+ V2
                    lista_final.append({
                        "name": titulo.strip(),
                        "category": nombre_grupo,
                        "info": {
                            "poster": poster,
                            "plot": sinopsis
                        },
                        "video": link_video
                    })
                    print("+", end="", flush=True)
        print("") 

    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
        json.dump(lista_final, f, indent=4, ensure_ascii=False)
    print(f"\n✅ Guardado {len(lista_final)} peliculas en {ARCHIVO_SALIDA} (Formato OTV)")

if __name__ == "__main__":
    generar_pelis_json()