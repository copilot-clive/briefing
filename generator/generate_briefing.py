#!/usr/bin/env python3
"""
Morning Briefing Generator
Generates daily briefing with expansion panels and voice audio
"""

import os
import sys
import json
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path

import requests
import yfinance as yf

# Kokoro speak script path
KOKORO_SPEAK = Path.home() / "kokoro-tts" / "speak"

# Configuration
PORTFOLIO_PATH = Path.home() / "clawd" / "config" / "portfolio.json"
OUTPUT_DIR = Path.home() / "projects" / "briefing"
VOICES = {
    "summary": "bm_lewis",      # Clive - British male grumpy
    "stocks": "am_michael",     # American male professional
    "crypto": "af_nova",        # American female tech-savvy
    "news": "bf_emma",          # British female authoritative
    "weather": "am_adam",       # American male friendly
}

# News sources (AllSides Center-rated)
NEWS_SOURCES = {
    "general": ["reuters.com", "apnews.com", "bbc.com"],
    "markets": ["bloomberg.com", "ft.com", "marketwatch.com"],
    "crypto": ["coindesk.com", "theblock.co"],
}


def load_portfolio():
    """Load portfolio configuration"""
    with open(PORTFOLIO_PATH) as f:
        return json.load(f)


def fetch_stock_data(symbols):
    """Fetch current stock prices and changes"""
    data = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            hist = ticker.history(period="5d")
            
            price = info.last_price
            prev = info.previous_close
            change_pct = ((price - prev) / prev) * 100 if prev else 0
            
            # Get 5-day prices for sparkline
            prices = hist['Close'].tolist()[-5:] if len(hist) > 0 else []
            
            data[symbol] = {
                "price": price,
                "change_pct": change_pct,
                "prev_close": prev,
                "prices_5d": prices,
            }
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            data[symbol] = {"price": 0, "change_pct": 0, "error": str(e)}
    return data


