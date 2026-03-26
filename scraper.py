import cloudscraper
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import re

URL = "https://www.edel-optics.pl/ME3004D-5015-Moncler.html"
PRICE_FILE = "last_price.txt"

SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

def get_current_price():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    scraper = cloudscraper.create_scraper()
    response = scraper.get(URL, headers=headers)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Zamiast szukać najwyższej kwoty, szukamy tekstu "w tym VAT", 
    # który zawsze występuje z główną ceną na górze strony (i nie ma go przy wersjach niżej).
    vat_tags = soup.find_all(string=re.compile(r'w\s+tym\s+VAT', re.IGNORECASE))
    
    if not vat_tags:
        raise ValueError("Nie znaleziono napisu 'w tym VAT' na całej stronie. Prawdopodobna blokada bota lub duża zmiana strony.")
        
    # Bierzemy pierwszy blok z "w tym VAT" od góry (to zawsze główny produkt na stronie Edel-Optics)
    first_vat_tag = vat_tags[0]
    
    # Cofnijmy się o dwa poziomy do góry w kodzie HTML, aby złapać blok obejmujący i tekst "w tym VAT" i samą cenę
    price_block = first_vat_tag.parent.parent
    price_text = price_block.get_text(separator=' ', strip=True)
    
    match = re.search(r'([\d\s]+,\d+)', price_text.replace('\xa0', ' '))
    if match:
        clean_price_str = match.group(1).replace(' ', '')
        amount = float(clean_price_str.replace(',', '.'))
        return amount, price_text
        
    raise ValueError(f"Znaleziono sekcję 'w tym VAT', ale nie udało się wyciągnąć z niej cyfr: {price_text}")

def get_last_price():
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                try:
                    return float(content)
                except ValueError:
                    return None
    return None

def save_current_price(price):
    with open(PRICE_FILE, "w", encoding="utf-8") as f:
        f.write(str(price))

def send_email_notification(old_price, new_price, raw_price_text):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
        print("Brak konfiguracji e-mail. Pomięto wysyłanie wiadomości.")
        return

    subject = "ZMIANA CENY Okularów Moncler!"
    
    if old_price is None:
        body = f"Rozpoczęto śledzenie ceny.\nAktualna cena to: {raw_price_text}\nLink: {URL}"
    elif new_price < old_price:
        body = f"CENA SPADŁA!\nStara cena: {old_price} PLN\nNowa cena: {new_price} PLN\nLink: {URL}"
    else:
        body = f"CENA WZROSŁA!\nStara cena: {old_price} PLN\nNowa cena: {new_price} PLN\nLink: {URL}"

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("E-mail powiadomieniowy został wysłany.")
    except Exception as e:
        print(f"Błąd wysyłania: {e}")

def main():
    print("Pobieranie aktualnej ceny...")
    try:
        current_price, raw_price_text = get_current_price()
        print(f"Aktualna cena: {current_price} ({raw_price_text})")
        
        last_price = get_last_price()
        print(f"Ostatnia znana cena: {last_price}")
        
        if last_price is None:
            print("To pierwsze uruchomienie. Zapisuję cenę i wysyłam maila powitalnego.")
            send_email_notification(None, current_price, raw_price_text)
            save_current_price(current_price)
        elif current_price != last_price:
            print("Cena uległa zmianie! Wysyłam powiadomienie...")
            send_email_notification(last_price, current_price, raw_price_text)
            save_current_price(current_price)
        else:
            print("Brak zmian w cenie. Nie wysyłam powiadomienia.")
            
    except Exception as e:
        print(f"Wystąpił błąd: {e}")

if __name__ == "__main__":
    main()
