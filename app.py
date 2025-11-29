import sys
import time
import pandas as pd
from bs4 import BeautifulSoup
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                               QHeaderView, QTextEdit, QLabel, QMessageBox, QAbstractItemView)
from PySide6.QtCore import Qt, QThread, Signal
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
#my custom driver module
from seleniumDriver import create_driver


class ScraperWorker(QThread):
    data_ready = Signal(pd.DataFrame) 
    log_message = Signal(str)         
    error_occurred = Signal(str) 

    def __init__(self, driver):
        super().__init__()
        self.driver = driver
        self.category_url = None

    def run(self):
        try:
            # we are starting
            self.log_message.emit("Navigating to Passo homepage...")
            start_url = "https://www.passo.com.tr/tr"
            category_name = "Futbol"
            
            self.driver.get(start_url)
            wait = WebDriverWait(self.driver, 15)
            
            # Find the category button inside the navbar using XPath text matching
            xpath_query = f"//div[@id='navbar-content']//a[.//i[contains(text(), '{category_name}')]]"
            category_btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_query)))
            
            self.log_message.emit("Clicking on Football category...")
            self.driver.execute_script("arguments[0].click();", category_btn)
            
            # Wait for the URL to actually change so we know we moved pages
            wait.until(EC.url_changes(start_url))
            time.sleep(2) # A little safety buffer for elements to settle
            
            self.category_url = self.driver.current_url
            self.log_message.emit(f"Category Link: {self.category_url}")

            self.log_message.emit("Listing matches...")
            
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'r-event-item')))
            
            # Parse the current page content with BeautifulSoup for faster extraction
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            bs_events = soup.find_all('div', class_='r-event-item')

            match_list = []
            
            # Loop through all the event cards we found
            for index, event in enumerate(bs_events):
                title_div = event.find('div', class_='r-title')
                title = title_div.get_text(strip=True) if title_div else "No Title"

                date_span = event.find('span', class_='r-date')
                date = date_span.get_text(strip=True) if date_span else "No Date"

                location_span = event.find('span', class_='r-location')
                location = location_span.get_text(strip=True) if location_span else "No Location"

                match_list.append({
                    'index': index,
                    'title': title,
                    'date': date,
                    'location': location
                })

            # Convert to DataFrame and send it back to the main UI
            df = pd.DataFrame(match_list)
            self.data_ready.emit(df)
            self.log_message.emit("List fetched successfully.")

        except Exception as e:
            self.error_occurred.emit(str(e))

class DetailWorker(QThread):
    details_ready = Signal(dict)
    log_message = Signal(str)
    
    def __init__(self, driver, url, index):
        super().__init__()
        self.driver = driver
        self.url = url
        self.index = index

    def run(self):
        try:
            self.log_message.emit(f"Fetching details for match at index {self.index}...")
            self.driver.get(self.url)
            wait = WebDriverWait(self.driver, 10)
            
            # Wait for the main list elements to load
            wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'r-event-item')))
            cards = self.driver.find_elements(By.CLASS_NAME, 'r-event-item')
            
            if self.index >= len(cards):
                self.log_message.emit("Error: Match index not found.")
                return

            target_card = cards[self.index]
            # Scroll to the element to ensure it's clickable
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_card)
            time.sleep(1)

            main_window = self.driver.current_window_handle
            
            # Click the detail button (overlay)
            detail_btn = target_card.find_element(By.CLASS_NAME, "overlay-text-container")
            self.driver.execute_script("arguments[0].click();", detail_btn)
            
            # Wait for the new tab/window to open
            wait.until(lambda d: len(d.window_handles) > 1)
            windows = self.driver.window_handles
            
            # Switch focus to the newly opened tab
            self.driver.switch_to.window(windows[-1])
            
            # Wait for the ticket info box to appear in the DOM
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'box')))
            
            # Logic to click "Show All Categories"
            try:
                # Search for the span containing the Turkish text "Tüm kategorileri göster"
                # Note: This text must remain in Turkish to match the website content.
                expand_xpath = "//span[contains(text(), 'Tüm kategorileri göster')]"
                
                expand_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, expand_xpath))
                )
                
                self.log_message.emit("Expand button found. Clicking...")
                self.driver.execute_script("arguments[0].click();", expand_btn)
                
                time.sleep(1.5)
                
            except Exception:
                self.log_message.emit("Expand button not found or list already full.")

            # Parse HTML content using BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            sidebar_div = soup.select_one('div.col-md-4.ticket-info')
            
            match_data = {"date": "N/A", "venue": "N/A", "categories": []}

            if sidebar_div:
                # Extract Date info
                date_el = sidebar_div.select_one('.box.first ul li')
                if date_el: match_data["date"] = date_el.get_text(strip=True)
                
                # Extract Venue info
                venue_el = sidebar_div.select_one('.text-primary')
                if venue_el: match_data["venue"] = venue_el.get_text(strip=True)
                
                # Extract Categories
                # Find the icon, then move up to the parent box container
                category_icon = sidebar_div.select_one('.passo-icon-hastag')
                if category_icon:
                    cat_box = category_icon.find_parent('div', class_='box')
                    if cat_box:
                        items = cat_box.select('ul li')
                        for item in items:
                            txt = item.get_text(strip=True)
                            if "Tüm kategorileri" not in txt and "Gizle" not in txt:
                                match_data["categories"].append(txt)
            
            # Close the detail tab and switch back to the main list
            self.driver.close() 
            self.driver.switch_to.window(main_window)
            
            self.details_ready.emit(match_data)
            self.log_message.emit("Details acquired.")

        except Exception as e:
            self.log_message.emit(f"Error: {e}")
            if len(self.driver.window_handles) > 1:
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])

