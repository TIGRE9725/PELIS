import requests
import json
import os
import sys

# CONFIGURACIÓN
GIST_ID = os.environ.get("GIST_ID_PELIS")
TOKEN = os.environ.get("GH_TOKEN")
ARCHIVO = "netvideo.pelis.m3u"

if not TOKEN:
    print("Error: No se encontró el token de GitHub")
    sys.exit(1)

print(f"Leyendo archivo {ARCHIVO}...")

try:
    # Leemos el archivo en modo binario y decodificamos ignorando errores
    with open(ARCHIVO, "rb") as f:
        contenido_bytes = f.read()
        
    # Limpieza final de bytes nulos
    contenido = contenido_bytes.decode("utf-8", errors="ignore").replace("\x00", "")
    
except Exception as e:
    print(f"Error leyendo archivo: {e}")
    sys.exit(1)

print(f"Subiendo a Gist {GIST_ID}...")

headers = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

data = {
    "files": {
        ARCHIVO: {
            "content": contenido
        }
    }
}

r = requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=data)

if r.status_code == 200:
    print("¡EXITO! Gist de Peliculas actualizado correctamente.")
else:
    print(f"Error al subir: {r.status_code}")
    print(r.text)
    sys.exit(1)
