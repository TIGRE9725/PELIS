import requests
import re
import base64
import json
import os
import urllib.parse

# --- CONFIGURACIÓN ---
COOKIE = "setLenguaje=spa"
SERVIDOR = os.environ.get("URL_SERVIDOR")
ARCHIVO_SALIDA = "netvideo.series.json" # Cambio de extensión

HEADERS = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": SERVIDOR
}

session = requests.Session()
session.headers.update(HEADERS)

# --- LISTA MAESTRA PARA JSON ---
biblioteca_json = []

def analizar_html_serie(html, id_serie):
    # (Mantengo tu lógica V18 de extracción de nombre y poster)
    nombre_final = f"Serie {id_serie}"
    poster_final = ""
    
    match_h2 = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)
    if match_h2: nombre_final = match_h2.group(1).strip()

    match_bg = re.search(r'background-image:\s*url\(([^)]+)\)', html, re.IGNORECASE)
    if match_bg:
        poster_final = match_bg.group(1).replace('"', '').replace("'", "").strip()
        if not poster_final.startswith("http"):
            poster_final = SERVIDOR + poster_final.replace("..", "")
    
    return nombre_final, poster_final

def decodificar_episodios_json(data_json):
    """Convierte el JSON interno del servidor al formato de episodios de OTT Navigator"""
    episodios_procesados = []
    
    for ep in data_json:
        num_ep = ep.get('number', 0)
        # Decodificar el link (tu lógica original)
        b64 = ep.get('mp4_spa') or ep.get('mp4_sub') or ep.get('stream') or ep.get('hls_spa')
        
        if b64:
            try:
                link = base64.b64decode(b64).decode('utf-8').replace("\\/", "/").strip()
                if not link.startswith("http"): link = SERVIDOR + link
                
                episodios_procesados.append({
                    "number": int(num_ep),
                    "title": ep.get('title', f"Episodio {num_ep}"),
                    "url": link,
                    # Si detectas ClearKey en el futuro, se añade aquí
                })
            except: pass
    return episodios_procesados

# ==========================================
# MOTOR DE EXTRACCIÓN MODIFICADO
# ==========================================
if __name__ == "__main__":
    if not SERVIDOR:
        print("Error: Configura URL_SERVIDOR")
    else:
        # Limitamos a la primera página para la prueba
        r = session.get(f"{SERVIDOR}/?series")
        ids_series = list(set(re.findall(r'[?&]item=([0-9]+)&serie', r.text)))[:5] # Top 5 series

        for id_serie in ids_series:
            r_serie = session.get(f"{SERVIDOR}/?item={id_serie}&serie")
            nombre_serie, poster = analizar_html_serie(r_serie.text, id_serie)
            
            # Crear objeto de la serie
            serie_obj = {
                "id": nombre_serie,
                "tipo": "series",
                "poster": poster,
                "seasons": []
            }

            # Buscar temporadas
            ids_temps = list(set(re.findall(r'[?&]item=([0-9]+)&season', r_serie.text)))
            ids_temps.sort()

            for i, id_temp in enumerate(ids_temps, 1):
                url_t = f"{SERVIDOR}/?watch={id_temp}&episode"
                r_t = session.get(url_t)
                match_vids = re.search(r'var\s+(?:serie|videos)\s*=\s*(\[.*?\]);', r_t.text, re.DOTALL)
                
                if match_vids:
                    data_vids = json.loads(match_vids.group(1))
                    serie_obj["seasons"].append({
                        "number": i,
                        "episodes": decodificar_episodios_json(data_vids)
                    })
            
            biblioteca_json.append(serie_obj)
            print(f"✅ Procesada: {nombre_serie}")

        # GUARDAR ARCHIVO FINAL
        with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
            json.dump(biblioteca_json, f, indent=4, ensure_ascii=False)
        
        print(f"\n🚀 Archivo {ARCHIVO_SALIDA} generado con éxito.")