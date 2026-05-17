import os
import sys
import requests
import json

# 1. Extraemos las llaves maestras desde GitHub Secrets
APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")

if not all([APP_KEY, APP_SECRET, REFRESH_TOKEN]):
    print("Error: Faltan credenciales de Dropbox en los Secrets.")
    sys.exit(1)

# Capturamos todos los nombres de archivos que le mandes desde el YAML
archivos_a_subir = sys.argv[1:]

if not archivos_a_subir:
    print("Error: No se especificaron archivos para subir.")
    sys.exit(1)

print("Renovando token de acceso temporal con Dropbox...")
# 2. Intercambiamos el Refresh Token por un Token de Subida nuevo
auth_response = requests.post(
    "https://api.dropbox.com/oauth2/token",
    data={
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN
    },
    auth=(APP_KEY, APP_SECRET)
)

if auth_response.status_code != 200:
    print(f"Error obteniendo token: {auth_response.text}")
    sys.exit(1)

ACCESS_TOKEN = auth_response.json()["access_token"]
print("¡Token obtenido con éxito! Iniciando transferencia a la nube...\n")

# 3. Empujar cada archivo a Dropbox
upload_url = "https://content.dropboxapi.com/2/files/upload"

for archivo in archivos_a_subir:
    # Validamos que el archivo exista y no venga vacío
    if os.path.exists(archivo) and os.path.getsize(archivo) > 1000:
        print(f"Subiendo {archivo}...")
        
        # Ruta en la carpeta secreta de tu App (Ej. /netvideo.pelis.m3u)
        dropbox_path = f"/{archivo}"
        
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Dropbox-API-Arg": json.dumps({
                "path": dropbox_path,
                "mode": "overwrite", # Sobrescribe el viejo automáticamente
                "autorename": False,
                "mute": True, # Evita notificaciones molestas si tienes la app
                "strict_conflict": False
            }),
            "Content-Type": "application/octet-stream"
        }
        
        try:
            with open(archivo, "rb") as f:
                data = f.read()
                
            upload_response = requests.post(upload_url, headers=headers, data=data)
            
            if upload_response.status_code == 200:
                print(f"--> ¡Éxito! {archivo} actualizado en Dropbox.")
            else:
                print(f"--> Error al subir {archivo}: {upload_response.text}")
        except Exception as e:
            print(f"--> Error local leyendo {archivo}: {e}")
    else:
        print(f"Ignorado: {archivo} (No existe o pesa menos de 1KB).")

print("\nSincronización total con Dropbox finalizada.")
