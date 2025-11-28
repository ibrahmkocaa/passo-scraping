from seleniumDriver import create_driver
import time
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd

driver = create_driver()

def get_category_url(start_url="https://www.passo.com.tr/tr", category_name="Futbol"):
    print(f"--- {start_url} adresine gidiliyor ---")
    driver.get(start_url)
    wait = WebDriverWait(driver, 15)

    try:
        xpath_query = f"//div[@id='navbar-content']//a[.//i[contains(text(), '{category_name}')]]"
        category_btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_query)))
        
        print(f"--- {category_name} menüsüne tıklanıyor ---")
        driver.execute_script("arguments[0].click();", category_btn)
        
        wait.until(EC.url_changes(start_url))
        time.sleep(2) 
        
        current_url = driver.current_url
        print(f"--- Güncel Link Alındı: {current_url} ---")
        return current_url

    except Exception as e:
        print(f"Kategoriye giderken hata oluştu: {e}")
        return None

def get_match_list(kategori_url):
    print("--- Maç listesi çekiliyor... ---")
    driver.get(kategori_url)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'r-event-item')))
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    bs_events = soup.find_all('div', class_='r-event-item')

    match_list = []

    for index, event in enumerate(bs_events, start=0):
        title_div = event.find('div', class_='r-title')
        title = title_div.get_text(strip=True) if title_div else "Başlık yok"

        date_span = event.find('span', class_='r-date')
        date = date_span.get_text(strip=True) if date_span else "Tarih yok"

        location_span = event.find('span', class_='r-location')
        location = location_span.get_text(strip=True) if location_span else "Konum yok"

        match_list.append({
            'index': index,
            'title': title,
            'date': date,
            'location': location
        })
    
    return pd.DataFrame(match_list)

def get_match_details(kategori_url, match_index):
    print(f"--- {match_index}. indexteki maçın detaylarına gidiliyor... ---")
    driver.get(kategori_url)
    wait = WebDriverWait(driver, 10)
    
    wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'r-event-item')))

    cards = driver.find_elements(By.CLASS_NAME, 'r-event-item')
    if match_index >= len(cards):
        return None
        
    target_card = cards[match_index]
    
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_card)
    time.sleep(1) 

    main_window = driver.current_window_handle

    try:
        detay_butonu = target_card.find_element(By.CLASS_NAME, "overlay-text-container")
        driver.execute_script("arguments[0].click();", detay_butonu)
        
        wait.until(lambda d: len(d.window_handles) > 1)
        windows = driver.window_handles
        driver.switch_to.window(windows[-1])
        
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'box')))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        sidebar_div = soup.select_one('div.col-md-4.ticket-info')

        match_data = {
            "tarih": None,
            "mekan": None,
            "kategoriler": []
        }

        if sidebar_div:
            date_element = sidebar_div.select_one('.box.first ul li')
            if date_element:
                match_data["tarih"] = date_element.get_text(strip=True)

            venue_element = sidebar_div.select_one('.text-primary')
            if venue_element:
                match_data["mekan"] = venue_element.get_text(strip=True)

            category_icon = sidebar_div.select_one('.passo-icon-hastag')
            if category_icon:
                category_box = category_icon.find_parent('div', class_='box')
                if category_box:
                    items = category_box.select('ul li')
                    for item in items:
                        text = item.get_text(strip=True)
                        if text and "Tüm kategorileri" not in text:
                            match_data["kategoriler"].append(text)
            
        driver.close()
        driver.switch_to.window(main_window)
        
        return match_data

    except Exception as e:
        print(f"Hata: {e}")
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(main_window)
        return None


dynamic_url = get_category_url()

if dynamic_url:
    df_matches = get_match_list(dynamic_url)
    print("\n--- MAÇ LİSTESİ ---")
    print(df_matches)
    print("-" * 30)

    target_index = 1
    if not df_matches.empty and len(df_matches) > target_index:
        secilen_mac = df_matches.iloc[target_index]['title']
        print(f"Seçilen Maç: {secilen_mac} (Index: {target_index})")
        
        match_info = get_match_details(dynamic_url, target_index)
        print("\n--- MAÇ DETAYLARI ---")
        print(match_info)
    else:
        print(f"Listede {target_index} numaralı index bulunamadı.")
else:
    print("Link alınamadığı için işlem yapılamadı.")

driver.quit()