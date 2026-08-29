from flask import Flask, jsonify, request, send_from_directory, make_response, render_template_string
from playwright.sync_api import sync_playwright
import urllib.parse
import json
import os
from datetime import datetime

app = Flask(__name__, static_folder='.', static_url_path='')

# Admin password to view visitor logs
ADMIN_PASSWORD = "admin"

# Isolated storage folder outside public static path
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'admin_data')
os.makedirs(DATA_DIR, exist_ok=True)
ANALYTICS_FILE = os.path.join(DATA_DIR, 'analytics.json')
VISITORS_FILE = os.path.join(DATA_DIR, 'visitors.json')

EXCLUDED_KEYWORDS = [
    'case', 'cover', 'protector', 'glass', 'film', 'shield', 
    'strap', 'holder', 'stand', 'cable', 'charger', 'skin', 
    'lens', 'armour', 'armor', 'sleeve', 'pouch',
    'tip', 'tips', 'hook', 'hooks', 'cap', 'caps', 'foam',
    'replacement', 'cleaning', 'cleaner', 'pen', 'lanyard',
    'attachment', 'accessory', 'accessories', 'pad', 'pads',
    'cushion', 'cushions', 'earpiece', 'shell', 'band', 'bands',
    'mount', 'dock', 'organizer', 'dust', 'plug', 'keychain',
    'compatible with', 'designed for', 'suitable for', 'fits '
]