def fetch_crypto_data():
    """Fetch crypto prices from CoinGecko"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "bitcoin,ethereum",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
        }
        resp = requests.get(url, params=params, timeout=10)
        return resp.json()
    except Exception as e:
        print(f"Error fetching crypto: {e}")
        return {}


def fetch_weather():
    """Fetch weather from Open-Meteo for Doha and Al Udeid"""
    weather_data = {}
    
    locations = {
        "doha": {"lat": 25.29, "lon": 51.53, "name": "Doha"},
        "al_udeid": {"lat": 25.12, "lon": 51.32, "name": "Al Udeid Air Base"},
    }
    
    for key, loc in locations.items():
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "current_weather": "true",
                "hourly": "temperature_2m,weathercode",
                "daily": "weathercode,temperature_2m_max,temperature_2m_min",
                "forecast_days": 7,
                "timezone": "Asia/Qatar",
            }
            resp = requests.get(url, params=params, timeout=10)
            weather_data[key] = resp.json()
            weather_data[key]["location_name"] = loc["name"]
        except Exception as e:
            print(f"Error fetching weather for {key}: {e}")
    
    return weather_data


def fetch_market_news():
    """Fetch market news headlines (placeholder - would need news API)"""
    # For now, return placeholder - in production would use NewsAPI or similar
    return [
        {"title": "Markets update pending", "source": "Reuters"},
    ]


def fetch_middle_east_news():
    """Fetch Middle East news from multiple RSS feeds"""
    import xml.etree.ElementTree as ET
    
    # Multiple sources for balanced coverage
    # Google News filtered for AP and Reuters only (wire services)
    feeds = [
        {"url": "https://news.google.com/rss/search?q=middle+east+site:apnews.com+when:1d&hl=en-US&gl=US&ceid=US:en", "source": "AP"},
        {"url": "https://news.google.com/rss/search?q=middle+east+site:reuters.com+when:1d&hl=en-US&gl=US&ceid=US:en", "source": "Reuters"},
        {"url": "https://news.google.com/rss/search?q=israel+OR+iran+site:apnews.com+when:1d&hl=en-US&gl=US&ceid=US:en", "source": "AP"},
        {"url": "https://news.google.com/rss/search?q=israel+OR+iran+site:reuters.com+when:1d&hl=en-US&gl=US&ceid=US:en", "source": "Reuters"},
    ]
    
    # Keywords to prioritize Middle East tension stories
    priority_keywords = [
        'israel', 'gaza', 'hamas', 'hezbollah', 'iran', 'lebanon', 
        'yemen', 'houthi', 'red sea', 'syria', 'iraq', 'saudi', 
        'qatar', 'uae', 'gulf', 'palestinian', 'netanyahu', 'tehran',
        'strike', 'missile', 'attack', 'tension', 'conflict', 'war'
    ]
    
    articles = []
    
    for feed in feeds:
        try:
            resp = requests.get(feed["url"], timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            })
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall('.//item')[:10]:
                    title_elem = item.find('title')
                    desc_elem = item.find('description')
                    if title_elem is not None:
                        title = title_elem.text or ''
                        desc = desc_elem.text if desc_elem is not None else ''
                        
                        # Score by relevance
                        text_lower = (title + ' ' + desc).lower()
                        relevance = sum(1 for kw in priority_keywords if kw in text_lower)
                        
                        articles.append({
                            'title': title,
                            'description': desc,
                            'source': feed["source"],
                            'relevance': relevance
                        })
        except Exception as e:
            print(f"  Error fetching {feed['source']}: {e}")
    
    # Sort by relevance, take top stories
    articles.sort(key=lambda x: x['relevance'], reverse=True)
    
    # Deduplicate by similar titles
    seen = set()
    unique = []
    for a in articles:
        title_key = a['title'][:50].lower()
        if title_key not in seen:
            seen.add(title_key)
            unique.append(a)
    
    return unique[:5]


def generate_news_script(data):
    """Generate Middle East news analysis - tension-aware, analytical"""
    news = data.get("news", {})
    articles = news.get("middle_east", [])
    
    if not articles:
        return "Quiet day on the Middle East front. No major developments to report."
    
    # Check for high-tension keywords
    tension_keywords = ['strike', 'attack', 'missile', 'killed', 'war', 'escalat', 'threat']
    high_tension = any(
        any(kw in a.get('title', '').lower() for kw in tension_keywords)
        for a in articles[:3]
    )
    
    script = ""
    
    if high_tension:
        script += "Alright, heads up — there's significant tension in the region right now. "
    else:
        script += "Here's what's happening in the Middle East. "
    
    # Summarize top stories with analysis
    for i, article in enumerate(articles[:3]):
        title = article.get('title', '')
        source = article.get('source', '')
        relevance = article.get('relevance', 0)
        
        # Clean up title for speech
        title = title.replace('—', '-').replace('"', '').replace("'", "")
        
        if i == 0:
            script += f"Top story: {title}. "
            if relevance > 3:
                script += "This is a significant development. "
        else:
            script += f"{title}. "
    
    # Context based on what we're seeing
    combined = ' '.join(a.get('title', '').lower() for a in articles[:5])
    
    if 'gaza' in combined or 'israel' in combined:
        script += "The Gaza situation continues to dominate headlines. "
    if 'iran' in combined:
        script += "Iran-related tensions are in play. Keep an eye on that. "
    if 'houthi' in combined or 'red sea' in combined:
        script += "Red Sea shipping disruptions ongoing. "
    if 'saudi' in combined or 'uae' in combined:
        script += "Gulf states making moves. "
    
    script += "That's your regional update. Stay safe out there."
    
    return script.strip()


def generate_voice(text, voice, output_path, speed=1.0):
    """Generate voice audio using Kokoro speak script"""
    try:
        # Use the kokoro speak script
        result = subprocess.run(
            [str(KOKORO_SPEAK), text, str(output_path), voice],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0 and output_path.exists():
            print(f"  Generated: {output_path.name}")
            return True
        else:
            print(f"  Error: {result.stderr}")
    except Exception as e:
        print(f"Error generating voice: {e}")
    return False


def generate_all_voices(briefing_data, output_dir):
    """Generate all voice files for the briefing"""
    voice_files = {}
    
    # Main summary
    summary_text = generate_summary_script(briefing_data)
    print(f"  Summary script: {len(summary_text)} chars")
    summary_path = output_dir / "audio_summary.wav"
    if generate_voice(summary_text, VOICES["summary"], summary_path, speed=0.95):
        voice_files["summary"] = "audio_summary.wav"
    
    # Stocks analysis
    stocks_text = generate_stocks_script(briefing_data)
    print(f"  Stocks script: {len(stocks_text)} chars")
    stocks_path = output_dir / "audio_stocks.wav"
    if generate_voice(stocks_text, VOICES["stocks"], stocks_path, speed=1.0):
        voice_files["stocks"] = "audio_stocks.wav"
    
    # Crypto analysis
    crypto_text = generate_crypto_script(briefing_data)
    print(f"  Crypto script: {len(crypto_text)} chars")
    crypto_path = output_dir / "audio_crypto.wav"
    if generate_voice(crypto_text, VOICES["crypto"], crypto_path, speed=1.0):
        voice_files["crypto"] = "audio_crypto.wav"
    
    # News analysis (Middle East)
    news_text = generate_news_script(briefing_data)
    print(f"  News script: {len(news_text)} chars")
    news_path = output_dir / "audio_news.wav"
    if generate_voice(news_text, VOICES["news"], news_path, speed=1.0):
        voice_files["news"] = "audio_news.wav"
    
    # Weather
    weather_text = generate_weather_script(briefing_data)
    print(f"  Weather script: {len(weather_text)} chars")
    weather_path = output_dir / "audio_weather.wav"
    if generate_voice(weather_text, VOICES["weather"], weather_path, speed=1.0):
        voice_files["weather"] = "audio_weather.wav"
    
    return voice_files


def generate_summary_script(data):
    """Generate main summary voice script - conversational, analytical"""
    date = datetime.now().strftime("%A, %B %d")
    
    portfolio = data.get("portfolio", {})
    stocks = data.get("stocks", {})
    crypto = data.get("crypto", {})
    weather = data.get("weather", {})
    news = data.get("news", {})
    
    # Find the story - biggest movers and why
    movers = [(sym, stocks.get(sym, {}).get("change_pct", 0)) for sym in portfolio.get("stocks", {}).keys()]
    movers.sort(key=lambda x: x[1])  # Sort by change, losers first
    
    biggest_loser = movers[0] if movers else None
    biggest_winner = movers[-1] if movers else None
    
    btc_change = crypto.get("bitcoin", {}).get("usd_24h_change", 0)
    
    # Weather data
    doha_weather = weather.get("doha", {})
    doha_temp = doha_weather.get("current_weather", {}).get("temperature", 20)
    
    # Build conversational script
    script = f"Morning Bernhard. {date}. "
    
    # Weather upfront
    script += f"It's {doha_temp:.0f} degrees in Doha right now. "
    
    # Weekly trend
    daily = doha_weather.get("daily", {})
    if daily.get("temperature_2m_max"):
        week_highs = daily["temperature_2m_max"][:7]
        avg_high = sum(week_highs) / len(week_highs) if week_highs else doha_temp
        if avg_high > 30:
            script += "Staying hot all week. "
        elif avg_high > 25:
            script += "Nice weather ahead for the week. "
        else:
            script += "Cooler week coming up. "
    
    # Lead with the main story
    if abs(btc_change) > 5:
        script += f"Crypto's taking a hit — Bitcoin's down about {abs(btc_change):.0f} percent. "
    
    # Stock narrative
    avg_change = sum(m[1] for m in movers) / len(movers) if movers else 0
    if avg_change < -2:
        script += "Red day in the markets. "
        if biggest_loser and biggest_loser[1] < -3:
            script += f"{biggest_loser[0]} is your biggest drag. "
    elif avg_change > 1:
        script += "Green day for your portfolio. "
    else:
        script += "Markets are mixed today. "
    
    # Middle East news teaser
    me_news = news.get("middle_east", [])
    if me_news and me_news[0].get('relevance', 0) > 2:
        script += "There's some significant Middle East news to cover. "
    
    script += "Check the sections for the full breakdown."
    
    return script.strip()


def generate_stocks_script(data):
    """Generate stocks analysis - WHY things are moving, not just numbers"""
    stocks = data.get("stocks", {})
    portfolio = data.get("portfolio", {})
    
    # Analyze the movements
    movers = []
    for symbol, info in portfolio.get("stocks", {}).items():
        stock_data = stocks.get(symbol, {})
        change = stock_data.get("change_pct", 0)
        movers.append((symbol, change))
    
    movers.sort(key=lambda x: x[1])
    
    script = "Alright, let's talk about what's actually happening with your stocks. "
    
    # Sector analysis
    tech_stocks = ['NVDA', 'GOOGL', 'META', 'AAPL', 'MSFT', 'AMZN']
    tech_changes = [stocks.get(s, {}).get("change_pct", 0) for s in tech_stocks if s in stocks]
    avg_tech = sum(tech_changes) / len(tech_changes) if tech_changes else 0
    
    if avg_tech < -2:
        script += "Tech is getting hit across the board today. "
        script += "This usually means either rate concerns, or investors rotating out of growth. "
    elif avg_tech > 2:
        script += "Tech is leading the charge today — risk-on mode. "
    
    # Individual stock stories
    if 'NVDA' in stocks:
        nvda_change = stocks['NVDA'].get('change_pct', 0)
        if abs(nvda_change) > 2:
            if nvda_change < 0:
                script += f"Nvidia's down — probably AI sentiment cooling off, or chip sector rotation. Nothing fundamental changed. "
            else:
                script += f"Nvidia's pushing higher — AI hype train keeps rolling. "
    
    if 'TSLA' in stocks:
        tsla_change = stocks['TSLA'].get('change_pct', 0)
        if abs(tsla_change) > 2:
            script += f"Tesla's volatile as usual — you know how that goes. "
    
    if 'AMZN' in stocks:
        amzn_change = stocks['AMZN'].get('change_pct', 0)
        if amzn_change < -3:
            script += "Amazon taking a hit — could be profit-taking or broader retail concerns. "
    
    # VOO as market proxy
    if 'VOO' in stocks:
        voo_change = stocks['VOO'].get('change_pct', 0)
        if voo_change < -1:
            script += f"The broader market via VOO is down too, so this isn't just your picks — it's the whole market. "
        elif voo_change > 1:
            script += "The market overall is up, so rising tide lifting all boats. "
    
    # Closing thought
    script += "No major earnings or news moving your specific holdings that I can see. Mostly macro sentiment."
    
    return script.strip()


def generate_crypto_script(data):
    """Generate crypto analysis - sentiment, why, predictions"""
    crypto = data.get("crypto", {})
    
    btc = crypto.get("bitcoin", {})
    eth = crypto.get("ethereum", {})
    
    btc_change = btc.get("usd_24h_change", 0)
    eth_change = eth.get("usd_24h_change", 0)
    btc_price = btc.get("usd", 0)
    
    script = "Okay, crypto. "
    
    # Analyze the move
    if btc_change < -5:
        script += "We're seeing a significant pullback. "
        script += "This kind of drop is usually one of three things: "
        script += "either macro fear pushing people to cash, "
        script += "whales taking profits, "
        script += "or some regulatory news spooking the market. "
        script += "Nothing has fundamentally changed about Bitcoin though. "
        
        if btc_price > 60000:
            script += "We're still well above sixty K, so this is normal volatility in the grand scheme. "
        
    elif btc_change < -2:
        script += "Slight pullback — nothing unusual. Crypto does this. "
        script += "Could just be profit-taking after recent gains. "
        
    elif btc_change > 5:
        script += "Nice rally happening. "
        script += "Usually driven by institutional buying or positive sentiment around ETFs. "
        
    else:
        script += "Pretty quiet in crypto land. Consolidation phase. "
    
    # ETH correlation
    if abs(btc_change - eth_change) < 2:
        script += "ETH is moving in lockstep with Bitcoin, which is normal. "
    elif eth_change < btc_change - 3:
        script += "Ethereum's underperforming Bitcoin today — sometimes means money rotating into BTC for safety. "
    elif eth_change > btc_change + 3:
        script += "Interesting — ETH is outperforming BTC. Could be Layer 2 hype or DeFi activity picking up. "
    
    # Sentiment
    if btc_change < -5:
        script += "Sentiment is fearful right now, which historically has been a good time to accumulate if you're long-term. "
    
    script += "You're holding for the long run anyway, so don't let the daily noise stress you out."
    
    return script.strip()


def generate_weather_script(data):
    """Generate weather - Doha, Al Udeid, and weekly outlook"""
    weather = data.get("weather", {})
    
    doha = weather.get("doha", {})
    al_udeid = weather.get("al_udeid", {})
    
    doha_current = doha.get("current_weather", {})
    udeid_current = al_udeid.get("current_weather", {})
    
    doha_temp = doha_current.get("temperature", 20)
    udeid_temp = udeid_current.get("temperature", doha_temp)
    doha_wind = doha_current.get("windspeed", 0)
    udeid_wind = udeid_current.get("windspeed", 0)
    
    script = ""
    
    # Doha today
    script += f"Doha right now: {doha_temp:.0f} degrees. "
    
    if doha_temp < 22:
        script += "Nice and cool — enjoy it while it lasts. "
    elif doha_temp < 30:
        script += "Comfortable temperature. "
    elif doha_temp < 38:
        script += "Warm but manageable. "
    else:
        script += "Hot one. Stay hydrated. "
    
    # Al Udeid for weekday flying
    script += f"Al Udeid is sitting at {udeid_temp:.0f} degrees. "
    
    if udeid_wind > 25:
        script += f"Watch the wind out there — {udeid_wind:.0f} K per hour. Could affect flight ops. "
    elif udeid_wind > 15:
        script += "Light winds at the base. "
    else:
        script += "Calm conditions at the base. "
    
    # Weekly outlook
    daily = doha.get("daily", {})
    if daily.get("temperature_2m_max"):
        highs = daily["temperature_2m_max"][:7]
        lows = daily.get("temperature_2m_min", [])[:7]
        
        avg_high = sum(highs) / len(highs) if highs else doha_temp
        
        script += f"Looking at the week ahead: highs around {avg_high:.0f} degrees. "
        
        # Trend
        if len(highs) >= 3:
            early_week = sum(highs[:3]) / 3
            late_week = sum(highs[3:]) / len(highs[3:]) if len(highs) > 3 else early_week
            
            if late_week > early_week + 3:
                script += "Warming up toward the weekend. "
            elif late_week < early_week - 3:
                script += "Cooling down later in the week. "
            else:
                script += "Pretty consistent all week. "
    
    script += "Safe travels if you're heading to the base."
    
    return script.strip()


def generate_html(briefing_data, voice_files, output_dir):
    """Generate the HTML briefing page with expansion panels"""
    
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    time_str = datetime.now().strftime("%I:%M %p")
    
    stocks = briefing_data.get("stocks", {})
    portfolio = briefing_data.get("portfolio", {})
    crypto = briefing_data.get("crypto", {})
    weather = briefing_data.get("weather", {})
    
    # Calculate portfolio total
    stock_total = sum(
        stocks.get(sym, {}).get("price", 0) * info.get("shares", 0)
        for sym, info in portfolio.get("stocks", {}).items()
    )
    cash = portfolio.get("stocksCashUSD", 0)
    
    btc_price = crypto.get("bitcoin", {}).get("usd", 0)
    eth_price = crypto.get("ethereum", {}).get("usd", 0)
    btc_held = portfolio.get("crypto", {}).get("BTC", {}).get("amount", 0)
    eth_held = portfolio.get("crypto", {}).get("ETH", {}).get("amount", 0)
    crypto_total = btc_price * btc_held + eth_price * eth_held
    
    # Build stock rows
    stock_rows = ""
    for symbol, info in portfolio.get("stocks", {}).items():
        stock_data = stocks.get(symbol, {})
        price = stock_data.get("price", 0)
        change = stock_data.get("change_pct", 0)
        shares = info.get("shares", 0)
        value = price * shares
        
        change_class = "positive" if change >= 0 else "negative"
        change_sign = "+" if change >= 0 else ""
        
        stock_rows += f'''
            <div class="stock-row">
                <div><div class="stock-symbol">{symbol}</div><div class="stock-shares">{shares:.2f} shares</div></div>
                <div class="stock-value">${value:,.0f}</div>
                <div class="stock-price">${price:.2f}</div>
                <div class="stock-change {change_class}">{change_sign}{change:.2f}%</div>
            </div>
        '''
    
    # Weather data (now has doha and al_udeid)
    doha_weather = weather.get("doha", {})
    al_udeid_weather = weather.get("al_udeid", {})
    
    doha_current = doha_weather.get("current_weather", {})
    temp = doha_current.get("temperature", 20)
    wind = doha_current.get("windspeed", 0)
    weather_code = doha_current.get("weathercode", 0)
    
    udeid_temp = al_udeid_weather.get("current_weather", {}).get("temperature", temp)
    udeid_wind = al_udeid_weather.get("current_weather", {}).get("windspeed", 0)
    
    # Weekly forecast
    daily = doha_weather.get("daily", {})
    week_highs = daily.get("temperature_2m_max", [])[:7] if daily else []
    week_lows = daily.get("temperature_2m_min", [])[:7] if daily else []
    
    # Weather code to description
    weather_desc = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Depositing rime fog", 51: "Light drizzle",
        61: "Slight rain", 63: "Moderate rain", 80: "Slight rain showers",
    }.get(weather_code, "Unknown")
    
    weather_emoji = "☀️" if weather_code < 2 else "⛅" if weather_code < 4 else "☁️"
    
    # Crypto data
    btc_data = crypto.get("bitcoin", {})
    eth_data = crypto.get("ethereum", {})
    btc_change = btc_data.get("usd_24h_change", 0)
    eth_change = eth_data.get("usd_24h_change", 0)
    
    # Build news items
    news = briefing_data.get("news", {})
    middle_east_news = news.get("middle_east", [])
    news_items = ""
    for article in middle_east_news[:3]:
        title = article.get('title', '')[:80]  # Truncate long titles
        source = article.get('source', '')
        news_items += f'<div>• {title} <span style="color: var(--text-muted);">({source})</span></div>'
    if not news_items:
        news_items = '<div>• No major news at this time</div>'
    
    # Build week forecast HTML
    days = ['Today', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    week_forecast_html = ""
    for i, (high, low) in enumerate(zip(week_highs[:7], week_lows[:7])):
        day = days[i] if i < len(days) else f'Day {i+1}'
        week_forecast_html += f'''
            <div style="background: var(--bg-card-inner); padding: 8px 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 0.7rem; color: var(--text-muted);">{day}</div>
                <div style="font-size: 0.9rem; font-weight: 600; color: var(--text-primary);">{high:.0f}°</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">{low:.0f}°</div>
            </div>
        '''
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Morning Briefing - {date_str}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-main: #0d0d1a;
            --bg-card: #1a1a2e;
            --bg-card-inner: #252540;
            --bg-expand: #1f1f38;
            --border: rgba(255, 255, 255, 0.08);
            --text-primary: #ffffff;
            --text-secondary: rgba(255, 255, 255, 0.7);
            --text-muted: rgba(255, 255, 255, 0.4);
            --accent-green: #4ade80;
            --accent-red: #f87171;
            --accent-cyan: #22d3ee;
            --accent-pink: #f472b6;
            --accent-orange: #fb923c;
            --accent-purple: #a29bfe;
            --radius: 20px;
            --radius-sm: 12px;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-main);
            color: var(--text-secondary);
            padding: 40px 24px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 40px; }}
        .header-emoji {{ font-size: 3rem; margin-bottom: 16px; }}
        .header h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, #22d3ee, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .date {{ color: var(--text-muted); margin-top: 8px; font-size: 0.9rem; }}
        .greeting {{ color: var(--text-secondary); margin-top: 8px; }}
        
        /* Audio player */
        .main-audio {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            margin: 20px 0;
            padding: 16px;
            background: var(--bg-card);
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
        }}
        .play-btn {{
            background: linear-gradient(135deg, #22d3ee, #a78bfa);
            border: none;
            border-radius: 50%;
            width: 48px;
            height: 48px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            transition: transform 0.2s;
        }}
        .play-btn:hover {{ transform: scale(1.1); }}
        .audio-label {{ color: var(--text-primary); font-weight: 600; }}
        audio {{ display: none; }}
        
        .dashboard {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; }}
        .row-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }}
        
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 24px;
            position: relative;
        }}
        .card-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }}
        .card-icon {{
            width: 40px; height: 40px;
            border-radius: var(--radius-sm);
            display: flex; align-items: center; justify-content: center;
            font-size: 1.2rem;
        }}
        .card-icon.green {{ background: rgba(74, 222, 128, 0.15); }}
        .card-icon.cyan {{ background: rgba(34, 211, 238, 0.15); }}
        .card-icon.orange {{ background: rgba(251, 146, 60, 0.15); }}
        .card-icon.purple {{ background: rgba(167, 139, 250, 0.15); }}
        .card-title {{ font-size: 1rem; font-weight: 600; color: var(--text-primary); }}
        .card-subtitle {{ font-size: 0.75rem; color: var(--text-muted); }}
        
        /* Expand button */
        .expand-btn {{
            position: absolute;
            top: 16px;
            right: 16px;
            background: var(--bg-card-inner);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 6px 12px;
            color: var(--text-secondary);
            font-size: 0.75rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }}
        .expand-btn:hover {{
            background: var(--accent-purple);
            color: var(--text-primary);
        }}
        
        /* Expansion panel */
        .expand-panel {{
            display: none;
            margin-top: 20px;
            padding: 20px;
            background: var(--bg-expand);
            border-radius: var(--radius-sm);
            border: 1px solid var(--border);
        }}
        .expand-panel.active {{ display: block; }}
        .expand-panel .panel-audio {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }}
        .panel-play-btn {{
            background: var(--accent-purple);
            border: none;
            border-radius: 50%;
            width: 36px;
            height: 36px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
        }}
        .panel-content {{ font-size: 0.9rem; line-height: 1.6; }}
        .panel-content h4 {{ color: var(--text-primary); margin-bottom: 8px; }}
        .panel-content p {{ margin-bottom: 12px; }}
        
        .portfolio-total {{
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 8px;
        }}
        .portfolio-change {{ font-size: 0.9rem; }}
        .positive {{ color: var(--accent-green); }}
        .negative {{ color: var(--accent-red); }}
        
        .stock-row {{
            display: grid;
            grid-template-columns: 100px 90px 80px 70px;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid var(--border);
        }}
        .stock-row:last-child {{ border-bottom: none; }}
        .stock-symbol {{ font-weight: 600; color: var(--text-primary); }}
        .stock-shares {{ font-size: 0.75rem; color: var(--text-muted); }}
        .stock-value {{ font-size: 0.85rem; color: var(--text-secondary); }}
        .stock-price {{ font-weight: 600; color: var(--text-primary); text-align: right; }}
        .stock-change {{ font-size: 0.8rem; font-weight: 600; text-align: right; }}
        
        .summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
        .summary-item {{
            background: var(--bg-card-inner);
            border-radius: var(--radius-sm);
            padding: 16px;
            text-align: center;
        }}
        .summary-label {{ font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }}
        .summary-value {{ font-size: 1.5rem; font-weight: 700; color: var(--text-primary); margin-top: 4px; }}
        
        .crypto-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
        .crypto-item {{
            background: var(--bg-card-inner);
            border-radius: var(--radius-sm);
            padding: 16px;
        }}
        .crypto-name {{ font-size: 0.8rem; color: var(--text-muted); }}
        .crypto-price {{ font-size: 1.1rem; font-weight: 700; color: var(--text-primary); margin-top: 4px; }}
        .crypto-change {{ font-size: 0.8rem; font-weight: 600; }}
        
        .weather-main {{ display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }}
        .weather-icon {{ font-size: 3rem; }}
        .weather-temp {{ font-size: 2.5rem; font-weight: 700; color: var(--text-primary); }}
        .weather-details {{ display: flex; gap: 24px; }}
        .weather-detail {{ font-size: 0.85rem; }}
        
        .motivation-card {{ grid-column: span 2; text-align: center; padding: 32px; }}
        .motivation-quote {{
            font-size: 1.3rem;
            font-style: italic;
            color: var(--text-primary);
            line-height: 1.6;
        }}
        .motivation-author {{ margin-top: 16px; color: var(--accent-purple); font-weight: 600; }}
        
        .footer {{ text-align: center; padding: 40px 0 16px; }}
        .footer-crab {{ font-size: 2rem; }}
        .footer-text {{ font-size: 0.75rem; color: var(--text-muted); margin-top: 8px; }}
        
        @media (max-width: 900px) {{
            .dashboard {{ grid-template-columns: 1fr; }}
            .row-2 {{ grid-template-columns: 1fr; }}
            .motivation-card {{ grid-column: span 1; }}
            .stock-row {{ grid-template-columns: 80px 1fr 70px; }}
            .stock-value {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="header-emoji">👋</div>
            <h1>Morning Briefing</h1>
            <p class="date">{date_str}</p>
            <p class="greeting">Good morning, Bernhard. Here's your daily snapshot.</p>
        </header>
        
        <!-- Main audio player -->
        <div class="main-audio">
            <button class="play-btn" onclick="toggleAudio('main-audio-player', this)">▶️</button>
            <span class="audio-label">Play Full Briefing</span>
            <audio id="main-audio-player" src="audio_summary.wav"></audio>
        </div>

        <div class="dashboard">
            <!-- Portfolio Card -->
            <div class="card">
                <button class="expand-btn" onclick="togglePanel('stocks-panel', this)">
                    <span>More</span> ▼
                </button>
                <div class="card-header">
                    <div class="card-icon green">📈</div>
                    <div>
                        <div class="card-title">Portfolio</div>
                        <div class="card-subtitle">8 positions + cash</div>
                    </div>
                </div>
                <div class="portfolio-total">${stock_total + cash:,.0f}</div>
                {stock_rows}
                
                <div id="stocks-panel" class="expand-panel">
                    <div class="panel-audio">
                        <button class="panel-play-btn" onclick="toggleAudio('stocks-audio', this)">▶️</button>
                        <span>Listen to stock analysis</span>
                        <audio id="stocks-audio" src="audio_stocks.wav"></audio>
                    </div>
                    <div class="panel-content">
                        <h4>Detailed Analysis</h4>
                        <p>Your portfolio breakdown with individual position values and daily performance metrics.</p>
                        <p><strong>Cash position:</strong> ${cash:,.0f}</p>
                        <p><strong>Total invested:</strong> ${stock_total:,.0f}</p>
                    </div>
                </div>
            </div>

            <div>
                <!-- Summary Card -->
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon cyan">📊</div>
                        <div>
                            <div class="card-title">Summary</div>
                            <div class="card-subtitle">Net worth breakdown</div>
                        </div>
                    </div>
                    <div class="summary-grid">
                        <div class="summary-item">
                            <div class="summary-label">Stocks</div>
                            <div class="summary-value">${stock_total/1000:.1f}K</div>
                        </div>
                        <div class="summary-item">
                            <div class="summary-label">Cash</div>
                            <div class="summary-value">${cash/1000:.1f}K</div>
                        </div>
                        <div class="summary-item">
                            <div class="summary-label">Crypto</div>
                            <div class="summary-value">${crypto_total/1000:.1f}K</div>
                        </div>
                        <div class="summary-item">
                            <div class="summary-label">Total</div>
                            <div class="summary-value">${(stock_total + cash + crypto_total)/1000:.0f}K</div>
                        </div>
                    </div>
                </div>

                <!-- Crypto Card -->
                <div class="card" style="margin-top: 20px;">
                    <button class="expand-btn" onclick="togglePanel('crypto-panel', this)">
                        <span>More</span> ▼
                    </button>
                    <div class="card-header">
                        <div class="card-icon orange">🪙</div>
                        <div>
                            <div class="card-title">Crypto</div>
                            <div class="card-subtitle">Main holdings</div>
                        </div>
                    </div>
                    <div class="crypto-grid">
                        <div class="crypto-item">
                            <div class="crypto-name">Bitcoin</div>
                            <div class="crypto-price">${btc_price:,.0f}</div>
                            <div class="crypto-change {'positive' if btc_change >= 0 else 'negative'}">{'+' if btc_change >= 0 else ''}{btc_change:.2f}%</div>
                        </div>
                        <div class="crypto-item">
                            <div class="crypto-name">Ethereum</div>
                            <div class="crypto-price">${eth_price:,.0f}</div>
                            <div class="crypto-change {'positive' if eth_change >= 0 else 'negative'}">{'+' if eth_change >= 0 else ''}{eth_change:.2f}%</div>
                        </div>
                    </div>
                    <div style="margin-top: 12px; font-size: 0.85rem; color: var(--text-muted);">
                        Your BTC: {btc_held:.3f} (${btc_price * btc_held:,.0f}) · ETH: {eth_held:.2f} (${eth_price * eth_held:,.0f})
                    </div>
                    
                    <div id="crypto-panel" class="expand-panel">
                        <div class="panel-audio">
                            <button class="panel-play-btn" onclick="toggleAudio('crypto-audio', this)">▶️</button>
                            <span>Listen to crypto update</span>
                            <audio id="crypto-audio" src="audio_crypto.wav"></audio>
                        </div>
                        <div class="panel-content">
                            <h4>Crypto Deep Dive</h4>
                            <p>24-hour price movements and your holdings breakdown.</p>
                            <p><strong>Bitcoin:</strong> {btc_change:.2f}% in 24h</p>
                            <p><strong>Ethereum:</strong> {eth_change:.2f}% in 24h</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="row-2">
            <!-- Weather Card -->
            <div class="card">
                <button class="expand-btn" onclick="togglePanel('weather-panel', this)">
                    <span>More</span> ▼
                </button>
                <div class="card-header">
                    <div class="card-icon cyan">🌤️</div>
                    <div>
                        <div class="card-title">Weather</div>
                        <div class="card-subtitle">Doha & Al Udeid</div>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px;">DOHA</div>
                        <div style="font-size: 2rem; font-weight: 700; color: var(--text-primary);">{temp:.0f}°C</div>
                        <div style="font-size: 0.8rem; color: var(--text-secondary);">{weather_desc}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px;">AL UDEID</div>
                        <div style="font-size: 2rem; font-weight: 700; color: var(--text-primary);">{udeid_temp:.0f}°C</div>
                        <div style="font-size: 0.8rem; color: var(--text-secondary);">💨 {udeid_wind:.0f} km/h</div>
                    </div>
                </div>
                
                <div id="weather-panel" class="expand-panel">
                    <div class="panel-audio">
                        <button class="panel-play-btn" onclick="toggleAudio('weather-audio', this)">▶️</button>
                        <span>Listen to full forecast</span>
                        <audio id="weather-audio" src="audio_weather.wav"></audio>
                    </div>
                    <div class="panel-content">
                        <h4>Week Ahead</h4>
                        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                            {week_forecast_html}
                        </div>
                    </div>
                </div>
            </div>

            <!-- Middle East News Card -->
            <div class="card">
                <button class="expand-btn" onclick="togglePanel('news-panel', this)">
                    <span>More</span> ▼
                </button>
                <div class="card-header">
                    <div class="card-icon orange">🌍</div>
                    <div>
                        <div class="card-title">Middle East</div>
                        <div class="card-subtitle">Regional news</div>
                    </div>
                </div>
                <div style="font-size: 0.9rem; line-height: 1.8;">
                    {news_items}
                </div>
                
                <div id="news-panel" class="expand-panel">
                    <div class="panel-audio">
                        <button class="panel-play-btn" onclick="toggleAudio('news-audio', this)">▶️</button>
                        <span>Listen to news analysis</span>
                        <audio id="news-audio" src="audio_news.wav"></audio>
                    </div>
                    <div class="panel-content">
                        <h4>Regional Analysis</h4>
                        <p>What's happening in the Middle East and what it means.</p>
                    </div>
                </div>
            </div>
        </div>

        <div class="row-2">
            <div class="card motivation-card">
                <div class="card-icon purple" style="margin: 0 auto 16px;">💡</div>
                <div class="motivation-quote">
                    "The stock market is a device for transferring money from the impatient to the patient."
                </div>
                <div class="motivation-author">— Warren Buffett</div>
            </div>
        </div>

        <footer class="footer">
            <div class="footer-crab">🦀</div>
            <p class="footer-text">Generated by Clive · Last updated {time_str}</p>
        </footer>
    </div>
    
    <script>
        function toggleAudio(audioId, btn) {{
            const audio = document.getElementById(audioId);
            if (audio.paused) {{
                // Pause all other audio
                document.querySelectorAll('audio').forEach(a => {{
                    if (a.id !== audioId) {{
                        a.pause();
                        a.currentTime = 0;
                    }}
                }});
                document.querySelectorAll('.play-btn, .panel-play-btn').forEach(b => {{
                    b.textContent = '▶️';
                }});
                audio.play();
                btn.textContent = '⏸️';
            }} else {{
                audio.pause();
                btn.textContent = '▶️';
            }}
            audio.onended = () => {{ btn.textContent = '▶️'; }};
        }}
        
        function togglePanel(panelId, btn) {{
            const panel = document.getElementById(panelId);
            const isActive = panel.classList.contains('active');
            
            // Close all panels first
            document.querySelectorAll('.expand-panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.expand-btn').forEach(b => {{
                b.innerHTML = '<span>More</span> ▼';
            }});
            
            if (!isActive) {{
                panel.classList.add('active');
                btn.innerHTML = '<span>Less</span> ▲';
            }}
        }}
    </script>
</body>
</html>'''
    
    return html


def main():
    """Main generator function"""
    import sys
    print(f"Generating briefing for {datetime.now().strftime('%Y-%m-%d %H:%M')}", flush=True)
    
    # Create output directory with unique hash
    date_str = datetime.now().strftime("%Y-%m-%d")
    hash_str = hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:16]
    folder_name = f"{date_str}-{hash_str}"
    output_dir = OUTPUT_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Output directory: {output_dir}")
    
    # Load portfolio
    print("Loading portfolio...")
    portfolio = load_portfolio()
    
    # Fetch data
    print("Fetching stock data...")
    stocks = fetch_stock_data(list(portfolio.get("stocks", {}).keys()))
    
    print("Fetching crypto data...")
    crypto = fetch_crypto_data()
    
    print("Fetching weather...")
    weather = fetch_weather()
    
    print("Fetching Middle East news...")
    middle_east_news = fetch_middle_east_news()
    
    # Compile briefing data
    briefing_data = {
        "portfolio": portfolio,
        "stocks": stocks,
        "crypto": crypto,
        "weather": weather,
        "news": {
            "middle_east": middle_east_news
        },
        "generated": datetime.now().isoformat(),
    }
    
    # Generate voice files
    print("Generating voice audio...")
    voice_files = generate_all_voices(briefing_data, output_dir)
    print(f"Generated voice files: {voice_files}")
    
    # Generate HTML
    print("Generating HTML...")
    html = generate_html(briefing_data, voice_files, output_dir)
    
    with open(output_dir / "index.html", "w") as f:
        f.write(html)
    
    # Update current page pointer
    with open(OUTPUT_DIR / ".current_page", "w") as f:
        f.write(folder_name)
    
    # Save briefing data as JSON for reference
    with open(output_dir / "data.json", "w") as f:
        json.dump(briefing_data, f, indent=2, default=str)
    
    print(f"Briefing generated: {folder_name}")
    return folder_name


if __name__ == "__main__":
    folder = main()
    print(f"\nBriefing URL: https://copilot-clive.github.io/briefing/{folder}/")
