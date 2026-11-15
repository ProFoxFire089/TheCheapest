@app.route('/api/search')
def search():
    visitor_id, is_new = get_or_assign_visitor_id()
    query = request.args.get('query', '').strip()
    raw_min_price = request.args.get('min_price', '0').strip()

    try:
        min_price = int(raw_min_price) if raw_min_price.isdigit() else 0
    except ValueError:
        min_price = 0

    if not query:
        return jsonify([])

    log_search_activity(visitor_id, query, min_price)

    deals = []
    deals.extend(get_local_deals(query, min_price))

    encoded_query = urllib.parse.quote(query)
    amazon_url = f"https://www.amazon.ae/s?k={encoded_query}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-AE,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.amazon.ae/",
        "Upgrade-Insecure-Requests": "1"
    }

    # Words that ONLY indicate a standalone accessory (safe to always block)
    STRICT_ACCESSORY_PHRASES = [
        'compatible with', 'designed for', 'suitable for', 'fits ',
        'replacement ear', 'ear pads', 'earpads', 'ear cushions',
        'headband cover', 'protective case', 'carrying case for',
        'silicone cover', 'tempered glass', 'screen protector'
    ]

    try:
        response = requests.get(amazon_url, headers=headers, timeout=10)
        print(f"Search '{query}' -> Amazon HTTP {response.status_code} (len={len(response.text)})")

        if "api-services-support@amazon.com" in response.text or "Type the characters you see" in response.text:
            print("WARNING: Amazon served a CAPTCHA page to Render IP.")

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('div[data-component-type="s-search-result"]')
            print(f"Found {len(items)} raw product cards for '{query}'")

            for item in items:
                try:
                    title_el = item.select_one('h2 a span') or item.select_one('h2 span')
                    price_el = item.select_one('.a-price-whole') or item.select_one('.a-price .a-offscreen')
                    link_el = item.select_one('h2 a.a-link-normal') or item.select_one('a.a-link-normal')
                    img_el = item.select_one('img.s-image')

                    if title_el and price_el:
                        title = title_el.get_text().strip()
                        title_lower = title.lower()

                        # Block standalone accessories without blocking real headphones that include a cable/pouch
                        if any(phrase in title_lower for phrase in STRICT_ACCESSORY_PHRASES):
                            continue
                        if title_lower.startswith(('case ', 'cover ', 'replacement ', 'earpad', 'cable ', 'charger ')):
                            continue

                        price_raw = price_el.get_text().replace(',', '').replace('.', '').replace('AED', '').strip()
                        digits = ''.join(filter(str.isdigit, price_raw))
                        if not digits:
                            continue
                        price = int(digits)

                        if min_price > 0 and price < min_price:
                            continue

                        href = link_el.get('href', '') if link_el else ''
                        if href.startswith('/'):
                            link = f"https://www.amazon.ae{href}"
                        elif href.startswith('http'):
                            link = href
                        else:
                            link = amazon_url

                        img_src = img_el.get('src', '') if img_el else ''

                        deals.append({
                            "title": title,
                            "price": price,
                            "store": "Amazon UAE",
                            "link": link,
                            "image": img_src
                        })
                except Exception:
                    continue
    except Exception as e:
        print(f"Scraping error: {e}")

    unique_deals = {d['title']: d for d in deals if d['title']}.values()
    sorted_deals = sorted(list(unique_deals), key=lambda x: x['price'])

    res = make_response(jsonify(sorted_deals[:20]))
    if is_new:
        res.set_cookie('visitor_id', visitor_id, max_age=31536000)
    return res
