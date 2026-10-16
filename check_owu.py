import os
import json
import hashlib
import mimetypes
from datetime import datetime
from io import BytesIO
import requests
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

def get_or_create_archive_folder(service, parent_folder_id, folder_name="Archiwum"):
    query = (
        f"name = '{folder_name}' and "
        f"'{parent_folder_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    items = results.get("files", [])
    if items:
        return items[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id]
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    print(f"Utworzono nowy folder archiwum: '{folder_name}'")
    return folder["id"]

def upload_to_drive(service, file_bytes, filename, folder_id, company="", archive_folder_id=None, archive_folder_name=None):
    folder_id = folder_id.strip().split("?")[0]
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/pdf"

    media = MediaIoBaseUpload(BytesIO(file_bytes), mimetype=mime_type, resumable=True)

    # Sprawdź czy plik o tej nazwie już istnieje w folderze docelowym
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get("files", [])

    if items:
        old_file_id = items[0]["id"]

        # Określ folder archiwum
        target_archive_id = archive_folder_id
        if not target_archive_id:
            target_name = archive_folder_name or (f"Archiwum {company}".strip() if company else "Archiwum")
            target_archive_id = get_or_create_archive_folder(service, folder_id, target_name)

        # Przygotuj nazwę archiwalną z datą
        name_part, ext_part = os.path.splitext(filename)
        date_str = datetime.now().strftime("%Y-%m-%d")
        archived_filename = f"{name_part}_arch_{date_str}{ext_part}"

        # Zapobieganie konfliktom przy wielokrotnej archiwizacji tego samego dnia
        check_q = f"name = '{archived_filename}' and '{target_archive_id}' in parents and trashed = false"
        arch_items = service.files().list(q=check_q, fields="files(id)").execute().get("files", [])
        if arch_items:
            time_str = datetime.now().strftime("%H%M%S")
            archived_filename = f"{name_part}_arch_{date_str}_{time_str}{ext_part}"

        # Przenieś i zmień nazwę starego pliku
        service.files().update(
            fileId=old_file_id,
            addParents=target_archive_id,
            removeParents=folder_id,
            body={"name": archived_filename},
            fields="id, parents, name"
        ).execute()
        print(f"Zarchiwizowano poprzednią wersję jako: '{archived_filename}'")

    # Wgraj nowy plik do głównego folderu
    metadata = {"name": filename, "parents": [folder_id]}
    service.files().create(body=metadata, media_body=media, fields="id").execute()
    print(f"Wgrano nowy plik: {filename}")

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
        company = item.get("company", "")
        archive_folder_id = item.get("archive_folder_id")
        archive_folder_name = item.get("archive_folder_name")

        print(f"Sprawdzam: {key}...")

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()

            current_hash = hashlib.sha256(resp.content).hexdigest()

            if known_hashes.get(key) != current_hash:
                print(f"-> Wykryto zmianę dla: {key}")
                known_hashes[key] = current_hash
                upload_to_drive(
                    service=service,
                    file_bytes=resp.content,
                    filename=item["filename"],
                    folder_id=item["drive_folder_id"],
                    company=company,
                    archive_folder_id=archive_folder_id,
                    archive_folder_name=archive_folder_name
                )
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
