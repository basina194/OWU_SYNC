"""
Skrypt do wygenerowania nowego token.json dla Google Drive.
Otworzy okno w domyślnej przeglądarce, aby zalogować się na konto Google.
Po udanej autoryzacji plik token.json zostanie zaktualizowany.
"""
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"

def main():
    if not os.path.exists(CLIENT_SECRET_FILE):
        print(f"BŁĄD: Nie znaleziono pliku {CLIENT_SECRET_FILE} w bieżącym katalogu.")
        return

    print("Uruchamiam proces autoryzacji Google OAuth...")
    print("Zaraz otworzy się okno przeglądarki. Zaloguj się i kliknij 'Zezwól' (oraz Zaawansowane -> Przejdź dalej, jeśli pojawi się ostrzeżenie).")
    
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print("\nSUKCES! Nowy plik token.json został pomyślnie utworzony i zapisany.")
    print("Zawartość token.json została odświeżona.")

if __name__ == "__main__":
    main()
