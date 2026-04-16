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

# Keywords para identificar géneros y consolidar categorías
KEYWORDS_GENEROS = [
    'acción', 'accion', 'aventura', 'adventura', 'drama', 'comedia', 
    'animación', 'animacion', 'sci-fi', 'fantasía', 'fantasia', 'terror', 
    'suspens', 'romance', 'crimen', 'documental', 'western', 'familia', 'kids'
]

print("--- NETVIDEO SERIES JSON V10 (PÓSTERS EXACTOS, TILDES Y GÉNEROS FIX) ---")

session = requests.Session()
session.headers.update(HEADERS)

# ==========================================
# FUNCIONES DE LIMPIEZA Y EXTRACCIÓN
# ==========================================

def verificar_url_existe(url):
    """Verifica si la imagen vertical existe sin descargarla toda"""
    if not url: return False
    try:
        r = session.head(url, timeout=2, allow_redirects=True)
        return r.status_code == 200
    except:
        return False

def extraer_metadatos_inteligentes(html):
    """Extrae Nombre respetando tildes y asigna una sola Categoría Estricta"""
    nombre_final = ""
    categoria_final = "NET-Series"
    
    # 1. TÍTULO LIMPIO (Sin destruir tildes)
    match_h2 = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)
    if match_h2:
        nombre_final = match_h2.group(1).strip()

    # 2. CATEGORÍA (Buscamos los párrafos y evitamos el que sea idéntico al título)
    texto_gen = ""
    bloques_p = re.findall(r'<p>([^<]+)</p>', html, re.IGNORECASE)
    
    for p in bloques_p:
        p_limpio = p.strip()
        if p_limpio.lower() != nombre_final.lower():
            if any(k in p_limpio.lower() for k in KEYWORDS_GENEROS):
                texto_gen = p_limpio
                break

    if not texto_gen and bloques_p:
        for p in bloques_p:
            if p.strip().lower() != nombre_final.lower():
                texto_gen = p.strip()
                break

    if texto_gen:
        texto_lower = texto_gen.lower()
        if 'acci' in texto_lower: categoria_final = "NET-Accion"
        elif 'animaci' in texto_lower or 'kids' in texto_lower: categoria_final = "NET-Animacion"
        elif 'comedi' in texto_lower: categoria_final = "NET-Comedia"
        elif 'drama' in texto_lower: categoria_final = "NET-Drama"
        elif 'terror' in texto_lower: categoria_final = "NET-Terror"
        elif 'suspens' in texto_lower: categoria_final = "NET-Suspenso"
        elif 'aventur' in texto_lower: categoria_final = "NET-Aventura"
        elif 'fantas' in texto_lower or 'sci-fi' in texto_lower: categoria_final = "NET-Fantasia"
        elif 'romance' in texto_lower: categoria_final = "NET-Romance"
        elif 'crimen' in texto_lower: categoria_final = "NET-Crimen"
        else:
            primera = re.split(r'[,&\s]', texto_gen)[0].strip()
            categoria_final = f"NET-{primera.title()}"

    return nombre_final, categoria_final

def extraer_nombre_archivo(url, fallback_name, s_num, e_num):
    """Limpia la URL del MP4 para sacar el nombre bonito del capítulo"""
    try:
        nombre = url.split('?')[0].split('/')[-1]
        nombre = urllib.parse.unquote(nombre)
        nombre = re.sub(r'\.(mp4|mkv|avi|ts)$', '', nombre, flags=re.IGNORECASE)
        partes = re.split(r'[\._\s-](S\d+|SEASON|TEMPORADA|CAPITULO|E\d+|rev\.|spa|sub)', nombre, flags=re.IGNORECASE)
        nombre_limpio = partes[0].replace('.', ' ').replace('_', ' ').strip().title()
        if len(nombre_limpio) < 2: return f"{fallback_name} S{s_num:02d}E{e_num:02d}"
        return f"{nombre_limpio} S{s_num:02d}E{e_num:02d}"
    except:
        return f"{fallback_name} S{s_num:02d}E{e_num:02d}"

