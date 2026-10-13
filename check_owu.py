import os
import json
import hashlib
import requests
from io import BytesIO
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CONFIG_FILE = "config.json"
HASHES_FILE = "hashes.json"
TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"

def get_drive_service():
    creds = None
    env_token = os.environ.get("GDRIVE_TOKEN_JSON")
    if env_token:
        creds = Credentials.from_authorized_user_info(json.loads(env_token), SCOPES)
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET_FILE):
                raise FileNotFoundError(f"Brak pliku {CLIENT_SECRET_FILE}. Umieść go w głównym katalogu.")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)

def upload_to_drive(service, file_bytes, filename, folder_id):
    media = MediaIoBaseUpload(BytesIO(file_bytes), mimetype="application/pdf", resumable=True)
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id)").execute()
    items = results.get("files", [])

    if items:
        file_id = items[0]["id"]
        service.files().update(fileId=file_id, media_body=media).execute()
        print(f"Zaktualizowano plik: {filename}")
    else:
        metadata = {"name": filename, "parents": [folder_id]}
        service.files().create(body=metadata, media_body=media, fields="id").execute()
        print(f"Pobrano i wgrano nowy plik: {filename}")

def main():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    known_hashes = {}
    if os.path.exists(HASHES_FILE):
        with open(HASHES_FILE, "r", encoding="utf-8") as f:
            try:
                known_hashes = json.load(f)
            except json.JSONDecodeError:
                known_hashes = {}

    service = get_drive_service()
    has_changes = False

    for item in config:
        key = f"{item['company']}_{item['product']}"
        url = item["url"]
        print(f"Sprawdzam: {key}...")

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()

            current_hash = hashlib.sha256(resp.content).hexdigest()

            if known_hashes.get(key) != current_hash:
                print(f"-> Wykryto zmianę dla: {key}")
                known_hashes[key] = current_hash
                upload_to_drive(service, resp.content, item["filename"], item["drive_folder_id"])
                has_changes = True
            else:
                print(f"Brak zmian dla: {key}")

        except Exception as e:
            print(f"Błąd przy pobieraniu {key}: {e}")

    if has_changes:
        with open(HASHES_FILE, "w", encoding="utf-8") as f:
            json.dump(known_hashes, f, indent=2)
        print("Zaktualizowano bazę sum kontrolnych hashes.json.")

if __name__ == '__main__':
    main()