def get_or_assign_visitor_id():
    """Reads or generates a sequential visitor ID (person_1, person_2, etc.)"""
    visitor_id = request.cookies.get('visitor_id')
    is_new = False

    if not visitor_id:
        is_new = True
        visitors = {}
        if os.path.exists(VISITORS_FILE):
            try:
                with open(VISITORS_FILE, 'r', encoding='utf-8') as f:
                    visitors = json.load(f)
            except Exception:
                visitors = {}

        next_index = len(visitors) + 1
        visitor_id = f"person_{next_index}"
        visitors[visitor_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            with open(VISITORS_FILE, 'w', encoding='utf-8') as f:
                json.dump(visitors, f, indent=2)
        except Exception as e:
            print(f"Error updating visitors file: {e}")

    return visitor_id, is_new


def log_search_activity(visitor_id, query, min_price):
    """Saves search activity in admin_data/analytics.json"""
    logs = []
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except Exception:
            logs = []

    logs.append({
        "visitor_id": visitor_id,
        "query": query,
        "min_price": min_price,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    try:
        with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"Error saving analytics: {e}")


def get_local_deals(query, min_price):
    """Loads manual local deals from local_deals.json using absolute path."""
    local_results = []
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_deals.json')
    
    if not os.path.exists(file_path):
        return local_results

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            local_data = json.load(f)

        query_words = query.lower().split()
        for item in local_data:
            title = item.get('title', '')
            title_lower = title.lower()
            price = item.get('price', 0)

            matches = all(word in title_lower for word in query_words)

            if matches and price >= min_price:
                local_results.append({
                    "title": title,
                    "price": price,
                    "store": item.get('store', 'Local Shop'),
                    "link": item.get('link', '#'),
                    "image": item.get('image', 'https://via.placeholder.com/80')
                })
    except Exception as e:
        print(f"Error reading local_deals.json: {e}")

    return local_results


@app.route('/')
def index():
    visitor_id, is_new = get_or_assign_visitor_id()
    response = make_response(send_from_directory('.', 'index.html'))
    if is_new:
        response.set_cookie('visitor_id', visitor_id, max_age=31536000)
    return response


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

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            page = context.new_page()
            page.goto(amazon_url, timeout=30000, wait_until="domcontentloaded")
            
            page.wait_for_selector('div[data-component-type="s-search-result"]', timeout=8000)
            items = page.query_selector_all('div[data-component-type="s-search-result"]')

            for item in items:
                try:
                    title_el = item.query_selector('h2 a span') or item.query_selector('h2 span')
                    price_el = item.query_selector('.a-price-whole') or item.query_selector('.a-price .a-offscreen')
                    link_el = item.query_selector('h2 a.a-link-normal') or item.query_selector('a.a-link-normal')
                    img_el = item.query_selector('img.s-image')

                    if title_el and price_el:
                        title = title_el.inner_text().strip()

                        if any(kw in title.lower() for kw in EXCLUDED_KEYWORDS):
                            continue

                        price_raw = price_el.inner_text().replace(',', '').replace('.', '').replace('AED', '').strip()
                        digits = ''.join(filter(str.isdigit, price_raw))
                        if not digits:
                            continue
                        price = int(digits)

                        if min_price > 0 and price < min_price:
                            continue

                        href = link_el.get_attribute('href') if link_el else ''
                        if href.startswith('/'):
                            link = f"https://www.amazon.ae{href}"
                        elif href.startswith('http'):
                            link = href
                        else:
                            link = amazon_url

                        img_src = img_el.get_attribute('src') if img_el else ''

                        deals.append({
                            "title": title,
                            "price": price,
                            "store": "Amazon UAE",
                            "link": link,
                            "image": img_src
                        })
                except Exception:
                    continue

            browser.close()
    except Exception as e:
        print(f"Scraping error: {e}")

    unique_deals = {d['title']: d for d in deals if d['title']}.values()
    sorted_deals = sorted(list(unique_deals), key=lambda x: x['price'])

    res = make_response(jsonify(sorted_deals[:20]))
    if is_new:
        res.set_cookie('visitor_id', visitor_id, max_age=31536000)
    return res


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    auth_pwd = request.args.get('password') or request.form.get('password')
    
    if auth_pwd != ADMIN_PASSWORD:
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head><title>Admin Login</title></head>
            <body style="background:#0b1120; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;">
                <h2>🔒 Private Analytics Dashboard</h2>
                <form method="POST" style="margin-top:20px;">
                    <input type="password" name="password" placeholder="Enter Admin Password" style="padding:10px; border-radius:6px; border:1px solid #334155; width:220px;" required />
                    <button type="submit" style="padding:10px 18px; background:#10b981; border:none; color:#022c22; font-weight:bold; border-radius:6px; cursor:pointer;">Login</button>
                </form>
            </body>
            </html>
        '''), 401

    logs = []
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except Exception:
            logs = []

    visitors_raw = {}
    if os.path.exists(VISITORS_FILE):
        try:
            with open(VISITORS_FILE, 'r', encoding='utf-8') as f:
                visitors_raw = json.load(f)
        except Exception:
            visitors_raw = {}

    visitor_history = {}
    for log in logs:
        vid = log.get('visitor_id')
        if vid not in visitor_history:
            visitor_history[vid] = []
        visitor_history[vid].append(log)

    visitor_list = []
    for vid, registered_time in visitors_raw.items():
        v_logs = visitor_history.get(vid, [])
        visitor_list.append({
            "id": vid,
            "registered_at": registered_time,
            "visit_count": len(v_logs),
            "logs": v_logs
        })

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Visitor Analytics Dashboard</title>
            <style>
                body { background: #0b1120; color: #fff; font-family: system-ui, -apple-system, sans-serif; padding: 30px; }
                h1 { color: #10b981; margin-bottom: 20px; }
                .table-card { background: #151d30; border: 1px solid #222f47; border-radius: 12px; overflow: hidden; }
                table { width: 100%; border-collapse: collapse; text-align: left; }
                th { background: #1e293b; color: #94a3b8; font-size: 14px; padding: 14px 16px; border-bottom: 1px solid #222f47; }
                td { padding: 14px 16px; border-bottom: 1px solid #222f47; font-size: 15px; }
                .visitor-tag { background: #1e293b; color: #ffffff; padding: 4px 10px; border-radius: 6px; font-weight: bold; }
                .visits-link { color: #38bdf8; font-weight: bold; text-decoration: underline; cursor: pointer; }
                .visits-link:hover { color: #60a5fa; }
                .details-row { display: none; background: #0f172a; }
                .details-box { padding: 16px; background: #090d16; border-radius: 8px; margin: 10px 0; border: 1px solid #1e293b; }
                .sub-table { width: 100%; margin: 0; }
                .sub-table th { background: transparent; color: #64748b; font-size: 12px; border-bottom: 1px solid #1e293b; }
                .sub-table td { font-size: 14px; border-bottom: 1px solid #151d30; padding: 8px 12px; }
            </style>
            <script>
                function toggleVisits(id) {
                    var el = document.getElementById(id);
                    if (el.style.display === "none" || el.style.display === "") {
                        el.style.display = "table-row";
                    } else {
                        el.style.display = "none";
                    }
                }
            </script>
        </head>
        <body>
            <h1>📊 Registered Visitor Log</h1>

            <div class="table-card">
                <table>
                    <thead>
                        <tr>
                            <th>Visitor ID</th>
                            <th>Registered Timestamp</th>
                            <th>Total Visits</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for visitor in visitor_list %}
                        <tr>
                            <td><span class="visitor-tag">{{ visitor.id }}</span></td>
                            <td style="color: #94a3b8;">{{ visitor.registered_at }}</td>
                            <td>
                                <span class="visits-link" onclick="toggleVisits('details-{{ visitor.id }}')">
                                    {{ visitor.id }} &nbsp;(Visits-{{ visitor.visit_count }})
                                </span>
                            </td>
                        </tr>
                        <tr id="details-{{ visitor.id }}" class="details-row">
                            <td colspan="3">
                                <div class="details-box">
                                    <table class="sub-table">
                                        <thead>
                                            <tr>
                                                <th>Visit #</th>
                                                <th>Search Query</th>
                                                <th>Min AED Filter</th>
                                                <th>Timestamp</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {% if visitor.logs %}
                                                {% for log in visitor.logs %}
                                                <tr>
                                                    <td style="color: #38bdf8; font-weight: bold;">visit{{ loop.index }}</td>
                                                    <td style="color: #10b981; font-weight: bold;">{{ log.query }}</td>
                                                    <td style="color: #cbd5e1;">{{ log.min_price }} AED</td>
                                                    <td style="color: #94a3b8;">{{ log.timestamp }}</td>
                                                </tr>
                                                {% endfor %}
                                            {% else %}
                                                <tr>
                                                    <td colspan="4" style="color: #64748b; text-align: center; padding: 12px;">No search activity logged yet for this visitor.</td>
                                                </tr>
                                            {% endif %}
                                        </tbody>
                                    </table>
                                </div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </body>
        </html>
    ''', visitor_list=visitor_list)


@app.route('/api/add-local-deal', methods=['POST'])
def add_local_deal():
    data = request.json
    if not data or not data.get('title') or not data.get('price'):
        return jsonify({"status": "error", "message": "Title and price are required"}), 400

    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_deals.json')

    local_data = []
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                local_data = json.load(f)
        except Exception:
            local_data = []

    new_deal = {
        "title": data.get('title'),
        "price": int(data.get('price')),
        "store": data.get('store', 'Local Shop'),
        "link": data.get('link', '#'),
        "image": data.get('image', 'https://via.placeholder.com/80')
    }

    local_data.append(new_deal)

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(local_data, f, indent=2)

    return jsonify({"status": "success", "deal": new_deal})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)