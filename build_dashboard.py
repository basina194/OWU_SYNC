import json
import os
from datetime import datetime

CONFIG_FILE = "config.json"
HASHES_FILE = "hashes.json"
OUTPUT_HTML = "index.html"

COMPANY_COLORS = {
    "PZU": {"badge": "bg-blue-100 text-blue-800 border-blue-200", "border": "border-blue-500", "accent": "#00529c"},
    "Warta": {"badge": "bg-cyan-100 text-cyan-800 border-cyan-200", "border": "border-cyan-600", "accent": "#002d72"},
    "HDI": {"badge": "bg-indigo-100 text-indigo-800 border-indigo-200", "border": "border-indigo-500", "accent": "#1e3a8a"},
    "Generali": {"badge": "bg-red-100 text-red-800 border-red-200", "border": "border-red-500", "accent": "#c8102e"},
    "Ergo_Hestia": {"badge": "bg-amber-100 text-amber-800 border-amber-200", "border": "border-amber-500", "accent": "#d97706"},
    "Compensa": {"badge": "bg-emerald-100 text-emerald-800 border-emerald-200", "border": "border-emerald-500", "accent": "#059669"},
    "Uniqa": {"badge": "bg-sky-100 text-sky-800 border-sky-200", "border": "border-sky-600", "accent": "#0284c7"},
    "Wiener": {"badge": "bg-orange-100 text-orange-800 border-orange-200", "border": "border-orange-500", "accent": "#ea580c"},
    "MTU": {"badge": "bg-teal-100 text-teal-800 border-teal-200", "border": "border-teal-500", "accent": "#0d9488"},
    "MTU24": {"badge": "bg-purple-100 text-purple-800 border-purple-200", "border": "border-purple-500", "accent": "#7c3aed"},
    "BBC": {"badge": "bg-gray-100 text-gray-800 border-gray-200", "border": "border-gray-400", "accent": "#4b5563"},
}

def format_company_name(name):
    return name.replace("_", " ")

def generate():
    if not os.path.exists(CONFIG_FILE) or not os.path.exists(HASHES_FILE):
        print(f"Brak pliku {CONFIG_FILE} lub {HASHES_FILE}!")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    with open(HASHES_FILE, "r", encoding="utf-8") as f:
        hashes_data = json.load(f)

    items = []
    total_docs = 0
    all_companies = set()

    for entry in config_data:
        company = entry.get("company", "Inne")
        product = entry.get("product", "")
        product_key = f"{company}_{product}".strip("_")
        page_url = entry.get("url", "#")
        folder_id = entry.get("drive_folder_id", "").strip().split("?")[0]
        drive_url = f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else "#"

        all_companies.add(company)

        # Pobieranie listy plików i hashy
        raw_docs = hashes_data.get(product_key, {})
        doc_list = []
        if isinstance(raw_docs, dict):
            for fname, fhash in raw_docs.items():
                doc_list.append({"name": fname, "hash": fhash[:12] if isinstance(fhash, str) else ""})
                total_docs += 1
        elif isinstance(raw_docs, str):
            doc_list.append({"name": product, "hash": raw_docs[:12]})
            total_docs += 1

        filters = []
        if entry.get("filter"):
            filters.append(f"Filtr: {entry['filter']}")
        if entry.get("exclude"):
            ex = entry["exclude"]
            if isinstance(ex, list):
                filters.append(f"Wyklucz: {', '.join(ex)}")
            else:
                filters.append(f"Wyklucz: {ex}")
        if entry.get("category"):
            filters.append(f"Kategoria: {entry['category']}")

        items.append({
            "company": company,
            "company_display": format_company_name(company),
            "product": product,
            "product_key": product_key,
            "page_url": page_url,
            "drive_url": drive_url,
            "documents": doc_list,
            "doc_count": len(doc_list),
            "filters": filters
        })

    # Sortowanie: wg ubezpieczyciela, potem produktu
    items.sort(key=lambda x: (x["company"].lower(), x["product"].lower()))

    # Przygotowanie danych do wbudowania w HTML
    dashboard_data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_companies": len(all_companies),
        "total_products": len(items),
        "total_documents": total_docs,
        "companies": sorted(list(all_companies)),
        "items": items
    }

    data_json_str = json.dumps(dashboard_data, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="pl" class="h-full">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OWU Sync Hub - Panel Monitorowania i Synchronizacji</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          fontFamily: {{
            sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
          }},
          colors: {{
            brand: {{
              50: '#eff6ff',
              100: '#dbeafe',
              500: '#3b82f6',
              600: '#2563eb',
              700: '#1d4ed8',
              800: '#1e40af',
              900: '#1e3a8a',
            }}
          }}
        }}
      }}
    }}
  </script>
  <style>
    body {{
      font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
    }}
    .custom-scrollbar::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    .custom-scrollbar::-webkit-scrollbar-track {{
      background: rgba(0, 0, 0, 0.03);
    }}
    .custom-scrollbar::-webkit-scrollbar-thumb {{
      background: rgba(156, 163, 175, 0.4);
      border-radius: 4px;
    }}
  </style>
