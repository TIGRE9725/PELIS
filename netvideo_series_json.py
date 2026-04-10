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
ARCHIVO_SALIDA = "netvideo_series.json"

HEADERS = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": SERVIDOR
}

print("--- NETVIDEO SERIES JSON V2 (OTV COMPATIBLE - FULL SCAN) ---")

session = requests.Session()
session.headers.update(HEADERS)

# =======================================================
# LÓGICAS DE LIMPIEZA Y FILTRADO
# =======================================================
def limpiar_texto_html(texto):
    if not texto: return ""
    txt = texto.replace("&amp;", "&").replace("&#038;", "&").replace("&quot;", '"')
    return txt.strip()

def limpiar_nombre_grupo(nombre_sucio):
    if not nombre_sucio: return "Series Varias"
    nombre = urllib.parse.unquote(nombre_sucio)
    nombre = nombre.replace('_', ' ').replace('-', ' ').replace('.', ' ')
    nombre = re.sub(r'\bS\d+\s*E\d+\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\b\d+x\d+\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\s+\d+\s+\d+$', '', nombre) 
    nombre = re.sub(r'\b(480|720|1080)[p]?\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\s+', ' ', nombre).strip()
    return nombre if len(nombre) >= 2 else nombre_sucio

def extraer_nombre_del_archivo(url):
    try:
        url_limpia = url.split('?')[0]
        nombre = url_limpia.split('/')[-1]
        nombre = re.sub(r'\.(mp4|mkv|avi|ts)$', '', nombre, flags=re.IGNORECASE)
        partes = re.split(r'[\._\s-](S\d+|SEASON|TEMPORADA|CAPITULO|E\d+|rev\.)', nombre, flags=re.IGNORECASE)
        nombre_limpio = partes[0].replace('.', ' ').replace('_', ' ')
        return nombre_limpio.strip().title() if len(nombre_limpio) >= 2 else None
    except: return None

def es_lista_de_generos(texto):
    if not texto: return False
    keywords = ['acción', 'aventura', 'drama', 'comedia', 'animación', 'sci-fi', 'fantasía', 'terror', 'suspenso', 'romance']
    matches = sum(1 for k in keywords if k in texto.lower())
    return matches >= 1 and ("," in texto or "&" in texto) or matches >= 2

def verificar_url_existe(url):
    if not url: return False
    try:
        return session.head(url, timeout=2, allow_redirects=True).status_code == 200
    except: return False

