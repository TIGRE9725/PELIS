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

print("--- NETVIDEO SERIES V11 (GROUP FIX) ---")
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
        url_limpia = url.split('?')[0]
        nombre_archivo = url_limpia.split('/')[-1]
        nombre_archivo = urllib.parse.unquote(nombre_archivo)
        
        # Eliminar extensión
        nombre_base = re.sub(r'\.(mp4|mkv|avi)$', '', nombre_archivo, flags=re.IGNORECASE)
        
        # Reemplazar puntos y guiones bajos por espacios
        nombre_limpio = nombre_base.replace('.', ' ').replace('_', ' ').replace('-', ' ')
        
        # Eliminar resoluciones y calidades comunes
        nombre_limpio = re.sub(r'\b(480|720|1080)[p]?\b', '', nombre_limpio, flags=re.IGNORECASE)
        nombre_limpio = re.sub(r'\b(hd|sd|rip|web|bluray)\b', '', nombre_limpio, flags=re.IGNORECASE)
        
        return nombre_limpio.strip()
    except:
        return "Desconocido"

def limpiar_nombre_grupo(nombre_sucio):
    """
    Deja solo el nombre de la serie, eliminando S01E01, 1-01, etc.
    Para que TiviMate agrupe todos los capitulos en una sola carpeta.
    """
    if not nombre_sucio: return "Series Varias"
    
    # Decodificar URL (%20 -> Espacio)
    nombre = urllib.parse.unquote(nombre_sucio)
    
    # Reemplazos básicos
    nombre = nombre.replace('_', ' ').replace('-', ' ').replace('.', ' ')
    
    # 1. Eliminar patrones de episodio: S01E01, 1x01, S1 E1
    nombre = re.sub(r'\bS\d+\s*E\d+\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\b\d+x\d+\b', '', nombre, flags=re.IGNORECASE)
    
    # 2. Eliminar patrones numéricos tipo "The Walking Dead 1 01" o "1-01"
    # Busca numeros al final que parezcan temporada/episodio
    nombre = re.sub(r'\s+\d+\s+\d+$', '', nombre) 
    
    # 3. Eliminar resoluciones y basura común
    nombre = re.sub(r'\b(480|720|1080)[p]?\b', '', nombre, flags=re.IGNORECASE)
    nombre = re.sub(r'\b(latino|castellano|sub|spa|eng)\b', '', nombre, flags=re.IGNORECASE)
    
    # 4. Limpieza final de espacios
    nombre = re.sub(r'\s+', ' ', nombre).strip()
    
    # Si nos pasamos y borramos todo, volver al original
    if len(nombre) < 2: return nombre_sucio
    
    return nombre

def procesar_bloque_completo(id_serie, url_origen, nombre_serie_web, temporada_label, poster_url):
    """Descarga JSON del reproductor y extrae capitulos"""
    global total_capitulos
    capitulos_encontrados = 0
    
    try:
        url_api = f"{SERVIDOR}/reproductor/include/seasons_new.php?id={id_serie}"
        r = session.get(url_api, timeout=10)
        
        if r.status_code == 200:
            data = r.json()
            
            # El nombre de la serie para el GRUPO debe ser limpio
            # Usamos el nombre que viene de la web (título de la página) porque suele ser el mejor
            grupo_serie = limpiar_nombre_grupo(nombre_serie_web)

            for season in data:
                # Si la temporada viene como "Temporada 1", extraemos el 1
                num_season = season.get('season_number', '1')
                if "Temporada" in str(num_season):
                    num_season = re.search(r'\d+', str(num_season))
                    num_season = num_season.group(0) if num_season else '1'
                
                # Formato S01
                s_str = f"S{int(num_season):02d}"

                for episode in season.get('episodes', []):
                    ep_num = episode.get('episode_number', '0')
                    # Formato E01
                    e_str = f"E{int(ep_num):02d}"
                    
                    titulo_ep = episode.get('title', '')
                    video_url = episode.get('link', '')
                    
                    if not video_url or "youtube" in video_url: continue
                    if not video_url.startswith("http"): video_url = SERVIDOR + video_url

                    # Nombre Final: "The Walking Dead S01E01"
                    nombre_display = f"{grupo_serie} {s_str}{e_str}"
                    if titulo_ep: nombre_display += f" {titulo_ep}"
                    
                    # Construcción M3U
                    # group-title debe ser SOLO el nombre de la serie
                    entry = f'#EXTINF:-1 tvg-id="" tvg-logo="{poster_url}" group-title="{grupo_serie}",{nombre_display}\n{video_url}'
                    contenido_m3u.append(entry)
                    
                    capitulos_encontrados += 1
                    total_capitulos += 1
                    
    except Exception as e:
        print(f"Error procesando API serie {id_serie}: {e}")
        
    return capitulos_encontrados

def escanear_series():
    try:
        # Escanear pagina 1 a 20 (ajustable)
        for page in range(1, 25):
            print(f"--- Escaneando Página {page} ---")
            url = f"{SERVIDOR}/series/?page={page}"
            
            try:
                r = session.get(url, timeout=15)
                if r.status_code != 200: break
                
                html = r.text
                bloques = re.findall(r'<a href="([^"]+)"[^>]*class="animation-1">.*?<img src="([^"]+)"[^>]*alt="([^"]+)"', html, re.DOTALL)
                
                if not bloques: 
                    print("No se encontraron series en esta página.")
                    break

                for link, img, titulo in bloques:
                    if not link.startswith("http"): link = SERVIDOR + link
                    if not img.startswith("http"): img = SERVIDOR + img
                    
                    if link in series_visitadas: continue
                    series_visitadas.add(link)
                    
                    nombre_serie = limpiar_texto_html(titulo)
                    
                    # Extraer ID de la serie desde la URL o el HTML
                    # Intentamos entrar a la serie para sacar el ID real
                    try:
                        r_serie = session.get(link, timeout=10)
                        html_serie = r_serie.text
                        
                        # Buscar ID maestro
                        # location.href = '../?watch=1234'
                        match_id = re.search(r"watch=(\d+)", html_serie)
                        if not match_id:
                            match_id = re.search(r"id=(\d+)", html_serie)
                        
                        if match_id:
                            id_serie = match_id.group(1)
                            print(f" Procesando: {nombre_serie} (ID: {id_serie}) ...", end="")
                            
                            n = procesar_bloque_completo(id_serie, link, nombre_serie, "S01", img)
                            
                            if n > 0: print(f" OK ({n} caps)")
                            else: print(" (0 caps)")
                            
                    except:
                        print(f" Error accediendo a serie: {nombre_serie}")
                        
            except Exception as e:
                print(f"Error pagina {page}: {e}")

    except Exception as e:
        print(f"Error general: {e}")

# Ejecutar
if __name__ == "__main__":
    if not SERVIDOR:
        print("Falta configurar la variable de entorno URL_SERVIDOR")
    else:
        escanear_series()
        
        # Guardar M3U
        with open(ARCHIVO_SALIDA, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(contenido_m3u))
            
        print(f"Generado {ARCHIVO_SALIDA} con {total_capitulos} capitulos.")