# --- (GUI Implementation) ---

class PassoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Passo Match Bot v1.0")
        self.setGeometry(100, 100, 900, 600)
        
        # Initialize the Selenium driver
        self.driver = create_driver()
        self.current_list_url = None
        
        self.init_ui()
        
        # Simple dark mode styling
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QLabel { color: #ffffff; font-size: 14px; font-weight: bold; }
            QPushButton { 
                background-color: #0078d7; color: white; border-radius: 5px; 
                padding: 10px; font-size: 13px; 
            }
            QPushButton:hover { background-color: #005a9e; }
            QPushButton:disabled { background-color: #555; }
            QTableWidget { background-color: #333; color: white; gridline-color: #444; }
            QHeaderView::section { background-color: #444; color: white; padding: 4px; }
            QTextEdit { background-color: #333; color: #00ff00; font-family: Consolas; }
        """)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # --- Top Panel ---
        top_layout = QHBoxLayout()
        self.btn_fetch_list = QPushButton("⚽ Fetch Match List")
        self.btn_fetch_list.clicked.connect(self.start_list_fetch)
        top_layout.addWidget(self.btn_fetch_list)
        
        self.lbl_status = QLabel("Ready")
        top_layout.addWidget(self.lbl_status)
        layout.addLayout(top_layout)

        # --- Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Index", "Event Name", "Date", "Location"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Stretch title column
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows) # Select full row
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers) # Make read-only
        layout.addWidget(self.table)

        # --- Detail Button ---
        self.btn_get_details = QPushButton("🔍 Get Details for Selected Match")
        self.btn_get_details.clicked.connect(self.start_detail_fetch)
        self.btn_get_details.setEnabled(False) # Disabled until list is fetched
        layout.addWidget(self.btn_get_details)

        # --- Details Display Area ---
        self.txt_details = QTextEdit()
        self.txt_details.setReadOnly(True)
        self.txt_details.setPlaceholderText("Details will appear here...")
        self.txt_details.setMaximumHeight(150)
        layout.addWidget(self.txt_details)

    # --- LISTING OPERATIONS ---
    def start_list_fetch(self):
        # Disable button to prevent double clicking
        self.btn_fetch_list.setEnabled(False)
        self.table.setRowCount(0)
        self.txt_details.clear()
        
        self.worker_list = ScraperWorker(self.driver)
        self.worker_list.log_message.connect(self.update_status)
        self.worker_list.data_ready.connect(self.populate_table)
        self.worker_list.error_occurred.connect(self.show_error)
        
        # Re-enable button when done
        self.worker_list.finished.connect(lambda: self.btn_fetch_list.setEnabled(True))
        
        self.worker_list.start()

    def populate_table(self, df):
        self.table.setRowCount(len(df))
        # Save the URL so the detail worker knows where to go back to
        self.current_list_url = self.worker_list.category_url 
        
        for row_idx, row_data in df.iterrows():
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(row_data['index'])))
            self.table.setItem(row_idx, 1, QTableWidgetItem(row_data['title']))
            self.table.setItem(row_idx, 2, QTableWidgetItem(row_data['date']))
            self.table.setItem(row_idx, 3, QTableWidgetItem(row_data['location']))
        
        # Now we can allow detail fetching
        self.btn_get_details.setEnabled(True)

    # --- DETAIL OPERATIONS ---
    def start_detail_fetch(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a match from the list!")
            return

        # Get data from the selected row (Index is in column 0)
        row = self.table.currentRow()
        match_index = int(self.table.item(row, 0).text())
        match_name = self.table.item(row, 1).text()
        
        self.update_status(f"Fetching details for {match_name}...")
        self.txt_details.setText("Loading...")
        self.btn_get_details.setEnabled(False)

        self.worker_detail = DetailWorker(self.driver, self.current_list_url, match_index)
        self.worker_detail.log_message.connect(self.update_status)
        self.worker_detail.details_ready.connect(self.show_details)
        self.worker_detail.finished.connect(lambda: self.btn_get_details.setEnabled(True))
        
        self.worker_detail.start()

    def show_details(self, data):
        text = f"📅 DATE: {data['date']}\n"
        text += f"📍 VENUE: {data['venue']}\n"
        text += "-" * 30 + "\n"
        text += "🎟️ CATEGORIES:\n"
        for cat in data['categories']:
            text += f"  • {cat}\n"
        
        self.txt_details.setText(text)

    # --- HELPER METHODS ---
    def update_status(self, msg):
        self.lbl_status.setText(msg)

    def show_error(self, err):
        QMessageBox.critical(self, "Error", f"An error occurred:\n{err}")

    def closeEvent(self, event):
        if self.driver:
            self.driver.quit()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PassoApp()
    window.show()
    sys.exit(app.exec())
