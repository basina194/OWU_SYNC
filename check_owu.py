import os
import re
import json
import hashlib
import mimetypes
from datetime import datetime
from io import BytesIO
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, unquote
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

class PDFLinkExtractor(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.pdf_links = []

    def handle_starttag(self, tag, attrs):
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        for key in ["href", "src", "data-url", "data-href", "data-src"]:
            val = attr_dict.get(key, "").strip()
            if val and ".pdf" in val.lower():
                full_url = urljoin(self.base_url, val)
                if full_url not in self.pdf_links:
                    self.pdf_links.append(full_url)

def extract_pdf_urls_from_html(base_url, html_text):
    parser = PDFLinkExtractor(base_url)
    try:
        parser.feed(html_text)
    except Exception:
        pass

    links = list(parser.pdf_links)

    # Fallback regex, gdyby kod HTML miał niestandardową strukturę
    pattern = r'(?:href|src|data-url|data-href)=[\x22\x27]([^\x22\x27]*?\.pdf(?:\?[^\x22\x27]*)?)[\x22\x27]'
    for match in re.finditer(pattern, html_text, re.IGNORECASE):
        candidate = urljoin(base_url, match.group(1).strip())
        if candidate not in links:
            links.append(candidate)

    return links

def get_pdf_urls_for_target(url, headers, fallback_if_no_pdfs=False):
    # Jeśli URL bezpośrednio wskazuje na plik .pdf
    clean_url = url.split("?")[0].split("#")[0]
    if clean_url.lower().endswith(".pdf"):
        return [url]

    # Pobieramy stronę i sprawdzamy nagłówki
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "").lower()
    if "application/pdf" in content_type:
        return [url]

    # Strona HTML - wyszukujemy linki do dokumentów PDF
    pdf_urls = extract_pdf_urls_from_html(url, resp.text)
    if not pdf_urls and fallback_if_no_pdfs:
        return [url]

    return pdf_urls

def get_filename(url, headers=None):
    if headers:
        cd = headers.get("Content-Disposition", "")
        if cd and "filename=" in cd:
            match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
            if match:
                fn = unquote(match.group(1).strip())
                if fn:
                    return fn

    parsed = urlparse(url)
    basename = unquote(parsed.path.split("/")[-1])
    basename = basename.split("?")[0].strip()
    if not basename:
        basename = "dokument.pdf"
    elif not basename.lower().endswith(".pdf"):
        basename += ".pdf"
    return basename

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

def move_file_to_archive(service, filename, folder_id, company="", archive_folder_id=None, archive_folder_name=None):
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get("files", [])
    if not items:
        return

    old_file_id = items[0]["id"]
    target_archive_id = archive_folder_id
    if not target_archive_id:
        target_name = archive_folder_name or (f"Archiwum {company}".strip() if company else "Archiwum")
        target_archive_id = get_or_create_archive_folder(service, folder_id, target_name)

    name_part, ext_part = os.path.splitext(filename)
    date_str = datetime.now().strftime("%Y-%m-%d")
    archived_filename = f"{name_part}_arch_{date_str}{ext_part}"

    check_q = f"name = '{archived_filename}' and '{target_archive_id}' in parents and trashed = false"
    arch_items = service.files().list(q=check_q, fields="files(id)").execute().get("files", [])
    if arch_items:
        time_str = datetime.now().strftime("%H%M%S")
        archived_filename = f"{name_part}_arch_{date_str}_{time_str}{ext_part}"

    service.files().update(
        fileId=old_file_id,
        addParents=target_archive_id,
        removeParents=folder_id,
        body={"name": archived_filename},
        fields="id, parents, name"
    ).execute()
    print(f"Zarchiwizowano stary plik jako '{archived_filename}' w folderze archiwum.")