# =======================================================
# ANÁLISIS Y EXTRACCIÓN
# =======================================================
def analizar_html_serie(html, id_serie):
    nombre_final = f"Serie {id_serie}"
    poster_final = ""
    sinopsis_final = "Sin descripción disponible."

    # Nombre Latino
    match_bloque = re.search(r'<h2[^>]*>(.*?)</h2>\s*<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if match_bloque:
        h2, p = limpiar_texto_html(match_bloque.group(1)), limpiar_texto_html(match_bloque.group(2))
        nombre_final = h2 if es_lista_de_generos(p) else p
    else:
        match_h2 = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)
        if match_h2: nombre_final = limpiar_texto_html(match_h2.group(1))

    # Sinopsis
    match_desc = re.search(r'<div[^>]*class="[^"]*w3-descripcion[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
    if match_desc: sinopsis_final = re.sub(r'<[^<]+?>', '', match_desc.group(1)).strip()

    # Poster Vertical Hack (V18)
    match_bg = re.search(r'background-image:\s*url\(([^)]+)\)', html, re.IGNORECASE)
    if match_bg:
        bg_url = match_bg.group(1).replace('"', '').replace("'", "").strip()
        if not bg_url.startswith("http"): bg_url = SERVIDOR + bg_url.replace("..", "")
        poster_hack = re.sub(r'p(\.(jpg|png|jpeg))$', r'i\1', bg_url.replace('/original/', '/w410/'), flags=re.IGNORECASE)
        poster_final = poster_hack if verificar_url_existe(poster_hack) else bg_url
    return nombre_final, poster_final, sinopsis_final

def armar_episodios_otv(data_json, nombre_web, num_temporada, diccionario_posters, poster_serie):
    episodios = []
    grupo_general = limpiar_nombre_grupo(nombre_web)
    try: data_json.sort(key=lambda x: int(x.get('number', 0)))
    except: pass

    for ep in data_json:
        try:
            num_ep = int(ep.get('number', 0))
            id_ep_str = str(ep.get('id', ''))
            b64 = ep.get('mp4_spa') or ep.get('mp4_sub') or ep.get('stream') or ep.get('hls_spa')
            if b64:
                url_video = base64.b64decode(b64.replace('\\/', '/')).decode('utf-8').replace("\\/", "/").strip()
                if not url_video.startswith("http"): url_video = SERVIDOR + url_video
                
                nombre_archivo = extraer_nombre_del_archivo(url_video)
                nombre_base = nombre_archivo if nombre_archivo else grupo_general
                titulo_final = f"{nombre_base} S{num_temporada:02d}E{num_ep:02d}"

                episodios.append({
                    "episode": num_ep,
                    "name": titulo_final,
                    "info": { "poster": diccionario_posters.get(id_ep_str, poster_serie) },
                    "video": url_video
                })
        except: pass
    return episodios

# ==========================================
# MOTOR PRINCIPAL
# ==========================================
if __name__ == "__main__":
    if not SERVIDOR: exit("Falta URL_SERVIDOR")
    
    series_visitadas = set()
    catalogo_series = []
    total_capitulos = 0

    for i in range(0, 60):
        url_pagina = f"{SERVIDOR}/?series" + (f"&page={i}" if i > 0 else "")
        print(f"\n📄 Página: {url_pagina}")
        try:
            r = session.get(url_pagina, timeout=10)
            ids_series = list(set(re.findall(r'[?&]item=([0-9]+)&serie', r.text)))
            
            for id_serie in ids_series:
                if id_serie in series_visitadas: continue
                series_visitadas.add(id_serie)
                
                r_serie = session.get(f"{SERVIDOR}/?item={id_serie}&serie", timeout=10)
                nombre_web, poster, sinopsis = analizar_html_serie(r_serie.text, id_serie)
                print(f"  📺 {nombre_web}...", end="", flush=True)

                temporadas_finales = []
                ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', r_serie.text)))

                if ids_temporadas:
                    ids_temporadas.sort()
                    for id_temp in ids_temporadas:
                        r_temp = session.get(f"{SERVIDOR}/?item={id_temp}&season", timeout=10)
                        num_t = int(re.search(r'(?:Temporada|Season)\s+(\d+)', r_temp.text, re.I).group(1)) if re.search(r'(?:Temporada|Season)\s+(\d+)', r_temp.text, re.I) else (ids_temporadas.index(id_temp) + 1)
                        
                        dic_posters = {id_e: (SERVIDOR + p.replace("..", "")) if not p.startswith("http") else p for id_e, p in re.findall(r"appClick\('(\d+)'[^>]*>.*?<img src=\"([^\"]+)\"", r_temp.text, re.S|re.I)}
                        
                        m_cap = re.search(r"appClick\('(\d+)'", r_temp.text)
                        if m_cap:
                            r_w = session.get(f"{SERVIDOR}/?watch={m_cap.group(1)}&episode", headers={"Referer": f"{SERVIDOR}/?item={id_temp}&season"}, timeout=12)
                            m_json = re.search(r'var\s+(?:serie|videos|movie)\s*=\s*(\[.*?\]);', r_w.text, re.S)
                            if m_json:
                                eps = armar_episodios_otv(json.loads(m_json.group(1)), nombre_web, num_t, dic_posters, poster)
                                if eps: temporadas_finales.append({"season": num_t, "episodes": eps})

                else:
                    m_maestro = re.search(r"location\.href\s*=\s*['\"]\.\./\?watch=(\d+)", r_serie.text) or re.search(r"appClick\(['\"](\d+)['\"]", r_serie.text)
                    id_a = m_maestro.group(1) if m_maestro else id_serie
                    r_w = session.get(f"{SERVIDOR}/?watch={id_a}&episode", headers={"Referer": f"{SERVIDOR}/?item={id_serie}&serie"}, timeout=12)
                    m_json = re.search(r'var\s+(?:serie|videos|movie)\s*=\s*(\[.*?\]);', r_w.text, re.S)
                    if m_json:
                        eps = armar_episodios_otv(json.loads(m_json.group(1)), nombre_web, 1, {}, poster)
                        if eps: temporadas_finales.append({"season": 1, "episodes": eps})

                if temporadas_finales:
                    catalogo_series.append({
                        "name": nombre_web,
                        "category": "NET-Series",
                        "info": { "poster": poster, "plot": sinopsis },
                        "seasons": temporadas_finales
                    })
                    caps = sum(len(t["episodes"]) for t in temporadas_finales)
                    total_capitulos += caps
                    print(f" OK ({caps} caps)")

        except Exception as e: print(f" Error: {e}")

    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
        json.dump(catalogo_series, f, indent=4, ensure_ascii=False)
    print(f"\n✅ Finalizado: {len(catalogo_series)} series y {total_capitulos} episodios en {ARCHIVO_SALIDA}")