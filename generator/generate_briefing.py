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
    "summary": "bm_lewis",      # Clive - British male
    "stocks": "am_michael",     # American male professional
    "crypto": "af_bella",       # American female modern
    "news": "bf_emma",          # British female authoritative
    "weather": "af_heart",      # Warm friendly
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


def fetch_weather(city="Doha"):
    """Fetch weather from Open-Meteo"""
    try:
        # Doha coordinates
        lat, lon = 25.29, 51.53
        url = f"https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            "hourly": "temperature_2m,weathercode",
            "daily": "weathercode,temperature_2m_max,temperature_2m_min",
            "timezone": "Asia/Qatar",
        }
        resp = requests.get(url, params=params, timeout=10)
        return resp.json()
    except Exception as e:
        print(f"Error fetching weather: {e}")
        return {}


def fetch_market_news():
    """Fetch market news headlines (placeholder - would need news API)"""
    # For now, return placeholder - in production would use NewsAPI or similar
    return [
        {"title": "Markets update pending", "source": "Reuters"},
    ]


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
    summary_path = output_dir / "audio_summary.wav"
    if generate_voice(summary_text, VOICES["summary"], summary_path, speed=0.95):
        voice_files["summary"] = "audio_summary.wav"
    
    # Stocks detail
    stocks_text = generate_stocks_script(briefing_data)
    stocks_path = output_dir / "audio_stocks.wav"
    if generate_voice(stocks_text, VOICES["stocks"], stocks_path, speed=1.0):
        voice_files["stocks"] = "audio_stocks.wav"
    
    # Crypto detail
    crypto_text = generate_crypto_script(briefing_data)
    crypto_path = output_dir / "audio_crypto.wav"
    if generate_voice(crypto_text, VOICES["crypto"], crypto_path, speed=1.0):
        voice_files["crypto"] = "audio_crypto.wav"
    
    # Weather detail
    weather_text = generate_weather_script(briefing_data)
    weather_path = output_dir / "audio_weather.wav"
    if generate_voice(weather_text, VOICES["weather"], weather_path, speed=1.0):
        voice_files["weather"] = "audio_weather.wav"
    
    return voice_files


def generate_summary_script(data):
    """Generate main summary voice script"""
    date = datetime.now().strftime("%A, %B %d")
    
    # Calculate totals
    portfolio = data.get("portfolio", {})
    stocks = data.get("stocks", {})
    crypto = data.get("crypto", {})
    weather = data.get("weather", {})
    
    total_value = sum(
        stocks.get(sym, {}).get("price", 0) * info.get("shares", 0)
        for sym, info in portfolio.get("stocks", {}).items()
    )
    total_value += portfolio.get("stocksCashUSD", 0)
    
    # Crypto value
    btc_price = crypto.get("bitcoin", {}).get("usd", 0)
    eth_price = crypto.get("ethereum", {}).get("usd", 0)
    btc_held = portfolio.get("crypto", {}).get("BTC", {}).get("amount", 0)
    eth_held = portfolio.get("crypto", {}).get("ETH", {}).get("amount", 0)
    crypto_value = btc_price * btc_held + eth_price * eth_held
    
    # Weather
    temp = weather.get("current_weather", {}).get("temperature", "unknown")
    
    # Build script
    script = f"""
    Good morning Bernhard. It's {date}. Here's your daily briefing.
    
    Your stock portfolio is currently valued at approximately {int(total_value / 1000)} thousand dollars.
    """
    
    # Check biggest movers
    movers = [(sym, stocks.get(sym, {}).get("change_pct", 0)) for sym in portfolio.get("stocks", {}).keys()]
    movers.sort(key=lambda x: abs(x[1]), reverse=True)
    
    if movers:
        top = movers[0]
        direction = "up" if top[1] > 0 else "down"
        script += f"The biggest mover today is {top[0]}, {direction} {abs(top[1]):.1f} percent. "
    
    # Crypto
    btc_change = crypto.get("bitcoin", {}).get("usd_24h_change", 0)
    script += f"Bitcoin is at {int(btc_price)} dollars, "
    script += f"{'up' if btc_change > 0 else 'down'} {abs(btc_change):.1f} percent. "
    
    # Weather
    script += f"The weather in Doha is {temp} degrees celsius. "
    
    script += "Expand any section for more details. Have a productive day."
    
    return script.strip()


