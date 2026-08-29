import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# Words that indicate an item is an accessory, part, or book
EXCLUDE_KEYWORDS = [
    'case', 'cover', 'protector', 'glass', 'book', 'guide', 'film', 
    'pouch', 'skin', 'strap', 'cable', 'charger', 'adapter', 'holder', 
    'stand', 'lens', 'tempered', 'silicone', 'shell', 'sleeve',
    'wallet', 'mount', 'panel', 'housing', 'tpu', 'replacement', 
    'screen', 'display', 'camera', 'armour', 'armor', 'buds', 'earbuds',
    'back cover', 'privacy', 'card holder', 'stylus', 'pen', 'battery'
]

def init_driver():
    """Initializes a headless Chrome browser session."""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def is_valid_product(title, price, min_price=200):
    """Filters out non-phone items and cheap accessories."""
    title_lower = title.lower()
    
    # 1. Reject if title matches any exclusion keyword
    if any(keyword in title_lower for keyword in EXCLUDE_KEYWORDS):
        return False
        
    # 2. Reject if price is below minimum threshold (e.g. 200 AED)
    if price < min_price:
        return False
        
    return True


def scrape_amazon_uae(query, min_price=200):
    """Scrapes Amazon UAE for matching products."""
    driver = init_driver()
    results = []
    
    try:
        refined_query = f"{query} phone" if len(query.split()) == 1 else query
        search_url = f"https://www.amazon.ae/s?k={refined_query.replace(' ', '+')}&i=mobile"
        driver.get(search_url)
        
        items = driver.find_elements(By.CSS_SELECTOR, 'div[data-component-type="s-search-result"]')
        
        for item in items:
            try:
                title_elem = item.find_element(By.CSS_SELECTOR, 'h2 span')
                title = title_elem.text.strip()
                
                price_whole = item.find_element(By.CSS_SELECTOR, 'span.a-price-whole').text.replace(',', '').strip()
                price = float(re.sub(r'[^\d.]', '', price_whole))
                
                link_elem = item.find_element(By.CSS_SELECTOR, 'h2 a')
                link = link_elem.get_attribute('href')
                
                img_elem = item.find_element(By.CSS_SELECTOR, 'img.s-image')
                image_url = img_elem.get_attribute('src')

                if is_valid_product(title, price, min_price=min_price):
                    results.append({
                        'title': title,
                        'price': price,
                        'link': link,
                        'image': image_url,
                        'store': 'Amazon UAE'
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"Amazon Selenium notice: {e}")
    finally:
        driver.quit()
        
    return results


def scrape_noon(query, min_price=200):
    """Placeholder for Noon scraper with error handling."""
    try:
        # If you have Noon scraping logic, place it here and pass results through is_valid_product()
        return []
    except Exception as e:
        print(f"Noon Selenium notice: {e}")
        return []


def scrape_dubizzle(query, min_price=200):
    """Placeholder for Dubizzle scraper with error handling."""
    try:
        # If you have Dubizzle scraping logic, place it here and pass results through is_valid_product()
        return []
    except Exception as e:
        print(f"Dubizzle Selenium notice: {e}")
        return []


def search_all(query):
    """Runs all scrapers, aggregates valid results, and sorts by price."""
    all_deals = []
    
    # Gather results from all active scrapers
    all_deals.extend(scrape_amazon_uae(query))
    all_deals.extend(scrape_noon(query))
    all_deals.extend(scrape_dubizzle(query))
    
    # Sort cheapest to highest price
    all_deals.sort(key=lambda x: x['price'])
    return all_deals