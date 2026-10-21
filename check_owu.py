"""
OWU Sync - Automatyczny monitoring i synchronizacja dokumentów OWU z Dyskiem Google.
Obsługuje serwisy ubezpieczycieli (Warta, PZU, Compensa, Ergo Hestia i in.),
inteligentne filtrowanie, wykluczanie archiwaliów, sprawdzanie stanu na Dysku Google
oraz automatyczne wersjonowanie i archiwizację.
"""

import os
import re
import sys
import html
import time
import json
import hashlib
import mimetypes
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin, urlparse, unquote

# Wymuszenie natychmiastowego wypisywania logów w GitHub Actions (brak buforowania)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==============================================================================
# STAŁE I KONFIGURACJA
# ==============================================================================
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CONFIG_FILE = "config.json"
HASHES_FILE = "hashes.json"
TOKEN_FILE = "token.json"
CLIENT_SECRET_FILE = "client_secret.json"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def create_http_session():
    """Tworzy zoptymalizowaną sesję HTTP z pulą połączeń (keep-alive) i ponawianiem prób."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# ==============================================================================
# FUNKCJE POMOCNICZE (TEKST I PARSOWANIE)
# ==============================================================================
def normalize_text(text):
    """Konwertuje tekst do małych liter, odkodowuje encje HTML i usuwa polskie znaki."""
    if not text:
        return ""
    text = html.unescape(str(text)).lower()
    mapping = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'
    }
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text

def normalize_searchable(text):
    """Normalizuje tekst zamieniając separatory (podkreślniki, myślniki, kropki) na spacje dla elastycznego dopasowywania."""
    if not text:
        return ""
    text = normalize_text(text)
    return re.sub(r'[\s_\-/,.\(\)\[\]"\'„”\xa0]+', ' ', text).strip()

def is_excluded(text_to_check, exclude_val):
    """Sprawdza czy dany tekst (lub nazwa pliku) pasuje do którejkolwiek z reguł wykluczających."""
    if not exclude_val or not text_to_check:
        return False
    if isinstance(exclude_val, str):
        if ',' in exclude_val:
            exclude_words = [normalize_searchable(w) for w in exclude_val.split(',') if w.strip()]
        else:
            exclude_words = [normalize_searchable(exclude_val)]
    elif isinstance(exclude_val, list):
        exclude_words = [normalize_searchable(str(w)) for w in exclude_val if str(w).strip()]
    else:
        exclude_words = [normalize_searchable(str(exclude_val))]

    searchable = f" {normalize_searchable(text_to_check)} "
    for w in exclude_words:
        if not w:
            continue
        if f" {w} " in searchable or w in searchable:
            return True
    return False

def fix_utf8_encoding(text):
    if not text:
        return ""
    try:
        return text.encode('latin1').decode('utf-8')
    except Exception:
        return text

def unescape_devalue(val):
    if not val:
        return ""
    val = val.replace("https:_~s~_~s~", "https://")
    val = val.replace("http:_~s~_~s~", "http://")
    val = val.replace("_~s~", "/")
    val = val.replace("_~l~", "<")
    val = val.replace("_~g~", ">")
    val = val.replace("_~d~", '"')
    val = val.replace("_~a~", '&')
    return val

MONTH_NAMES_PATTERN = r'(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|wrze[sś]nia|pa[zź]dziernika|listopada|grudnia)'
DATE_PATTERN = r'\d{1,2}[.\-/\s_]\d{1,2}[.\-/\s_]\d{2,4}'
ARCHIVE_REGEX = re.compile(
    r'(?:obowi[aą]zuj[aącecy]{1,3}[_\s]+do|wa[zż]n[ey][_\s]+do|(?:\b|_)do[\s_]+' + DATE_PATTERN + r'|(?:\b|_)do[\s_]+\d{1,2}[\s_]+' + MONTH_NAMES_PATTERN + r'[\s_]+\d{4}|archiwaln)',
    re.I
)

def extract_pdf_items_from_html(base_url, html_text, session=None):
    """
    Ekstraktuje wszystkie dokumenty PDF ze strony HTML wraz z kontekstem i flagą archiwum.
    """
    items = []
    seen_urls = set()

    # 1. Obsługa formatu serializacji Generali (devalue serialization w sekcjach/akordeonach)
    if "_~s~" in html_text or "~s~" in html_text or "generali.pl" in base_url.lower():
        comp_matches = list(re.finditer(r'\{"__component":"(page\.[^"]+)"', html_text))
        for i, m in enumerate(comp_matches):
            start_idx = m.start()
            end_idx = comp_matches[i+1].start() if i+1 < len(comp_matches) else start_idx + 150000
            chunk = html_text[start_idx:end_idx]

            title_m = re.search(r'"Title":"([^"]+)"', chunk)
            title = fix_utf8_encoding(unescape_devalue(title_m.group(1))).strip() if title_m else ""

            file_matches = re.finditer(
                r'\{[^{}]*?"name"\s*:\s*"([^"]+)"[^{}]*?"alternativeText"\s*:\s*"([^"]*)"[^{}]*?"url"\s*:\s*"([^"]+)"[^{}]*?\}',
                chunk
            )
            for fm in file_matches:
                fn = fix_utf8_encoding(unescape_devalue(fm.group(1))).strip()
                alt = fix_utf8_encoding(unescape_devalue(fm.group(2))).strip()
                raw_url = unescape_devalue(fm.group(3)).strip()

                if not raw_url.startswith("http"):
                    raw_url = urljoin(base_url, raw_url)

                if ".pdf" in raw_url.lower() or fn.lower().endswith(".pdf"):
                    if raw_url in seen_urls:
                        continue
                    seen_urls.add(raw_url)

                    full_desc = f"{title} {fn} {alt}".strip()
                    is_arch = False
                    if ARCHIVE_REGEX.search(full_desc) or '/archiwum/' in raw_url.lower() or '/archive/' in raw_url.lower():
                        is_arch = True

                    items.append({
                        'url': raw_url,
                        'text': f"{fn} {alt}".strip(),
                        'context': title,
                        'is_archive': is_arch
                    })

        # Dodatkowy fallback na luźne linki Generali
        clean = re.sub(r'https:[_~s]+www', 'https://www', html_text)
        clean = re.sub(r'[_~]+s[_~]+', '/', clean)
        for m in re.finditer(r'(https://(?:www\.)?generali\.pl/media/[^\x22\x27\s<>]+\.pdf)', clean, re.I):
            u = m.group(1)
            if u not in seen_urls:
                seen_urls.add(u)
                items.append({
                    'url': u,
                    'text': '',
                    'context': '',
                    'is_archive': bool(ARCHIVE_REGEX.search(u) or '/archiwum/' in u.lower() or '/archive/' in u.lower())
                })

    clean_html = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', '', html_text, flags=re.I)

    # 2. Podział na sekcje wg nagłówków h1-h3 (kategorie/akordeony, np. Compensa)
    raw_sections = re.split(r'(<h[1-3][^>]*>.*?</h[1-3]>)', clean_html, flags=re.I)
    parsed_sections = []
    if len(raw_sections) > 1:
        if raw_sections[0].strip():
            parsed_sections.append(("", raw_sections[0]))
        for i in range(1, len(raw_sections), 2):
            h_text = re.sub(r'<[^>]+>', '', raw_sections[i]).strip()
            content = raw_sections[i + 1] if i + 1 < len(raw_sections) else ''
            parsed_sections.append((h_text, content))
    else:
        parsed_sections.append(("", clean_html))

    req = session or requests

    for cat_title, section_html in parsed_sections:
        # Wykrycie sekcji archiwum w obrębie danej sekcji / akordeonu
        arch_match = re.search(
            r'<(?:h[3-6]|strong|p|b|div)[^>]*>(?:<[^>]+>|\s)*?[Aa]rchiwum:?[\s\S]*?</(?:h[3-6]|strong|p|b|div)>',
            section_html,
            re.I
        )
        arch_pos = arch_match.start() if arch_match else len(section_html)

        # A. Klasyczne linki <a> z .pdf
        for m in re.finditer(r'<a[^>]+href=[\x22\x27]([^\x22\x27]*?\.pdf(?:\?[^\x22\x27]*)?)[\x22\x27][^>]*>(.*?)</a>', section_html, re.I | re.S):
            link_url = urljoin(base_url, m.group(1).strip())
            title_attr_m = re.search(r'title=[\x22\x27]([^\x22\x27]+)[\x22\x27]', m.group(0), re.I)
            aria_attr_m = re.search(r'aria-label=[\x22\x27]([^\x22\x27]+)[\x22\x27]', m.group(0), re.I)
            extra_desc = ""
            if title_attr_m:
                extra_desc += f" {title_attr_m.group(1)}"
            if aria_attr_m:
                extra_desc += f" {aria_attr_m.group(1)}"
            raw_text = re.sub(r'<[^>]+>', ' ', m.group(2)).strip() + extra_desc
            link_text = re.sub(r'\s+', ' ', raw_text)
            link_pos = m.start()

            is_arch = False
            if link_pos >= arch_pos:
                is_arch = True
            elif '/archiwum/' in link_url.lower() or '/archive/' in link_url.lower():
                is_arch = True
            elif ARCHIVE_REGEX.search(link_text):
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

        # B. Linki z data-url / data-href lub do repozytoriów plików (np. PZU fileserver)
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
                        head = req.head(cand_url, timeout=10, allow_redirects=True)
                        ct = head.headers.get("Content-Type", "").lower()
                        cd = head.headers.get("Content-Disposition", "").lower()
                        if "application/pdf" in ct or ".pdf" in cd:
                            real_fn = get_filename(cand_url, head.headers)
                            combined_text = f"{clean_text} {real_fn}".strip()
                            seen_urls.add(cand_url)
                            items.append({
                                'url': cand_url,
                                'text': combined_text,
                                'context': cat_title,
                                'preferred_filename': real_fn,
                                'is_archive': False
                            })
                    except Exception:
                        pass

        # C. Elementy z data-file='pdf' (np. PZU)
        data_pdf_pattern = r'<[^>]+data-file=[\x22\x27]pdf[\x22\x27][^>]*>[\s\S]{0,400}?href=[\x22\x27]([^\x22\x27]+)[\x22\x27]'
        for m in re.finditer(data_pdf_pattern, section_html, re.I):
            cand_url = urljoin(base_url, m.group(1).strip())
            if cand_url not in seen_urls:
                try:
                    head = req.head(cand_url, timeout=10, allow_redirects=True)
                    ct = head.headers.get("Content-Type", "").lower()
                    cd = head.headers.get("Content-Disposition", "").lower()
                    if "application/pdf" in ct or ".pdf" in cd:
                        real_fn = get_filename(cand_url, head.headers)
                        seen_urls.add(cand_url)
                        items.append({
                            'url': cand_url,
                            'text': real_fn,
                            'context': cat_title,
                            'preferred_filename': real_fn,
                            'is_archive': False
                        })
                except Exception:
                    pass

    return items

def filter_items(items, filter_val=None, exclude_val=None, exclude_archive=False):
    """
    Filtruje listę dokumentów:
    1. Odrzuca archiwa (jeśli exclude_archive=True).
    2. Odrzuca słowa i frazy wykluczające (exclude_val).
    3. Priorytetowo dopasowuje całą frazę (np. 'ERGO 1' lub 'GENERALI, Z MYŚLĄ O AUCIE').
    4. W razie potrzeby dopasowuje wszystkie słowa kluczowe (z granicami słów dla liczb).
    """
    active_items = [it for it in items if not (exclude_archive and it.get("is_archive"))]

    if exclude_val:
        active_items = [
            it for it in active_items
            if not is_excluded(f"{it.get('context', '')} {it.get('text', '')} {it.get('preferred_filename', '')} {it.get('url', '')}", exclude_val)
        ]

    if not filter_val:
        return active_items

    if isinstance(filter_val, list):
        norm_filter = " ".join(normalize_searchable(str(w)) for w in filter_val if str(w).strip())
        filter_words = [normalize_searchable(str(w)) for w in filter_val if str(w).strip()]
    else:
        norm_filter = normalize_searchable(str(filter_val)).strip()
        filter_words = [w for w in norm_filter.split(' ') if w]

    # 1. Priorytet: dopasowanie całej frazy w tekście, kontekście, nazwie pliku lub URL (z elastycznymi separatorami)
    phrase_pattern = r'\b' + r'[\s\-_/,\.„”"\'\(\)]+'.join(re.escape(w) for w in filter_words) + r'\b'
    phrase_matches = [
        it for it in active_items
        if re.search(phrase_pattern, normalize_text(f"{it.get('context', '')} {it.get('text', '')} {it.get('preferred_filename', '')} {it.get('url', '')}"))
    ]
    if phrase_matches:
        return phrase_matches

    # 2. Fallback: dopasowanie wszystkich słów z granicami słów dla liczb/krótkich kodów
    word_matches = []
    for it in active_items:
        searchable = normalize_searchable(f"{it.get('context', '')} {it.get('text', '')} {it.get('preferred_filename', '')} {it.get('url', '')}")
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

def get_pdf_urls_for_target(url, session, filter_val=None, exclude_val=None, exclude_archive=False, fallback_if_no_pdfs=False, category=None, query=None):
    """Pobiera i parsuje stronę (lub wysyła zapytanie wyszukiwarki), zwracając listę docelowych URL-i PDF."""
    clean_url = url.split("?")[0].split("#")[0]
    if clean_url.lower().endswith(".pdf"):
        return [url]

    resp = session.get(url, timeout=30)
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
            post_headers = {"Referer": url}
            resp = session.post(url, data=post_data, headers=post_headers, timeout=30)
            resp.raise_for_status()

    resp.encoding = resp.apparent_encoding or "utf-8"

    # Strona HTML - wyszukujemy dokumenty PDF
    items = extract_pdf_items_from_html(url, resp.text, session=session)
    matched = filter_items(items, filter_val=filter_val, exclude_val=exclude_val, exclude_archive=exclude_archive)
    pdf_urls = list(dict.fromkeys(it["url"] for it in matched))

    if not pdf_urls and fallback_if_no_pdfs:
        return [url]

    return pdf_urls

def get_filename(url, headers=None):
    """Pobiera nazwę pliku z nagłówka Content-Disposition (z dekodowaniem UTF-8) lub z URL."""
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

# ==============================================================================
# ZARZĄDZANIE DYSKIEM GOOGLE (Z CACHEM I WERYFIKACJĄ ISTNIENIA)
# ==============================================================================
def get_drive_service():
    """Autoryzacja Google Drive API."""
    creds = None
    env_token = os.environ.get("GDRIVE_TOKEN_JSON")
    if env_token:
        creds = Credentials.from_authorized_user_info(json.loads(env_token), SCOPES)
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except Exception as e:
                if env_token:
                    raise RuntimeError(
                        "Token Google Drive (GDRIVE_TOKEN_JSON) w GitHub Secrets wygasł lub został unieważniony przez Google (invalid_grant).\n"
                        "Powód: aplikacja OAuth w Google Cloud ma status 'Testing' (wtedy token wygasa po 7 dniach).\n"
                        "Rozwiązanie: w Google Cloud Console przestaw 'Publishing status' na 'In production', "
                        "wygeneruj nowy token.json lokalnie i wklej go do GitHub Secrets jako GDRIVE_TOKEN_JSON."
                    ) from e
                print(f"Token wygasł i nie dało się go automatycznie odświeżyć ({e}).")
                print("Uruchamiam logowanie w przeglądarce, aby wygenerować nowy token...")

        if not refreshed:
            if not os.path.exists(CLIENT_SECRET_FILE):
                raise FileNotFoundError(f"Brak pliku {CLIENT_SECRET_FILE}. Umieść go w głównym katalogu.")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)

class DriveManager:
    """Klasa optymalizująca operacje na Dysku Google poprzez buforowanie zawartości folderów."""
    def __init__(self, service):
        self.service = service
        self.folder_cache = {}          # folder_id -> {filename: file_dict}
        self.archive_folder_cache = {}  # (parent_id, folder_name) -> archive_folder_id

    def get_folder_files(self, folder_id):
        """Pobiera zawartość folderu za jednym zapytaniem do API Dysku Google."""
        clean_id = folder_id.strip().split("?")[0]
        if clean_id not in self.folder_cache:
            query = f"'{clean_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"
            results = self.service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=1000
            ).execute()
            self.folder_cache[clean_id] = {f["name"]: f for f in results.get("files", [])}
        return self.folder_cache[clean_id]

    def file_exists(self, filename, folder_id):
        """Sprawdza czy plik fizycznie istnieje w danym folderze na Dysku Google."""
        return filename in self.get_folder_files(folder_id)

    def get_or_create_archive_folder(self, parent_folder_id, folder_name="Archiwum"):
        """Pobiera lub tworzy folder archiwum (z buforowaniem ID w pamięci)."""
        clean_parent = parent_folder_id.strip().split("?")[0]
        cache_key = (clean_parent, folder_name)
        if cache_key in self.archive_folder_cache:
            return self.archive_folder_cache[cache_key]

        query = (
            f"name = '{folder_name}' and "
            f"'{clean_parent}' in parents and "
            f"mimeType = 'application/vnd.google-apps.folder' and "
            f"trashed = false"
        )
        results = self.service.files().list(q=query, fields="files(id)").execute()
        items = results.get("files", [])
        if items:
            archive_id = items[0]["id"]
        else:
            metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [clean_parent]
            }
            folder = self.service.files().create(body=metadata, fields="id").execute()
            print(f"Utworzono nowy folder archiwum: '{folder_name}'")
            archive_id = folder["id"]

        self.archive_folder_cache[cache_key] = archive_id
        return archive_id

    def move_file_to_archive(self, filename, folder_id, company="", archive_folder_id=None, archive_folder_name=None):
        """
        Przenosi plik do archiwum TYLKO jeśli plik faktycznie istnieje w folderze głównym.
        Zwraca nazwę zarchiwizowanego pliku lub None jeśli pliku nie ma na Dysku.
        """
        clean_folder = folder_id.strip().split("?")[0]
        files = self.get_folder_files(clean_folder)
        file_info = files.get(filename)
        if not file_info:
            return None

        old_file_id = file_info["id"]
        target_archive_id = archive_folder_id
        if not target_archive_id:
            target_name = archive_folder_name or (f"Archiwum {company}".strip() if company else "Archiwum")
            target_archive_id = self.get_or_create_archive_folder(clean_folder, target_name)

        name_part, ext_part = os.path.splitext(filename)
        date_str = datetime.now().strftime("%Y-%m-%d")
        archived_filename = f"{name_part}_arch_{date_str}{ext_part}"

        # Sprawdzenie unikalności nazwy w folderze archiwum
        check_q = f"name = '{archived_filename}' and '{target_archive_id}' in parents and trashed = false"
        arch_items = self.service.files().list(q=check_q, fields="files(id)").execute().get("files", [])
        if arch_items:
            time_str = datetime.now().strftime("%H%M%S")
            archived_filename = f"{name_part}_arch_{date_str}_{time_str}{ext_part}"

        self.service.files().update(
            fileId=old_file_id,
            addParents=target_archive_id,
            removeParents=clean_folder,
            body={"name": archived_filename},
            fields="id, parents, name"
        ).execute()

        # Usunięcie z lokalnego cache folderu głównego
        files.pop(filename, None)
        print(f"Zarchiwizowano stary plik jako '{archived_filename}' w folderze archiwum.")
        return archived_filename

    def upload_file(self, file_bytes, filename, folder_id, company="", archive_folder_id=None, archive_folder_name=None):
        """Wgrywa plik na Dysk Google. Jeśli plik o tej nazwie już istnieje na Dysku, najpierw go archiwizuje."""
        clean_folder = folder_id.strip().split("?")[0]

        # Jeśli stary plik fizycznie istnieje na Dysku -> przenieś go do archiwum
        if self.file_exists(filename, clean_folder):
            self.move_file_to_archive(filename, clean_folder, company, archive_folder_id, archive_folder_name)

        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/pdf"

        new_file = None
        for attempt in range(3):
            try:
                media = MediaIoBaseUpload(BytesIO(file_bytes), mimetype=mime_type, resumable=True)
                metadata = {"name": filename, "parents": [clean_folder]}
                new_file = self.service.files().create(body=metadata, media_body=media, fields="id, name").execute()
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                else:
                    raise e

        # Dodanie do lokalnego cache folderu
        files = self.get_folder_files(clean_folder)
        files[filename] = new_file
        print(f"Pobrano i wgrano plik na Dysk Google: {filename}")
        return new_file["id"]

# ==============================================================================
# POWIADOMIENIA E-MAIL
# ==============================================================================
def send_email_notification(changes):
    """Wysyła estetyczne powiadomienie e-mail w formacie HTML o wykrytych zmianach w OWU."""
    smtp_user = os.environ.get("EMAIL_SENDER") or os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("EMAIL_PASSWORD") or os.environ.get("SMTP_PASSWORD")
    recipient = os.environ.get("EMAIL_RECEIVER") or smtp_user
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))

    if not smtp_user or not smtp_pass or not recipient:
        print("Powiadomienia e-mail: Brak skonfigurowanych zmiennych EMAIL_SENDER / EMAIL_PASSWORD (pomijam wysyłkę).")
        return

    subject = f"[OWU SYNC] Wykryto zmiany w dokumentach ({len(changes)})"

    rows_html = ""
    for c in changes:
        action_color = "#10b981" if "Nowy" in c["action"] else ("#3b82f6" if "Zaktualizowana" in c["action"] else "#f59e0b")
        drive_link = f"https://drive.google.com/drive/folders/{c['folder_id']}" if c.get('folder_id') else "#"
        rows_html += f"""
        <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 10px; font-weight: bold; color: #1e293b;">{c['company']}</td>
            <td style="padding: 10px; color: #334155;">{c['product']}</td>
            <td style="padding: 10px;"><span style="background-color: {action_color}; color: white; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600;">{c['action']}</span></td>
            <td style="padding: 10px; font-family: monospace; font-size: 12px; color: #0f172a;">{c['filename']}</td>
            <td style="padding: 10px;"><a href="{drive_link}" style="color: #2563eb; text-decoration: none; font-weight: 600; font-size: 12px;" target="_blank">Otwórz Dysk &rarr;</a></td>
        </tr>
        """

    html_content = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 20px; color: #1e293b;">
        <div style="max-width: 700px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="background: linear-gradient(135deg, #1e3a8a, #2563eb); padding: 20px 24px; color: #ffffff;">
                <h2 style="margin: 0; font-size: 20px; font-weight: bold;">OWU Sync - Wykryto zmiany w dokumentach</h2>
                <p style="margin: 6px 0 0 0; font-size: 13px; opacity: 0.9;">Zarejestrowano {len(changes)} zmian(y) podczas ostatniego cyklu skanowania.</p>
            </div>
            <div style="padding: 20px 24px;">
                <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
                    <thead>
                        <tr style="background-color: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase;">
                            <th style="padding: 10px;">Firma</th>
                            <th style="padding: 10px;">Produkt</th>
                            <th style="padding: 10px;">Zdarzenie</th>
                            <th style="padding: 10px;">Plik</th>
                            <th style="padding: 10px;">Dysk</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0; text-align: center;">
                    <a href="https://basina194.github.io/OWU_SYNC/" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 9px 18px; border-radius: 8px; font-size: 13px; font-weight: 600;" target="_blank">Otwórz Panel OWU Hub</a>
                </div>
            </div>
            <div style="background-color: #f8fafc; padding: 12px 24px; font-size: 11px; color: #64748b; border-top: 1px solid #e2e8f0; text-align: center;">
                Wiadomość wygenerowana automatycznie przez OWU Sync Bot w chmurze GitHub Actions.
            </div>
        </div>
    </body>
    </html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = recipient
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [recipient], msg.as_string())
        print(f"Pomyślnie wysłano powiadomienie e-mail o zmianach na adres: {recipient}")
    except Exception as err:
        print(f"Błąd podczas wysyłania powiadomienia e-mail: {err}")


# ==============================================================================
# GŁÓWNA PĘTLA PROGRAMU
# ==============================================================================
def main():
    if "--test-email" in sys.argv or os.environ.get("TEST_EMAIL") == "1":
        print("Tryb testowy: Wysyłanie próbnego powiadomienia e-mail...")
        test_changes = [
            {
                "action": "Nowy dokument (Test)",
                "company": "PZU",
                "product": "Auto OC (Test)",
                "filename": "Test_OWU_Sync.pdf",
                "folder_id": ""
            }
        ]
        send_email_notification(test_changes)
        return
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
    drive = DriveManager(service)
    session = create_http_session()
    has_changes = False
    notification_changes = []

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
        exclude_archive = item.get("exclude_archive", True if (filter_val or exclude_val or category_val or query_val) else False)

        filter_info = f" [filtr: '{filter_val}']" if filter_val else ""
        if exclude_val:
            filter_info += f" [wyklucz: '{exclude_val}']"
        if category_val:
            filter_info += f" [kategoria: '{category_val}']"
        print(f"\nSprawdzam: {product_key}{filter_info} ({page_url})...")

        try:
            pdf_urls = get_pdf_urls_for_target(
                url=page_url,
                session=session,
                filter_val=filter_val,
                exclude_val=exclude_val,
                exclude_archive=exclude_archive,
                fallback_if_no_pdfs=bool(item.get("filename")),
                category=category_val,
                query=query_val
            )
            if not pdf_urls:
                print(f"Nie znaleziono pasujących plików PDF pod adresem: {page_url}")
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
                    resp = session.get(pdf_url, timeout=30)
                    resp.raise_for_status()

                    if len(pdf_urls) == 1 and item.get("filename"):
                        filename = item["filename"]
                    else:
                        filename = get_filename(pdf_url, resp.headers)

                    # Bezpiecznik: jeśli nazwa pliku zawiera frazę wykluczoną (np. lista warsztatów)
                    if is_excluded(filename, exclude_val):
                        print(f"-> Pomijam plik (wykluczenie z konfiguracji): {filename}")
                        continue

                    current_filenames.add(filename)
                    current_hash = hashlib.sha256(resp.content).hexdigest()
                    current_product_hashes[filename] = current_hash

                    # Weryfikacja: czy plik fizycznie istnieje na Dysku Google oraz czy zmienił się hash
                    file_on_drive = drive.file_exists(filename, folder_id)
                    hash_changed = (prev_hashes.get(filename) != current_hash)

                    if not file_on_drive:
                        print(f"-> Brak pliku na Dysku Google (wymagane wgranie): {filename}")
                        drive.upload_file(
                            file_bytes=resp.content,
                            filename=filename,
                            folder_id=folder_id,
                            company=company,
                            archive_folder_id=archive_folder_id,
                            archive_folder_name=archive_folder_name
                        )
                        has_changes = True
                        notification_changes.append({"action": "Nowy dokument", "company": company, "product": product, "filename": filename, "folder_id": folder_id})
                    elif hash_changed:
                        print(f"-> Wykryto nową wersję pliku: {filename}")
                        drive.upload_file(
                            file_bytes=resp.content,
                            filename=filename,
                            folder_id=folder_id,
                            company=company,
                            archive_folder_id=archive_folder_id,
                            archive_folder_name=archive_folder_name
                        )
                        has_changes = True
                        notification_changes.append({"action": "Zaktualizowana treść OWU", "company": company, "product": product, "filename": filename, "folder_id": folder_id})
                    else:
                        print(f"Brak zmian (plik aktualny na Dysku Google): {filename}")

                except Exception as file_err:
                    print(f"Błąd przy pobieraniu pliku {pdf_url}: {file_err}")

            # Wykrywanie plików, które usunięto ze strony lub z filtrów
            removed_files = set(prev_hashes.keys()) - current_filenames
            for removed_fn in removed_files:
                if drive.file_exists(removed_fn, folder_id):
                    print(f"-> Plik {removed_fn} nie występuje już w konfiguracji/na stronie - przenoszę do archiwum.")
                    drive.move_file_to_archive(
                        filename=removed_fn,
                        folder_id=folder_id,
                        company=company,
                        archive_folder_id=archive_folder_id,
                        archive_folder_name=archive_folder_name
                    )
                    has_changes = True
                    notification_changes.append({"action": "Przeniesiono do archiwum", "company": company, "product": product, "filename": removed_fn, "folder_id": folder_id})
                else:
                    print(f"-> Plik {removed_fn} usunięty z monitoringu (brak na Dysku Google - pomijam archiwizację).")

            known_hashes[product_key] = current_product_hashes

        except Exception as e:
            print(f"Błąd przy sprawdzaniu {product_key}: {e}")

    if has_changes:
        with open(HASHES_FILE, "w", encoding="utf-8") as f:
            json.dump(known_hashes, f, indent=2)
        print("\nZaktualizowano bazę sum kontrolnych hashes.json.")

    try:
        import build_dashboard
        build_dashboard.generate()
    except Exception as dash_err:
        print(f"Uwaga: Nie udało się zaktualizować panelu dashboard: {dash_err}")

    if notification_changes:
        send_email_notification(notification_changes)

if __name__ == '__main__':
    main()

