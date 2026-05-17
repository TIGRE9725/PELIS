import requests
import json
import os
import sys

# CONFIGURACIÓN
GIST_ID = os.environ.get("GIST_ID_PELIS")
TOKEN = os.environ.get("GH_TOKEN")

if not TOKEN or not GIST_ID:
    print("Error: No se encontró el token de GitHub o el GIST_ID")
    sys.exit(1)

# Los 4 archivos que queremos subir al mismo Gist
archivos = [
    "netvideo.pelis.m3u",
    "netvideo.series.m3u",
    "netvideo_pelis.json",
    "netvideo_series.json"
]

files_payload = {}
print("Preparando archivos para subir al Gist...")

for archivo in archivos:
    # Verificamos que el archivo exista y no esté vacío (más de 1KB)
    if os.path.exists(archivo) and os.path.getsize(archivo) > 1000:
        print(f"Procesando {archivo}...")
        try:
            # Leemos en binario y decodificamos como lo tenías originalmente
            with open(archivo, "rb") as f:
                contenido_bytes = f.read()
                
            contenido = contenido_bytes.decode("utf-8", errors="ignore").replace("\x00", "")
            files_payload[archivo] = {"content": contenido}
            
        except Exception as e:
            print(f"Error leyendo archivo {archivo}: {e}")
    else:
        print(f"Ignorando {archivo} (No existe o está vacío)")

if not files_payload:
    print("No hay archivos válidos para subir.")
    sys.exit(0)

print(f"Subiendo paquete al Gist {GIST_ID}...")

headers = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

data = {
    "files": files_payload
}

r = requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=data)

if r.status_code == 200:
    print("¡EXITO! Gist actualizado correctamente con todos los archivos.")
else:
    print(f"Error al subir: {r.status_code}")
    print(r.text)
    sys.exit(1)