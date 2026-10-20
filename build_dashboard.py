import json
import os
from datetime import datetime

CONFIG_FILE = "config.json"
HASHES_FILE = "hashes.json"
OUTPUT_HTML = "index.html"

COMPANY_GRADIENTS = {
    "PZU": "from-blue-600 to-blue-700 text-white",
    "Warta": "from-sky-600 to-cyan-700 text-white",
    "HDI": "from-indigo-600 to-blue-800 text-white",
    "Generali": "from-rose-600 to-red-700 text-white",
    "Ergo_Hestia": "from-amber-600 to-orange-700 text-white",
    "Compensa": "from-emerald-600 to-teal-700 text-white",
    "Uniqa": "from-cyan-600 to-blue-700 text-white",
    "Wiener": "from-orange-600 to-amber-700 text-white",
    "MTU": "from-teal-600 to-emerald-700 text-white",
    "MTU24": "from-purple-600 to-indigo-700 text-white",
    "BBC": "from-slate-600 to-slate-700 text-white",
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

    companies_dict = {}
    total_docs = 0
    total_products = 0

    for entry in config_data:
        company = entry.get("company", "Inne")
        product = entry.get("product", "")
        product_key = f"{company}_{product}".strip("_")
        page_url = entry.get("url", "#")
        folder_id = entry.get("drive_folder_id", "").strip().split("?")[0]
        drive_url = f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else "#"

        raw_docs = hashes_data.get(product_key, {})
        if isinstance(raw_docs, dict):
            doc_count = len(raw_docs)
        elif isinstance(raw_docs, str):
            doc_count = 1
        else:
            doc_count = 0

        total_docs += doc_count
        total_products += 1

        if company not in companies_dict:
            companies_dict[company] = {
                "company": company,
                "company_display": format_company_name(company),
                "total_docs": 0,
                "products": []
            }

        companies_dict[company]["total_docs"] += doc_count
        companies_dict[company]["products"].append({
            "product": product,
            "product_key": product_key,
            "page_url": page_url,
            "drive_url": drive_url,
            "doc_count": doc_count
        })

    # Sortowanie ubezpieczycieli alfabetycznie
    sorted_companies = sorted(companies_dict.keys(), key=lambda c: c.lower())
    for comp in sorted_companies:
        companies_dict[comp]["products"].sort(key=lambda p: p["product"].lower())

    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Pre-renderowanie kart firm bezpośrednio w HTML
    cards_html_list = []
    pills_html_list = [
        f'<button data-company="all" class="company-pill whitespace-nowrap px-3 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 bg-blue-600 text-white shadow-sm shadow-blue-500/20">'
        f'<span>Wszystkie</span>'
        f'<span class="text-[10px] px-1.5 py-0.2 rounded-full bg-white/20 text-white">{len(sorted_companies)}</span>'
        f'</button>'
    ]

    for comp in sorted_companies:
        c_data = companies_dict[comp]
        gradient = COMPANY_GRADIENTS.get(comp, "from-slate-700 to-slate-800 text-white")
        prod_count = len(c_data["products"])
        comp_docs = c_data["total_docs"]

        # Pigułka filtru
        pills_html_list.append(
            f'<button data-company="{comp}" class="company-pill whitespace-nowrap px-3 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300">'
            f'<span>{c_data["company_display"]}</span>'
            f'<span class="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-400">{prod_count}</span>'
            f'</button>'
        )

        # Wiersze produktów
        rows = []
        for p in c_data["products"]:
            dot_color = "bg-emerald-500" if p["doc_count"] > 0 else "bg-amber-400"
            rows.append(f"""
            <div class="product-row flex items-center justify-between py-2 px-3 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/60 transition" data-product-name="{p['product'].lower()}">
              <div class="flex items-center gap-2.5 min-w-0">
                <span class="w-2 h-2 rounded-full {dot_color} flex-shrink-0"></span>
                <span class="font-semibold text-sm text-slate-800 dark:text-slate-200 truncate">{p['product']}</span>
                <span class="text-xs text-slate-500 dark:text-slate-400 font-medium">({p['doc_count']} OWU)</span>
              </div>
              <div class="flex items-center gap-1.5 flex-shrink-0">
                <a href="{p['drive_url']}" target="_blank" class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/50 hover:bg-blue-100 dark:hover:bg-blue-900/60 rounded-lg transition" title="Otwórz folder na Dysku Google">
                  <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/></svg>
                  <span>Dysk</span>
                </a>
                <a href="{p['page_url']}" target="_blank" class="p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition" title="Strona ubezpieczyciela">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                </a>
              </div>
            </div>
            """)

        rows_html = "\n".join(rows)

        card_html = f"""
        <div class="company-card bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-sm overflow-hidden flex flex-col justify-between hover:shadow-md transition" data-company-id="{comp}" data-company-name="{c_data['company_display'].lower()}">
          <div>
            <div class="bg-gradient-to-r {gradient} px-4 py-3 flex items-center justify-between">
              <h3 class="font-bold text-base tracking-tight">{c_data['company_display']}</h3>
              <div class="flex items-center gap-2 text-xs font-semibold">
                <span class="bg-black/20 px-2 py-0.5 rounded-lg">{prod_count} prod.</span>
                <span class="bg-white/20 px-2 py-0.5 rounded-lg">{comp_docs} plików OWU</span>
              </div>
            </div>
            <div class="p-3 divide-y divide-slate-100 dark:divide-slate-800/80 space-y-1">
              {rows_html}
            </div>
          </div>
        </div>
        """
        cards_html_list.append(card_html)

    all_cards_html = "\n".join(cards_html_list)
    all_pills_html = "\n".join(pills_html_list)

    html_content = f"""<!DOCTYPE html>
<html lang="pl" class="h-full">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OWU Sync Hub - Panel Towarzystw</title>
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
      width: 5px;
      height: 5px;
    }}
    .custom-scrollbar::-webkit-scrollbar-track {{
      background: transparent;
    }}
    .custom-scrollbar::-webkit-scrollbar-thumb {{
      background: rgba(156, 163, 175, 0.3);
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
                  Aktywny
                </span>
              </div>
              <p class="text-xs text-slate-500 dark:text-slate-400 hidden sm:block">Panel synchronizacji dokumentów z podziałem na towarzystwa ubezpieczeniowe</p>
            </div>
          </div>

          <div class="flex items-center gap-2 sm:gap-3">
            <button id="themeToggle" class="p-2 rounded-xl text-slate-500 hover:text-slate-700 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-800 transition" title="Zmień motyw">
              <svg id="sunIcon" class="w-5 h-5 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
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
      
      <!-- Statystyki KPI -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Towarzystwa</span>
          <p class="text-2xl sm:text-3xl font-extrabold mt-1 text-slate-900 dark:text-white">{len(sorted_companies)}</p>
          <span class="text-xs text-slate-500 dark:text-slate-400">Główne grupy</span>
        </div>

        <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Produkty</span>
          <p class="text-2xl sm:text-3xl font-extrabold mt-1 text-slate-900 dark:text-white">{total_products}</p>
          <span class="text-xs text-slate-500 dark:text-slate-400">Monitorowane linie</span>
        </div>

        <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Dokumenty OWU</span>
          <p class="text-2xl sm:text-3xl font-extrabold mt-1 text-slate-900 dark:text-white">{total_docs}</p>
          <span class="text-xs text-slate-500 dark:text-slate-400">Zsynchronizowane pliki</span>
        </div>

        <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Ostatni cykl</span>
          <p class="text-base sm:text-lg font-bold mt-2 text-slate-900 dark:text-white truncate">{gen_time}</p>
          <span class="text-xs text-slate-500 dark:text-slate-400">Automatyczny monitoring</span>
        </div>
      </div>

      <!-- Filtry i Wyszukiwarka -->
      <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 sm:p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm mb-6 space-y-3">
        <div class="relative">
          <div class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
            </svg>
          </div>
          <input type="text" id="searchInput" placeholder="Filtruj towarzystwo lub produkt (np. PZU, Warta, AC, Turysta)..." class="w-full pl-10 pr-10 py-2.5 bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition">
          <button id="clearSearch" class="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 hidden">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <!-- Przyciski Szybkiego Wyboru Towarzystwa -->
        <div id="companyPills" class="flex items-center gap-1.5 overflow-x-auto pb-1 custom-scrollbar text-xs">
          {all_pills_html}
        </div>
      </div>

      <!-- Kontener Pogrupowanych Towarzystw (Karty Ubezpieczycieli) -->
      <div id="companiesContainer" class="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {all_cards_html}
      </div>

      <!-- Komunikat braku wyników -->
      <div id="noResults" class="hidden text-center py-16">
        <div class="w-16 h-16 mx-auto mb-3 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-400">
          <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        </div>
        <h3 class="text-sm font-semibold text-slate-800 dark:text-slate-200">Nie znaleziono pasujących pozycji</h3>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">Zmień frazę wyszukiwania lub zresetuj filtr.</p>
      </div>

    </main>

    <!-- Stopka -->
    <footer class="mt-auto border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 py-5">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
        <div>OWU Sync System • GitHub Actions + Google Drive</div>
        <div>GitHub Pages: <span class="font-medium text-slate-700 dark:text-slate-300">https://basina194.github.io/OWU_SYNC/</span></div>
      </div>
    </footer>
  </div>

  <script>
    (function() {{
      try {{
        let currentCompany = 'all';
        let searchQuery = '';

        // Obsługa motywu
        const themeToggle = document.getElementById('themeToggle');
        const sunIcon = document.getElementById('sunIcon');
        const moonIcon = document.getElementById('moonIcon');

        function updateTheme(isDark) {{
          if (isDark) {{
            document.documentElement.classList.add('dark');
            if (sunIcon) sunIcon.classList.remove('hidden');
            if (moonIcon) moonIcon.classList.add('hidden');
            try {{ localStorage.setItem('theme', 'dark'); }} catch(e) {{}}
          }} else {{
            document.documentElement.classList.remove('dark');
            if (sunIcon) sunIcon.classList.add('hidden');
            if (moonIcon) moonIcon.classList.remove('hidden');
            try {{ localStorage.setItem('theme', 'light'); }} catch(e) {{}}
          }}
        }}

        let isDark = false;
        try {{
          const savedTheme = localStorage.getItem('theme');
          isDark = savedTheme === 'dark' || (!savedTheme && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
        }} catch(e) {{}}
        updateTheme(isDark);

        if (themeToggle) {{
          themeToggle.addEventListener('click', function() {{
            updateTheme(!document.documentElement.classList.contains('dark'));
          }});
        }}

        // Filtrowanie kart w czystym DOM (bez ryzyka błędów parsowania)
        const cards = Array.from(document.querySelectorAll('.company-card'));
        const pills = Array.from(document.querySelectorAll('.company-pill'));
        const searchInput = document.getElementById('searchInput');
        const clearSearch = document.getElementById('clearSearch');
        const noResults = document.getElementById('noResults');

        function applyFilters() {{
          let visibleCardsCount = 0;

          cards.forEach(function(card) {{
            const compId = card.getAttribute('data-company-id');
            const compName = card.getAttribute('data-company-name') || '';

            // Filtr towarzystwa
            const matchesCompany = (currentCompany === 'all' || compId === currentCompany);
            if (!matchesCompany) {{
              card.style.display = 'none';
              return;
            }}

            // Filtr wyszukiwarki po produktach wewnątrz firmy
            const rows = Array.from(card.querySelectorAll('.product-row'));
            let matchingRowsCount = 0;

            rows.forEach(function(row) {{
              const prodName = row.getAttribute('data-product-name') || '';
              const matchesSearch = !searchQuery || 
                                    compName.indexOf(searchQuery) !== -1 || 
                                    compId.toLowerCase().indexOf(searchQuery) !== -1 || 
                                    prodName.indexOf(searchQuery) !== -1;
              
              if (matchesSearch) {{
                row.style.display = 'flex';
                matchingRowsCount++;
              }} else {{
                row.style.display = 'none';
              }}
            }});

            if (matchingRowsCount > 0) {{
              card.style.display = 'flex';
              visibleCardsCount++;
            }} else {{
              card.style.display = 'none';
            }}
          }});

          if (noResults) {{
            if (visibleCardsCount === 0) {{
              noResults.classList.remove('hidden');
            }} else {{
              noResults.classList.add('hidden');
            }}
          }}
        }}

        // Obsługa pigułek towarzystw
        pills.forEach(function(btn) {{
          btn.addEventListener('click', function() {{
            currentCompany = btn.getAttribute('data-company');
            
            pills.forEach(function(p) {{
              const isSelected = p.getAttribute('data-company') === currentCompany;
              if (isSelected) {{
                p.className = 'company-pill whitespace-nowrap px-3 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 bg-blue-600 text-white shadow-sm shadow-blue-500/20';
                const counter = p.querySelector('span:last-child');
                if (counter) counter.className = 'text-[10px] px-1.5 py-0.2 rounded-full bg-white/20 text-white';
              }} else {{
                p.className = 'company-pill whitespace-nowrap px-3 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300';
                const counter = p.querySelector('span:last-child');
                if (counter) counter.className = 'text-[10px] px-1.5 py-0.2 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-400';
              }}
            }});

            applyFilters();
          }});
        }});

        // Obsługa pola wyszukiwania
        if (searchInput) {{
          searchInput.addEventListener('input', function(e) {{
            searchQuery = e.target.value.toLowerCase().trim();
            if (clearSearch) {{
              if (searchQuery.length > 0) clearSearch.classList.remove('hidden');
              else clearSearch.classList.add('hidden');
            }}
            applyFilters();
          }});
        }}

        if (clearSearch) {{
          clearSearch.addEventListener('click', function() {{
            if (searchInput) searchInput.value = '';
            searchQuery = '';
            clearSearch.classList.add('hidden');
            applyFilters();
          }});
        }}

        applyFilters();
      }} catch(err) {{
        console.error('Błąd inicjalizacji panelu:', err);
      }}
    }})();
  </script>
</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Pomyślnie wygenerowano plik {OUTPUT_HTML} (Towarzystwa: {len(sorted_companies)}, Produkty: {total_products}, Dokumenty: {total_docs})")

if __name__ == "__main__":
    generate()
