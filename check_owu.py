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

def normalize_text(text):
    text = (text or "").lower()
    mapping = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'
    }
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text

def extract_pdf_items_from_html(base_url, html_text, headers):
    items = []
    seen_urls = set()

    clean_html = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', '', html_text, flags=re.I)

    # Obsługa specyficznego formatu serializacji Generali (devalue serialization)
    if "_~s~" in html_text or "~s~" in html_text:
        clean = re.sub(r'https:[_~s]+www', 'https://www', html_text)
        clean = re.sub(r'[_~]+s[_~]+', '/', clean)
        for m in re.finditer(r'(https://(?:www\.)?generali\.pl/media/[^\x22\x27\s<>]+\.pdf)', clean, re.I):
            u = m.group(1)
            if u not in seen_urls:
                seen_urls.add(u)
                items.append({'url': u, 'text': '', 'context': '', 'is_archive': False})

    # Podział na sekcje wg nagłówków h1-h3 (np. kategorie / akordeony jak w Compensie)
    raw_sections = re.split(r'(<h[1-3][^>]*>.*?</h[1-3]>)', clean_html, flags=re.I)

    parsed_sections = []
    if len(raw_sections) > 1:
        for i in range(1, len(raw_sections), 2):
            h_text = re.sub(r'<[^>]+>', '', raw_sections[i]).strip()
            content = raw_sections[i+1] if i+1 < len(raw_sections) else ''
            parsed_sections.append((h_text, content))
    else:
        parsed_sections.append(("", clean_html))

    for cat_title, section_html in parsed_sections:
        # Wykrycie sekcji archiwum w obrębie danej sekcji / akordeonu
        arch_match = re.search(
            r'<(?:h[3-6]|strong|p|b|div)[^>]*>(?:<[^>]+>|\s)*?[Aa]rchiwum:?[\s\S]*?</(?:h[3-6]|strong|p|b|div)>',
            section_html,
            re.I
        )
        arch_pos = arch_match.start() if arch_match else len(section_html)

        # 1. Klasyczne linki <a> z .pdf
        for m in re.finditer(r'<a[^>]+href=[\x22\x27]([^\x22\x27]*?\.pdf(?:\?[^\x22\x27]*)?)[\x22\x27][^>]*>(.*?)</a>', section_html, re.I | re.S):
            link_url = urljoin(base_url, m.group(1).strip())
            raw_text = re.sub(r'<[^>]+>', ' ', m.group(2)).strip()
            link_text = re.sub(r'\s+', ' ', raw_text)
            link_pos = m.start()

            is_arch = False
            if link_pos >= arch_pos:
                is_arch = True
            elif '/archiwum/' in link_url.lower() or '/archive/' in link_url.lower():
                is_arch = True
            elif re.search(r'(?:obowi[aą]zuj[aącecy]{1,3}\s+do|wa[zż]n[ey]\s+do|\bdo\s+\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{2,4}|archiwaln)', link_text, re.I):
                is_arch = True

            # Czyszczenie dopisków o rozmiarze pliku np. "PDF 409,1 KB" aby cyfry nie zakłócały filtrów
            clean_text = re.sub(r'(?:PDF\s*)?\d+(?:[.,]\d+)?\s*(?:[kKmMgGtT]?[bB]|bajt[oó]w)\b', '', link_text, flags=re.I).strip()

            if link_url not in seen_urls:
                seen_urls.add(link_url)
                items.append({
                    'url': link_url,
                    'text': clean_text,
                    'context': cat_title,
                    'is_archive': is_arch
                })

        # 2. Linki z data-url / data-href lub do repozytoriów plików (np. PZU fileserver)
        fs_pattern = r'<a[^>]+(?:href|src|data-url|data-href)=[\x22\x27]([^\x22\x27]*(?:_fileserver|/files/|/documents/|/pobierz|/download)[^\x22\x27]*)[\x22\x27][^>]*>(.*?)</a>'
        for m in re.finditer(fs_pattern, section_html, re.I | re.S):
            cand_url = urljoin(base_url, m.group(1).strip())
            raw_text = re.sub(r'<[^>]+>', ' ', m.group(2)).strip()
            link_text = re.sub(r'\s+', ' ', raw_text)
            clean_text = re.sub(r'(?:PDF\s*)?\d+(?:[.,]\d+)?\s*(?:[kKmMgGtT]?[bB]|bajt[oó]w)\b', '', link_text, flags=re.I).strip()
            if cand_url not in seen_urls:
                clean = cand_url.split("?")[0].split("#")[0]
                if clean.lower().endswith(".pdf"):
                    seen_urls.add(cand_url)
                    items.append({
                        'url': cand_url,
                        'text': clean_text,
                        'context': cat_title,
                        'is_archive': '/archiwum/' in cand_url.lower() or 'archiwaln' in clean_text.lower()
                    })
                else:
                    try:
                        head = requests.head(cand_url, headers=headers, timeout=10, allow_redirects=True)
                        ct = head.headers.get("Content-Type", "").lower()
                        cd = head.headers.get("Content-Disposition", "").lower()
                        if "application/pdf" in ct or ".pdf" in cd:
                            seen_urls.add(cand_url)
                            items.append({
                                'url': cand_url,
                                'text': clean_text,
                                'context': cat_title,
                                'is_archive': False
                            })
                    except Exception:
                        pass

        # 3. Elementy data-file='pdf' (np. PZU)
        data_pdf_pattern = r'<[^>]+data-file=[\x22\x27]pdf[\x22\x27][^>]*>[\s\S]{0,400}?href=[\x22\x27]([^\x22\x27]+)[\x22\x27]'
        for m in re.finditer(data_pdf_pattern, section_html, re.I):
            cand_url = urljoin(base_url, m.group(1).strip())
            if cand_url not in seen_urls:
                try:
                    head = requests.head(cand_url, headers=headers, timeout=10, allow_redirects=True)
                    ct = head.headers.get("Content-Type", "").lower()
                    cd = head.headers.get("Content-Disposition", "").lower()
                    if "application/pdf" in ct or ".pdf" in cd:
                        seen_urls.add(cand_url)
                        items.append({
                            'url': cand_url,
                            'text': '',
                            'context': cat_title,
                            'is_archive': False
                        })
                except Exception:
                    pass

    return items