def upload_to_drive(service, file_bytes, filename, folder_id, company="", archive_folder_id=None, archive_folder_name=None):
    folder_id = folder_id.strip().split("?")[0]
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/pdf"

    media = MediaIoBaseUpload(BytesIO(file_bytes), mimetype=mime_type, resumable=True)

    # Jeśli plik o tej nazwie już istnieje w folderze głównym -> przenosimy go najpierw do archiwum
    move_file_to_archive(service, filename, folder_id, company, archive_folder_id, archive_folder_name)

    # Wgrywamy nową wersję pliku pod oryginalną nazwą
    metadata = {"name": filename, "parents": [folder_id]}
    service.files().create(body=metadata, media_body=media, fields="id").execute()
    print(f"Pobrano i wgrano plik: {filename}")

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
        company = item.get("company", "")
        product = item.get("product", "")
        product_key = f"{company}_{product}".strip("_")
        page_url = item["url"]
        folder_id = item["drive_folder_id"].strip().split("?")[0]
        archive_folder_id = item.get("archive_folder_id")
        archive_folder_name = item.get("archive_folder_name")

        print(f"\nSprawdzam: {product_key} ({page_url})...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            pdf_urls = get_pdf_urls_for_target(page_url, headers, fallback_if_no_pdfs=bool(item.get("filename")))
            if not pdf_urls:
                print(f"Nie znaleziono żadnych plików PDF pod adresem: {page_url}")
                continue

            print(f"Znaleziono {len(pdf_urls)} plik(ów) PDF.")

            # Poprzednio zapisane sumy dla tego produktu
            prev_product_entry = known_hashes.get(product_key, {})
            if isinstance(prev_product_entry, str):
                prev_hashes = {item.get("filename") or "stary_dokument.pdf": prev_product_entry}
            elif isinstance(prev_product_entry, dict):
                prev_hashes = dict(prev_product_entry)
            else:
                prev_hashes = {}

            current_product_hashes = {}
            current_filenames = set()

            for pdf_url in pdf_urls:
                try:
                    resp = requests.get(pdf_url, headers=headers, timeout=30)
                    resp.raise_for_status()

                    # Nazwa pliku pobierana z URL/nagłówków lub z configu (jeśli jawnie podano dla pojedynczego linku)
                    if len(pdf_urls) == 1 and item.get("filename"):
                        filename = item["filename"]
                    else:
                        filename = get_filename(pdf_url, resp.headers)

                    current_filenames.add(filename)
                    current_hash = hashlib.sha256(resp.content).hexdigest()
                    current_product_hashes[filename] = current_hash

                    if prev_hashes.get(filename) != current_hash:
                        print(f"-> Wykryto zmianę lub nowy plik: {filename}")
                        upload_to_drive(
                            service=service,
                            file_bytes=resp.content,
                            filename=filename,
                            folder_id=folder_id,
                            company=company,
                            archive_folder_id=archive_folder_id,
                            archive_folder_name=archive_folder_name
                        )
                        has_changes = True
                    else:
                        print(f"Brak zmian dla: {filename}")

                except Exception as file_err:
                    print(f"Błąd przy pobieraniu pliku {pdf_url}: {file_err}")

            # Wykrywanie plików, które usunięto / zastąpiono nowymi na stronie
            removed_files = set(prev_hashes.keys()) - current_filenames
            for removed_fn in removed_files:
                print(f"-> Plik {removed_fn} nie występuje już na stronie - przenoszę do archiwum.")
                move_file_to_archive(
                    service=service,
                    filename=removed_fn,
                    folder_id=folder_id,
                    company=company,
                    archive_folder_id=archive_folder_id,
                    archive_folder_name=archive_folder_name
                )
                has_changes = True

            known_hashes[product_key] = current_product_hashes

        except Exception as e:
            print(f"Błąd przy sprawdzaniu {product_key}: {e}")

    if has_changes:
        with open(HASHES_FILE, "w", encoding="utf-8") as f:
            json.dump(known_hashes, f, indent=2)
        print("\nZaktualizowano bazę sum kontrolnych hashes.json.")

if __name__ == '__main__':
    main()