def extraer_diccionario_visual(html):
    """Lee el HTML para guardar la miniatura y duración de cada capítulo"""
    vis_dict = {}
    bloques = re.findall(r'<a[^>]*class="[^"]*w3-episode[^"]*"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
    for b in bloques:
        ep_match = re.search(r'Episodio\s+(\d+)', b, re.IGNORECASE)
        if ep_match:
            ep_num = int(ep_match.group(1))
            dur_match = re.search(r'>\s*(\d+)\s*min\s*<', b, re.IGNORECASE)
            icon_match = re.search(r'src="([^"]+w200[^"]+)"', b, re.IGNORECASE)
            vis_dict[ep_num] = {
                "duration": int(dur_match.group(1)) if dur_match else 0,
                "icon": SERVIDOR + icon_match.group(1).replace("..", "") if icon_match else ""
            }
    return vis_dict

# ==========================================
# MOTOR PRINCIPAL
# ==========================================

def procesar_temporada(id_watch, url_referer, nombre_serie, s_num, vis_dict, poster_serie):
    """Saca los videos del reproductor y los fusiona con los datos visuales"""
    url_watch = f"{SERVIDOR}/?watch={id_watch}&episode"
    eps_finales = []
    try:
        r = session.get(url_watch, headers={"Referer": url_referer}, timeout=12)
        match_json = re.search(r'var\s+(?:serie|videos|movie)\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
        
        if match_json:
            data = json.loads(match_json.group(1))
            data.sort(key=lambda x: int(x.get('number', 0))) 
            
            for ep in data:
                ep_num = int(ep.get('number', 0))
                b64 = ep.get('mp4_spa') or ep.get('mp4_sub') or ep.get('stream') or ep.get('hls_spa')
                
                if b64:
                    link_crudo = base64.b64decode(b64).decode('utf-8').replace("\\/", "/").strip()
                    
                    # --- REEMPLAZO DE CLOUD ---
                    link_crudo = link_crudo.replace("/cloud_a/", "/cloud_1/").replace("/cloud_b/", "/cloud_2/")
                    
                    if not link_crudo.startswith("http"): link_crudo = SERVIDOR + link_crudo
                    
                    nombre_ep = extraer_nombre_archivo(link_crudo, nombre_serie, s_num, ep_num)
                    
                    datos_html = vis_dict.get(ep_num, {})
                    icon_ep = datos_html.get("icon", poster_serie)
                    dur_ep = datos_html.get("duration", 0)
                    
                    ep_obj = {
                        "episode": ep_num,
                        "name": nombre_ep,
                        "info": {"icon": icon_ep},
                        "video": link_crudo
                    }
                    if dur_ep > 0: ep_obj["info"]["duration"] = dur_ep
                    eps_finales.append(ep_obj)
    except: pass
    return eps_finales

if __name__ == "__main__":
    catalogo_otv = []
    total_series = 0
    total_caps = 0
    series_visitadas = set()

    if not SERVIDOR:
        print("Error: Variable de entorno URL_SERVIDOR no configurada.")
        exit()

    urls_series = [f"{SERVIDOR}/?series"]
    for i in range(1, 60): urls_series.append(f"{SERVIDOR}/?series&page={i}")

    for url_pagina in urls_series:
        print(f"\n📄 Escaneando: {url_pagina}")
        try:
            r = session.get(url_pagina, timeout=10)
            ids_series = list(set(re.findall(r'[?&]item=([0-9]+)&serie', r.text)))
            
            for id_url in ids_series:
                if id_url in series_visitadas: continue
                series_visitadas.add(id_url)
                
                url_serie = f"{SERVIDOR}/?item={id_url}&serie"
                try:
                    r_serie = session.get(url_serie, timeout=10)
                    html = r_serie.text
                    
                    # --- 1. TÍTULO Y CATEGORÍA ---
                    nombre_serie, categoria_serie = extraer_metadatos_inteligentes(html)
                    if not nombre_serie: nombre_serie = f"Serie {id_url}"
                    
                    print(f"  📺 {nombre_serie}...", end="", flush=True)

                    # --- 2. PÓSTER (LÓGICA EXACTA DE RESGUARDO DEL ORIGINAL) ---
                    match_img = re.search(r'background-image:\s*url\(([^)]+)\)', html, re.IGNORECASE)
                    if not match_img: match_img = re.search(r'src="(\.\./poster/[^"]+)"', html)
                    
                    poster_final = ""
                    
                    if match_img:
                        bg_url_raw = match_img.group(1).replace('"', '').replace("'", "").strip()
                        if not bg_url_raw.startswith("http"):
                            bg_url_raw = SERVIDOR + bg_url_raw.replace("..", "")
                            
                        # GUARDAMOS EL ORIGINAL INTACTO (con su p, b, o sin letra)
                        poster_original_exacto = bg_url_raw
                        
                        # Extraemos la base para probar el w410
                        file_img = bg_url_raw.split('/')[-1]
                        id_poster_real_match = re.search(r'^([^/]+?)[A-Za-z]?\.', file_img)
                        
                        if id_poster_real_match:
                            id_poster_real = id_poster_real_match.group(1)
                            # Armamos la prueba con w410 e 'i'
                            poster_prueba_w410 = f"{SERVIDOR}/poster/w410/{id_poster_real}i.jpg"
                            
                            # Verificamos
                            if verificar_url_existe(poster_prueba_w410):
                                poster_final = poster_prueba_w410 # Éxito
                            else:
                                poster_final = poster_original_exacto # Falló, usamos el original intacto
                        else:
                            poster_final = poster_original_exacto
                    else:
                        poster_final = ""

                    # --- 3. GÉNEROS MÚLTIPLES FIX (Evita el título) ---
                    generos_finales = []
                    bloques_p_generos = re.findall(r'<p>([^<]+)</p>', html, re.IGNORECASE)
                    for p_text in bloques_p_generos:
                        if p_text.strip().lower() != nombre_serie.lower():
                            generos_finales = [g.strip().title() for g in p_text.split(',')]
                            break

                    # --- 4. CLASIFICACIÓN (EDAD) ---
                    edad_final = ""
                    match_edad = re.search(r'<div class="w3-tag[^>]*>([^<]+)</div>', html, re.IGNORECASE)
                    if match_edad:
                        edad_final = match_edad.group(1).strip()

                    # --- 5. SINOPSIS (PLOT LIMPIO) ---
                    plot_final = ""
                    bloques_desc = re.findall(r'<div[^>]*class="[^"]*w3-text-overview w3-descripcion[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
                    for bloque in bloques_desc:
                        if "Audio disponible" not in bloque and "<h4" not in bloque:
                            plot_final = re.sub(r'<[^>]+>', '', bloque).strip()
                            break

                    serie_obj = {
                        "name": nombre_serie,
                        "category": categoria_serie,
                        "info": { "poster": poster_final },
                        "seasons": []
                    }
                    if plot_final: serie_obj["info"]["plot"] = plot_final
                    if generos_finales: serie_obj["info"]["genres"] = generos_finales
                    if edad_final: serie_obj["info"]["age_rating"] = edad_final

                    # --- 6. EXTRACCIÓN DE TEMPORADAS ---
                    ids_temporadas = list(set(re.findall(r'[?&]item=([0-9]+)&season', html)))
                    caps_serie = 0
                    
                    if ids_temporadas:
                        ids_temporadas.sort()
                        for id_temp in ids_temporadas:
                            url_temp = f"{SERVIDOR}/?item={id_temp}&season"
                            r_temp = session.get(url_temp, timeout=10)
                            html_temp = r_temp.text
                            m_s = re.search(r'(?:Temporada|Season)\s+(\d+)', html_temp, re.IGNORECASE)
                            s_num = int(m_s.group(1)) if m_s else 1
                            vis_dict = extraer_diccionario_visual(html_temp)
                            eps = procesar_temporada(id_temp, url_temp, nombre_serie, s_num, vis_dict, poster_final)
                            if eps:
                                serie_obj["seasons"].append({"season": s_num, "episodes": eps})
                                caps_serie += len(eps)
                    else:
                        vis_dict = extraer_diccionario_visual(html)
                        m_maestro = re.search(r"location\.href\s*=\s*['\"]\.\./\?watch=(\d+)", html) or re.search(r"appClick\(['\"]\(\d+\)['\"]", html)
                        id_a = m_maestro.group(1) if m_maestro else id_url
                        eps = procesar_temporada(id_a, url_serie, nombre_serie, 1, vis_dict, poster_final)
                        if eps:
                            serie_obj["seasons"].append({"season": 1, "episodes": eps})
                            caps_serie += len(eps)

                    if caps_serie > 0:
                        catalogo_otv.append(serie_obj)
                        total_series += 1
                        total_caps += caps_serie
                        print(f" OK ({caps_serie} caps)")
                    else:
                        print(" (0 caps)")

                except Exception as e:
                    print(f" [X] Error: {e}")
                    
        except Exception as e:
            print(f"Error página: {e}")

    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
        json.dump(catalogo_otv, f, indent=4, ensure_ascii=False)
        
    print(f"\n✅ Catálogo JSON generado exitosamente.")
    print(f"📺 Total Series: {total_series} | 🎬 Total Capítulos: {total_caps}")