</head>
<body class="h-full bg-slate-50 text-slate-800 dark:bg-slate-950 dark:text-slate-100 transition-colors duration-200">
  <div class="min-h-full flex flex-col">
    <!-- Górny Pasek Nawigacyjny -->
    <header class="sticky top-0 z-30 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200/80 dark:border-slate-800">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex items-center justify-between h-16">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
              </svg>
            </div>
            <div>
              <div class="flex items-center gap-2">
                <span class="font-bold text-lg tracking-tight bg-gradient-to-r from-slate-900 to-slate-700 dark:from-white dark:to-slate-300 bg-clip-text text-transparent">OWU Sync Hub</span>
                <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/70 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800">
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  Online
                </span>
              </div>
              <p class="text-xs text-slate-500 dark:text-slate-400 hidden sm:block">Automatyczny system weryfikacji i synchronizacji dokumentów OWU</p>
            </div>
          </div>

          <div class="flex items-center gap-2 sm:gap-3">
            <button id="themeToggle" class="p-2 rounded-xl text-slate-500 hover:text-slate-700 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-800 transition" title="Zmień motyw">
              <!-- Słońce (dla dark) -->
              <svg id="sunIcon" class="w-5 h-5 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
              <!-- Księżyc (dla light) -->
              <svg id="moonIcon" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            </button>
            <a href="https://github.com/basina194/OWU_SYNC" target="_blank" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 dark:text-slate-300 dark:bg-slate-800 dark:hover:bg-slate-700 rounded-xl transition">
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
              <span>GitHub</span>
            </a>
          </div>
        </div>
      </div>
    </header>

    <!-- Główna Zawartość -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
      
      <!-- Statystyki / Karty KPI -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Towarzystwa</span>
            <div class="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 flex items-center justify-center">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
            </div>
          </div>
          <p id="statCompanies" class="text-2xl sm:text-3xl font-extrabold mt-2 text-slate-900 dark:text-white">-</p>
          <span class="text-xs text-slate-500 dark:text-slate-400">Wszystkie monitorowane firmy</span>
        </div>

        <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Produkty</span>
            <div class="w-8 h-8 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
            </div>
          </div>
          <p id="statProducts" class="text-2xl sm:text-3xl font-extrabold mt-2 text-slate-900 dark:text-white">-</p>
          <span class="text-xs text-slate-500 dark:text-slate-400">Śledzone kategorie polis</span>
        </div>

        <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Dokumenty OWU</span>
            <div class="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/></svg>
            </div>
          </div>
          <p id="statDocs" class="text-2xl sm:text-3xl font-extrabold mt-2 text-slate-900 dark:text-white">-</p>
          <span class="text-xs text-slate-500 dark:text-slate-400">Pliki zsynchronizowane na Dysku</span>
        </div>

        <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Ostatni cykl</span>
            <div class="w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 flex items-center justify-center">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
          </div>
          <p id="statSync" class="text-base sm:text-lg font-bold mt-3 text-slate-900 dark:text-white truncate">-</p>
          <span class="text-xs text-slate-500 dark:text-slate-400">Codziennie o 06:00 UTC</span>
        </div>
      </div>

      <!-- Filtry, Wyszukiwarka i Kontrolki -->
      <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-6 border border-slate-200/80 dark:border-slate-800 shadow-sm mb-6 space-y-4">
        <div class="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
          
          <!-- Pole Wyszukiwania -->
          <div class="relative flex-1">
            <div class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
              </svg>
            </div>
            <input type="text" id="searchInput" placeholder="Szukaj firmy, produktu, lub nazwy pliku PDF..." class="w-full pl-10 pr-10 py-2.5 bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition">
            <button id="clearSearch" class="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 hidden">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>

          <!-- Przełącznik Widoku (Karty / Tabela) -->
          <div class="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-xl self-end md:self-auto">
            <button id="viewGrid" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm transition">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
              <span>Karty</span>
            </button>
            <button id="viewTable" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16"/></svg>
              <span>Tabela</span>
            </button>
          </div>
        </div>

        <!-- Przyciski Szybkiego Wyboru Towarzystwa (Filtry Pills) -->
        <div id="companyPills" class="flex items-center gap-1.5 overflow-x-auto pb-1 custom-scrollbar text-xs">
          <!-- Wstrzykiwane przez JS -->
        </div>
      </div>

      <!-- Licznik wyników -->
      <div class="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mb-4 px-1">
        <div>Wyświetlanie: <span id="resultsCount" class="font-bold text-slate-800 dark:text-slate-200">0</span> z <span id="totalCount" class="font-bold text-slate-800 dark:text-slate-200">0</span> produktów</div>
        <div id="filterIndicator" class="hidden text-blue-600 dark:text-blue-400 font-medium">Aktywny filtr towarzystwa</div>
      </div>

      <!-- Widok Siatki (Karty) -->
      <div id="gridContainer" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        <!-- Generowane dynamicznie -->
      </div>

      <!-- Widok Tabeli -->
      <div id="tableContainer" class="hidden bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="bg-slate-50 dark:bg-slate-800/60 text-slate-600 dark:text-slate-400 text-xs uppercase tracking-wider border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th class="py-3 px-4">Towarzystwo</th>
                <th class="py-3 px-4">Produkt</th>
                <th class="py-3 px-4">Pliki OWU</th>
                <th class="py-3 px-4 text-right">Odnośniki</th>
              </tr>
            </thead>
            <tbody id="tableBody" class="divide-y divide-slate-100 dark:divide-slate-800">
              <!-- Wiersze generowane dynamicznie -->
            </tbody>
          </table>
        </div>
      </div>

      <!-- Komunikat braku wyników -->
      <div id="noResults" class="hidden text-center py-16">
        <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-400">
          <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        </div>
        <h3 class="text-base font-semibold text-slate-800 dark:text-slate-200">Nie znaleziono pasujących pozycji</h3>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">Spróbuj zmienić słowa kluczowe lub zresetuj filtr towarzystwa.</p>
      </div>

    </main>

    <!-- Stopka -->
    <footer class="mt-auto border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 py-6">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500 dark:text-slate-400">
        <div class="flex items-center gap-2">
          <span>OWU Sync System</span>
          <span>•</span>
          <span>GitHub Actions + Google Drive</span>
        </div>
        <div>
          Hosting: <span class="font-medium text-slate-700 dark:text-slate-300">GitHub Pages</span>
        </div>
      </div>
    </footer>
  </div>

  <!-- Dane zsynchronizowane ze skryptem Python -->
  <script>
    window.OWU_DATA = {data_json_str};
  </script>

  <!-- Logika aplikacji Frontend -->
  <script>
    document.addEventListener('DOMContentLoaded', () => {{
      const data = window.OWU_DATA;
      if (!data) return;

      // Stan widoku
      let currentCompany = 'all';
      let searchQuery = '';
      let isTableView = false;

      // Inicjalizacja metryk
      document.getElementById('statCompanies').textContent = data.total_companies;
      document.getElementById('statProducts').textContent = data.total_products;
      document.getElementById('statDocs').textContent = data.total_documents;
      document.getElementById('statSync').textContent = data.generated_at;
      document.getElementById('totalCount').textContent = data.total_products;

      // Przełącznik ciemnego motywu
      const themeToggle = document.getElementById('themeToggle');
      const sunIcon = document.getElementById('sunIcon');
      const moonIcon = document.getElementById('moonIcon');

      function updateTheme(isDark) {{
        if (isDark) {{
          document.documentElement.classList.add('dark');
          sunIcon.classList.remove('hidden');
          moonIcon.classList.add('hidden');
          localStorage.setItem('theme', 'dark');
        }} else {{
          document.documentElement.classList.remove('dark');
          sunIcon.classList.add('hidden');
          moonIcon.classList.remove('hidden');
          localStorage.setItem('theme', 'light');
        }}
      }}

      const savedTheme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      updateTheme(savedTheme === 'dark');

      themeToggle.addEventListener('click', () => {{
        updateTheme(!document.documentElement.classList.contains('dark'));
      }});

      // Generowanie przycisków Towarzystw
      const pillsContainer = document.getElementById('companyPills');
      const allCompanies = ['all', ...data.companies];

      function renderPills() {{
        pillsContainer.innerHTML = allCompanies.map(c => {{
          const isSelected = c === currentCompany;
          const label = c === 'all' ? 'Wszystkie' : c.replace('_', ' ');
          const count = c === 'all' ? data.total_products : data.items.filter(i => i.company === c).length;
          const activeClasses = isSelected 
            ? 'bg-blue-600 text-white shadow-sm shadow-blue-500/20' 
            : 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300';
          return `
            <button data-company="${{c}}" class="company-pill whitespace-nowrap px-3 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 ${{activeClasses}}">
              <span>${{label}}</span>
              <span class="text-[10px] px-1.5 py-0.2 rounded-full ${{isSelected ? 'bg-white/20 text-white' : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-400'}}">${{count}}</span>
            </button>
          `;
        }}).join('');

        pillsContainer.querySelectorAll('.company-pill').forEach(btn => {{
          btn.addEventListener('click', () => {{
            currentCompany = btn.dataset.company;
            renderPills();
            renderContent();
          }});
        }});
      }}

      renderPills();

      // Przełączanie widoków
      const viewGridBtn = document.getElementById('viewGrid');
      const viewTableBtn = document.getElementById('viewTable');
      const gridContainer = document.getElementById('gridContainer');
      const tableContainer = document.getElementById('tableContainer');

      viewGridBtn.addEventListener('click', () => {{
        isTableView = false;
        viewGridBtn.className = 'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm transition';
        viewTableBtn.className = 'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition';
        gridContainer.classList.remove('hidden');
        tableContainer.classList.add('hidden');
      }});

      viewTableBtn.addEventListener('click', () => {{
        isTableView = true;
        viewTableBtn.className = 'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm transition';
        viewGridBtn.className = 'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition';
        tableContainer.classList.remove('hidden');
        gridContainer.classList.add('hidden');
      }});

      // Wyszukiwarka
      const searchInput = document.getElementById('searchInput');
      const clearSearch = document.getElementById('clearSearch');

      searchInput.addEventListener('input', (e) => {{
        searchQuery = e.target.value.toLowerCase().trim();
        clearSearch.classList.toggle('hidden', searchQuery.length === 0);
        renderContent();
      }});

      clearSearch.addEventListener('click', () => {{
        searchInput.value = '';
        searchQuery = '';
        clearSearch.classList.add('hidden');
        renderContent();
      }});

      // Mapowanie stylów badge dla towarzystw
      const companyColors = {{
        "PZU": "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800",
        "Warta": "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-800",
        "HDI": "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-300 dark:border-indigo-800",
        "Generali": "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800",
        "Ergo_Hestia": "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800",
        "Compensa": "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800",
        "Uniqa": "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950/40 dark:text-cyan-300 dark:border-cyan-800",
        "Wiener": "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950/40 dark:text-orange-300 dark:border-orange-800",
        "MTU": "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950/40 dark:text-teal-300 dark:border-teal-800",
        "MTU24": "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/40 dark:text-purple-300 dark:border-purple-800",
      }};

      function getCompanyBadgeClass(comp) {{
        return companyColors[comp] || "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700";
      }}

      // Główny render zawartości
      function renderContent() {{
        const filtered = data.items.filter(item => {{
          const matchesCompany = currentCompany === 'all' || item.company === currentCompany;
          if (!matchesCompany) return false;

          if (!searchQuery) return true;
          const searchIn = [
            item.company,
            item.company_display,
            item.product,
            ...item.documents.map(d => d.name)
          ].join(' ').toLowerCase();

          return searchIn.includes(searchQuery);
        }});

        document.getElementById('resultsCount').textContent = filtered.length;
        document.getElementById('noResults').classList.toggle('hidden', filtered.length > 0);

        // Render kart
        gridContainer.innerHTML = filtered.map(item => {{
          const badgeClass = getCompanyBadgeClass(item.company);
          const docsHtml = item.documents.length > 0 
            ? item.documents.map(doc => `
              <li class="flex items-start gap-2 py-1.5 px-2 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800/80 text-xs text-slate-700 dark:text-slate-300">
                <svg class="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path>
                </svg>
                <div class="flex-1 min-w-0">
                  <p class="font-medium truncate" title="${{doc.name}}">${{doc.name}}</p>
                  <p class="text-[10px] text-slate-400 font-mono mt-0.5">SHA: ${{doc.hash}}...</p>
                </div>
              </li>
            `).join('')
            : `<li class="text-xs text-slate-400 italic py-2">Brak zarejestrowanych plików PDF</li>`;

          const filtersHtml = item.filters.length > 0
            ? `<div class="mt-2.5 flex flex-wrap gap-1">
                ${{item.filters.map(f => `<span class="inline-block text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700">${{f}}</span>`).join('')}}
               </div>`
            : '';

          return `
            <div class="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow">
              <div>
                <div class="flex items-center justify-between gap-2 mb-3">
                  <span class="px-2.5 py-1 rounded-lg text-xs font-semibold border ${{badgeClass}}">
                    ${{item.company_display}}
                  </span>
                  <span class="inline-flex items-center gap-1 text-xs font-medium text-slate-500 dark:text-slate-400">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                    ${{item.doc_count}} PDF
                  </span>
                </div>
                
                <h3 class="font-bold text-base text-slate-900 dark:text-white tracking-tight mb-1">${{item.product}}</h3>
                ${{filtersHtml}}

                <div class="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800">
                  <p class="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-2">Pobrane dokumenty:</p>
                  <ul class="space-y-1.5 max-h-48 overflow-y-auto custom-scrollbar pr-1">
                    ${{docsHtml}}
                  </ul>
                </div>
              </div>

              <div class="mt-5 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center gap-2">
                <a href="${{item.drive_url}}" target="_blank" class="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl transition shadow-sm shadow-blue-500/20">
                  <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/>
                  </svg>
                  <span>Dysk Google</span>
                </a>
                <a href="${{item.page_url}}" target="_blank" class="inline-flex items-center justify-center p-2 text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 rounded-xl transition" title="Strona ubezpieczyciela">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                </a>
              </div>
            </div>
          `;
        }}).join('');

        // Render tabeli
        const tableBody = document.getElementById('tableBody');
        tableBody.innerHTML = filtered.map(item => {{
          const badgeClass = getCompanyBadgeClass(item.company);
          const docsText = item.documents.length > 0 
            ? item.documents.map(d => `<div class="truncate max-w-xs text-xs text-slate-700 dark:text-slate-300 py-0.5">• ${{d.name}}</div>`).join('')
            : `<span class="text-xs text-slate-400 italic">Brak</span>`;

          return `
            <tr class="hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition">
              <td class="py-3 px-4 whitespace-nowrap">
                <span class="px-2.5 py-0.5 rounded-lg text-xs font-semibold border ${{badgeClass}}">
                  ${{item.company_display}}
                </span>
              </td>
              <td class="py-3 px-4 font-semibold text-slate-900 dark:text-white whitespace-nowrap">
                ${{item.product}}
              </td>
              <td class="py-3 px-4">
                ${{docsText}}
              </td>
              <td class="py-3 px-4 text-right whitespace-nowrap">
                <div class="flex items-center justify-end gap-2">
                  <a href="${{item.drive_url}}" target="_blank" class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/40 hover:bg-blue-100 dark:hover:bg-blue-900/60 rounded-lg transition">
                    <span>Dysk</span>
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                  </a>
                  <a href="${{item.page_url}}" target="_blank" class="p-1 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition" title="Strona WWW">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                  </a>
                </div>
              </td>
            </tr>
          `;
        }}).join('');
      }}

      renderContent();
    }});
  </script>
</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Pomyślnie wygenerowano plik {OUTPUT_HTML} (Towarzystwa: {len(all_companies)}, Produkty: {len(items)}, Dokumenty: {total_docs})")

if __name__ == "__main__":
    generate()