def filter_items(items, filter_val=None, exclude_val=None, exclude_archive=False):
    # 1. Filtrowanie archiwów
    active_items = [it for it in items if not (exclude_archive and it.get("is_archive"))]

    # 2. Wykluczenia (exclude)
    if exclude_val:
        if isinstance(exclude_val, str):
            exclude_words = [normalize_text(w) for w in re.split(r'[\s,]+', exclude_val) if w.strip()]
        else:
            exclude_words = [normalize_text(str(w)) for w in exclude_val if str(w).strip()]
        active_items = [
            it for it in active_items
            if not any(w in normalize_text(f"{it.get('context', '')} {it.get('text', '')}") for w in exclude_words)
        ]

    if not filter_val:
        return active_items

    if isinstance(filter_val, list):
        norm_filter = " ".join(normalize_text(str(w)) for w in filter_val if str(w).strip())
        filter_words = [normalize_text(str(w)) for w in filter_val if str(w).strip()]
    else:
        norm_filter = normalize_text(str(filter_val)).strip()
        filter_words = [w for w in re.split(r'[\s,]+', norm_filter) if w]

    # 3. Dopasowanie całej frazy (priorytetowe)
    phrase_pattern = r'\b' + r'[\s\-_/]+'.join(re.escape(w) for w in filter_words) + r'\b'
    phrase_matches = [
        it for it in active_items
        if re.search(phrase_pattern, normalize_text(f"{it.get('context', '')} {it.get('text', '')}"))
    ]
    if phrase_matches:
        return phrase_matches

    # 4. Fallback: dopasowanie wszystkich słów (z granicami słów dla liczb / krótkich kodów)
    word_matches = []
    for it in active_items:
        searchable = normalize_text(f"{it.get('context', '')} {it.get('text', '')}")
        ok = True
        for w in filter_words:
            if w.isdigit() or len(w) <= 2:
                pattern = r'(?<![a-zA-Z0-9])' + re.escape(w) + r'(?![a-zA-Z0-9])'
                if not re.search(pattern, searchable):
                    ok = False
                    break
            else:
                if w not in searchable:
                    ok = False
                    break
        if ok:
            word_matches.append(it)
    return word_matches