def generate_stocks_script(data):
    """Generate stocks detail voice script"""
    stocks = data.get("stocks", {})
    portfolio = data.get("portfolio", {})
    
    script = "Here's your detailed stock breakdown. "
    
    for symbol, info in portfolio.get("stocks", {}).items():
        stock_data = stocks.get(symbol, {})
        price = stock_data.get("price", 0)
        change = stock_data.get("change_pct", 0)
        shares = info.get("shares", 0)
        value = price * shares
        
        direction = "up" if change > 0 else "down"
        script += f"{symbol} is at {price:.0f} dollars, {direction} {abs(change):.1f} percent. "
        script += f"Your {shares:.1f} shares are worth {value/1000:.1f} thousand. "
    
    return script.strip()


def generate_crypto_script(data):
    """Generate crypto detail voice script"""
    crypto = data.get("crypto", {})
    portfolio = data.get("portfolio", {})
    
    btc = crypto.get("bitcoin", {})
    eth = crypto.get("ethereum", {})
    
    btc_held = portfolio.get("crypto", {}).get("BTC", {}).get("amount", 0)
    eth_held = portfolio.get("crypto", {}).get("ETH", {}).get("amount", 0)
    
    script = "Here's your crypto update. "
    
    if btc:
        btc_val = btc.get("usd", 0) * btc_held
        btc_change = btc.get("usd_24h_change", 0)
        script += f"Bitcoin is trading at {btc.get('usd', 0):.0f} dollars, "
        script += f"{'up' if btc_change > 0 else 'down'} {abs(btc_change):.1f} percent in the last 24 hours. "
        script += f"Your point six bitcoin is worth {btc_val/1000:.1f} thousand dollars. "
    
    if eth:
        eth_val = eth.get("usd", 0) * eth_held
        eth_change = eth.get("usd_24h_change", 0)
        script += f"Ethereum is at {eth.get('usd', 0):.0f} dollars, "
        script += f"{'up' if eth_change > 0 else 'down'} {abs(eth_change):.1f} percent. "
        script += f"Your eleven E T H is worth {eth_val/1000:.1f} thousand. "
    
    return script.strip()


def generate_weather_script(data):
    """Generate weather detail voice script"""
    weather = data.get("weather", {})
    current = weather.get("current_weather", {})
    daily = weather.get("daily", {})
    
    temp = current.get("temperature", "unknown")
    wind = current.get("windspeed", 0)
    
    script = f"Current conditions in Doha: {temp} degrees celsius with winds at {wind:.0f} kilometers per hour. "
    
    if daily and daily.get("temperature_2m_max"):
        high = daily["temperature_2m_max"][0] if daily["temperature_2m_max"] else "unknown"
        low = daily["temperature_2m_min"][0] if daily.get("temperature_2m_min") else "unknown"
        script += f"Today's high will be {high:.0f} degrees, low of {low:.0f}. "
    
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
    
    # Weather data
    current_weather = weather.get("current_weather", {})
    temp = current_weather.get("temperature", "N/A")
    wind = current_weather.get("windspeed", 0)
    weather_code = current_weather.get("weathercode", 0)
    
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
                        <div class="card-subtitle">Doha, Qatar</div>
                    </div>
                </div>
                <div class="weather-main">
                    <div class="weather-icon">{weather_emoji}</div>
                    <div class="weather-temp">{temp}°C</div>
                </div>
                <div class="weather-details">
                    <div class="weather-detail">💨 {wind:.0f} km/h wind</div>
                    <div class="weather-detail">☁️ {weather_desc}</div>
                </div>
                
                <div id="weather-panel" class="expand-panel">
                    <div class="panel-audio">
                        <button class="panel-play-btn" onclick="toggleAudio('weather-audio', this)">▶️</button>
                        <span>Listen to weather forecast</span>
                        <audio id="weather-audio" src="audio_weather.wav"></audio>
                    </div>
                    <div class="panel-content">
                        <h4>Extended Forecast</h4>
                        <p>Current conditions and outlook for today.</p>
                    </div>
                </div>
            </div>

            <!-- Markets Today Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon orange">🌍</div>
                    <div>
                        <div class="card-title">Markets Today</div>
                        <div class="card-subtitle">Key moves</div>
                    </div>
                </div>
                <div style="font-size: 0.9rem; line-height: 1.8;">
                    <div>• Market data as of last close</div>
                    <div>• Crypto prices are live (24h change)</div>
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
    
    # Compile briefing data
    briefing_data = {
        "portfolio": portfolio,
        "stocks": stocks,
        "crypto": crypto,
        "weather": weather,
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
