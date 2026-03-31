import cloudscraper
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import re
import json

DATA_FILE = "data.json"

EDEL_OPTICS_URLS = {
    "Moncler (ME3004D-5015)": "https://www.edel-optics.pl/ME3004D-5015-Moncler.html",
    "Mont Blanc (MB0315OA-002)": "https://www.edel-optics.pl/MB0315OA-002-Mont-Blanc.html"
}

DROPBOX_URL = "https://www.dropbox.com/scl/fi/zrire9bkugmbdbiln92mi/EP_wyniki_20260325_publ.xlsx?rlkey=pc4z21c2qsv8zkz9oyx85unv9&e=3&dl=0"

SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

def get_edel_optics_price(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    vat_tags = soup.find_all(string=re.compile(r'w\s+tym\s+VAT', re.IGNORECASE))
    if not vat_tags:
        raise ValueError(f"Nie znaleziono napisu 'w tym VAT' na calej stronie.")
        
    first_vat_tag = vat_tags[0]
    price_block = first_vat_tag.parent.parent
    price_text = price_block.get_text(separator=' ', strip=True)
    
    matches = re.findall(r'([\d\s]+,\d+)', price_text.replace('\xa0', ' '))
    if matches:
        clean_price_str = matches[-1].replace(' ', '')
        amount = float(clean_price_str.replace(',', '.'))
        return amount
        
    raise ValueError(f"Nie udalo sie wyciagnac cyfr ze stringa: {price_text}")

def get_dropbox_date():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    scraper = cloudscraper.create_scraper()
    response = scraper.get(DROPBOX_URL, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    label = soup.find(string=re.compile("Data modyfikacji", re.IGNORECASE))
    if label:
        row = label.find_parent(attrs={"role": "row"})
        if row:
            cell = row.find(attrs={"role": "cell"})
            if cell:
                return cell.get_text(strip=True)
                
    match = re.search(r'(\d{2}\.\d{2}\.\d{4},\s*\d{2}:\d{2})', response.text)
    if match:
        return match.group(1)
        
    raise ValueError("Nie znaleziono etykiety 'Data modyfikacji' na Dropboxie.")

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_email_notification(changes):
    if not changes:
        return
        
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
        print("Brak konfiguracji e-mail.")
        return

    subject = "AKTUALIZACJA: Powiadamiator zglasza zmiany!"
    body = "Oto podsumowanie najnowszych zmian:\n\n"
    for change in changes:
        body += f"🔹 {change}\n\n"

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("E-mail wyslany.")
    except Exception as e:
        print(f"Blad wysylania: {e}")

def main():
    old_data = load_data()
    new_data = dict(old_data)
    changes = []
    
    for name, url in EDEL_OPTICS_URLS.items():
        print(f"Sprawdzanie: {name}...")
        try:
            current_price = get_edel_optics_price(url)
            print(f"  Znaleziono: {current_price} PLN")
            last_price = old_data.get(name)
            
            if last_price is None:
                changes.append(f"Rozpoczęto śledzenie {name}. Aktywna cena to: {current_price} PLN\nLink: {url}")
                new_data[name] = current_price
            elif current_price != last_price:
                diff_percent = abs(current_price - last_price) / last_price * 100
                if diff_percent >= 1.0:
                    kierunek = "SPADŁA" if current_price < last_price else "WZROSŁA"
                    changes.append(f"CENA {kierunek} ({name})!\nPoprzednia: {last_price} PLN\nNowa: {current_price} PLN\nLink: {url}")
                    new_data[name] = current_price
                else:
                    print(f"  Zmiana o {diff_percent:.2f}% zignorowana (<1%).")
                    new_data[name] = current_price
            else:
                print(f"  Brak zmian dla {name}.")
        except Exception as e:
            print(f"  Blad ({name}): {e}")

    print("Sprawdzanie: Dropbox...")
    try:
        current_date = get_dropbox_date()
        print(f"  Data na chmurze: {current_date}")
        last_date = old_data.get("DropboxExcel")
        
        if last_date is None:
            changes.append(f"Rozpoczęto śledzenie pliku. Data modyfikacji: {current_date}\nLink: {DROPBOX_URL}")
            new_data["DropboxExcel"] = current_date
        elif current_date != last_date:
            changes.append(f"ZAKTUALIZOWANO PLIK! Nowa data: {current_date} (Zastępuje: {last_date})\nLink: {DROPBOX_URL}")
            new_data["DropboxExcel"] = current_date
        else:
            print("  Brak nowosci.")
    except Exception as e:
        print(f"  Blad Dropbox: {e}")

    if changes:
        print("Wysylam maila...")
        send_email_notification(changes)
        save_data(new_data)
    else:
        print("Brak zmian do wyslania. Koniec.")

if __name__ == "__main__":
    main()