def get_pdf_urls_for_target(url, headers, filter_val=None, exclude_val=None, exclude_archive=False, fallback_if_no_pdfs=False, category=None, query=None):
    # Jeśli URL bezpośrednio wskazuje na plik .pdf
    clean_url = url.split("?")[0].split("#")[0]
    if clean_url.lower().endswith(".pdf"):
        return [url]

    session = requests.Session()
    resp = session.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "").lower()
    if "application/pdf" in content_type:
        return [url]

    # Obsługa repozytoriów z formularzem wyszukiwania (np. Ergo Hestia /wyszukiwarka/dokumenty/)
    if 'id="id_search_form"' in resp.text or 'id_query' in resp.text:
        csrf_match = re.search(r'name=[\x22\x27]csrfmiddlewaretoken[\x22\x27]\s+value=[\x22\x27]([^\x22\x27]+)[\x22\x27]', resp.text)
        if csrf_match:
            csrf_token = csrf_match.group(1)
            if query is not None:
                query_to_send = str(query)
            elif filter_val:
                # Oczyszczenie ogólnych prefiksów by wyszukiwarka Hestii celnie wyszukała nazwę produktu
                clean_q = re.sub(r'(?:og[oó]lne\s+warunki\s+(?:ubezpiecze[nń]\s+)?|owu\s+)', '', str(filter_val), flags=re.I).strip()
                query_to_send = clean_q or str(filter_val)
            else:
                query_to_send = ""

            post_data = {
                "csrfmiddlewaretoken": csrf_token,
                "query": query_to_send,
                "category": category or ""
            }
            post_headers = dict(headers)
            post_headers["Referer"] = url
            resp = session.post(url, data=post_data, headers=post_headers, timeout=30)
            resp.raise_for_status()

    resp.encoding = resp.apparent_encoding or "utf-8"

    # Strona HTML - wyszukujemy dokumenty PDF
    items = extract_pdf_items_from_html(url, resp.text, headers)
    matched = filter_items(items, filter_val=filter_val, exclude_val=exclude_val, exclude_archive=exclude_archive)
    pdf_urls = list(dict.fromkeys(it["url"] for it in matched))

    if not pdf_urls and fallback_if_no_pdfs:
        return [url]

    return pdf_urls

def get_filename(url, headers=None):
    if headers:
        cd = headers.get("Content-Disposition", "")
        if cd and "filename" in cd:
            match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
            if match:
                fn = unquote(match.group(1).strip().strip('"').strip("'"))
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

        filter_val = item.get("filter") or item.get("target") or item.get("include")
        exclude_val = item.get("exclude")
        category_val = item.get("category")
        query_val = item.get("query")
        # Domyślnie wykluczamy archiwa jeśli podano filtr lub wykluczenia, chyba że w configu jawnie ustawiono exclude_archive
        exclude_archive = item.get("exclude_archive", True if (filter_val or exclude_val or category_val or query_val) else False)

        filter_info = f" [filtr: '{filter_val}']" if filter_val else ""
        if category_val:
            filter_info += f" [kategoria: '{category_val}']"
        print(f"\nSprawdzam: {product_key}{filter_info} ({page_url})...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            pdf_urls = get_pdf_urls_for_target(
                page_url,
                headers,
                filter_val=filter_val,
                exclude_val=exclude_val,
                exclude_archive=exclude_archive,
                fallback_if_no_pdfs=bool(item.get("filename")),
                category=category_val,
                query=query_val
            )
            if not pdf_urls:
                print(f"Nie znaleziono żadnych plików PDF pod adresem: {page_url}")
                continue

            print(f"Znaleziono {len(pdf_urls)} pasujący(ch) plik(ów) PDF.")

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
