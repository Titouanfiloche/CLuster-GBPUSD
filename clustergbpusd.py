import rlcompleter
import readline
readline.parse_and_bind("tab: complete")
#!/usr/bin/env python3
# coding: utf-8

import requests
import pandas as pd
from bs4 import BeautifulSoup
import datetime as dt
import numpy as np
import pytz
import telegram

# === PARAMETRES ===
API_KEY_TWELVE = "a77aea14967440938a748d4313fdf39a"
TELEGRAM_TOKEN = "7614952417:AAGoqLBNgsBl1ZNZOLUdEuZAe9CMZPVxGb4"
TELEGRAM_CHAT_ID = "1088487103"

# === FONCTIONS ===
def convert_to_24h_format(time_str):
    try:
        return dt.datetime.strptime(time_str.strip().lower(), "%I:%M%p").time()
    except:
        return None
        
def get_volatility(symbol, interval="1min", window=180):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={window}&apikey={API_KEY_TWELVE}"
    r = requests.get(url).json()
    df = pd.DataFrame(r['values'])
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df = df.set_index('datetime').sort_index()
    df = df.between_time("08:00", "11:00")
    return df['high'].max() - df['low'].min()

def get_lunch_volatility(symbol, interval="1min", window=120):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={window}&apikey={API_KEY_TWELVE}"
    r = requests.get(url).json()
    df = pd.DataFrame(r['values'])
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df = df.set_index('datetime').sort_index()
    df = df.between_time("11:00", "12:45")
    return df['high'].max() - df['low'].min()

def get_delta_spread():
    vol_gbp = get_volatility("GBP/USD")
    vol_eur = get_volatility("EUR/USD")
    return vol_gbp - vol_eur

def scraper_forexfactory():
    url = "https://www.forexfactory.com/calendar?day=today"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

   events = []

for row in soup.select("tr.calendar__row"):
    try:
        impact_td = row.select_one(".calendar__impact")
        if not impact_td or "high" not in str(impact_td).lower():
            continue

        country_icon = row.select_one(".calendar__flag")
        country = country_icon["title"].strip() if country_icon else ""
        if country not in ["USD", "EUR", "GBP"]:
            continue

        title_cell = row.select_one(".calendar__event")
        title = title_cell.get_text(strip=True) if title_cell else ""

        time_cell = row.select_one(".calendar__time")
        time_str = time_cell.get_text(strip=True).lower() if time_cell else ""
        if time_str in ["all day", "tentative", ""]:
            continue

        # Convertir l'heure en format 24h UTC
        today = dt.datetime.now(pytz.UTC).date()
        converted_time = convert_to_24h_format(time_str)
        if converted_time is None:
            try:
                converted_time = dt.datetime.strptime(time_str.strip(), "%H:%M").time()
            except:
                continue

        time_obj = dt.datetime.combine(today, converted_time).replace(tzinfo=pytz.UTC)

        events.append({
            "source": "ForexFactory",
            "impact": "High",
            "country": country,
            "event": title,
            "time": time_obj
        })

    except Exception as e:
        print(f"[ERREUR PARSING LIGNE ForexFactory] {e}")
        continue
           
    after_13h = [e for e in events if e["time"].hour >= 13]
    return events, after_13h

def scraper_investing():
    url = "https://www.investing.com/economic-calendar/"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest"
    }

    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    events = []
    rows = soup.select("tr.js-event-item")
    for row in rows:
    try:
    impact_icons = row.select("td[class*='sentiment'] i.fullStarIcon")
    if len(impact_icons) < 3:
        continue
    impact = "High"

    country_cell = row.select_one("td.flagCur span")
    country = country_cell.text.strip() if country_cell else ""
    if country not in ["USD", "EUR", "GBP"]:
        continue
        
    title_cell = row.select_one("td.event")
    title = title_cell.text.strip() if title_cell else ""

    time_cell = row.select_one("td.time")
    time_str = time_cell.text.strip()
    if time_str.lower() in ["all day", "tentative", ""]:
        continue
            
    today = dt.datetime.now(pytz.UTC).date()
    try:
        converted_time = dt.datetime.strptime(time_str, "%H:%M").time()
    except:
        continue
               
    time_obj = dt.datetime.strptime(full_time, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)

    events.append({
        "source": "Investing",
        "impact": "High",
        "country": country,
        "event": title,
        "time": time_obj
    })
    except Exception as e:
        print(f"[ERREUR PARSING Investing] {e}")
        continue

    after_13h = [e for e in events if e["time"].hour >= 13]
    return events, after_13h

def get_calendar_announcements():
    try:
        events_ff, after_13h_ff = scraper_forexfactory()
    except Exception as e:
        print(f"[ERREUR ForexFactory] {e}")
        events_ff, after_13h_ff = [], []

    try:
        events_inv, after_13h_inv = scraper_investing()
    except Exception as e:
        print(f"[ERREUR Investing] {e}")
        events_inv, after_13h_inv = [], []

    all_events = events_ff + events_inv
    all_after_13h = after_13h_ff + after_13h_inv

    return all_events, all_after_13h

def determine_cluster():
    score = [0, 0, 0]

    # 1. Vol London
    vol_london = get_volatility("GBP/USD") * 10000
    if vol_london < 45:
        score[0] += 3; score[1] += 0; score[2] += 2
    elif 45 <= vol_london <= 65:
        score[0] += 1; score[1] += 3; score[2] += 2
    else:
        score[0] += 0; score[1] += 3; score[2] += 2

    # 2. Lunch > London ?
    lunch_vol = get_lunch_volatility("GBP/USD") * 10000
    if lunch_vol > vol_london:
        score[0] += 3; score[1] += 2; score[2] += 1
    else:
        score[0] += 1; score[1] += 3; score[2] += 2

    # 3. Annonces éco
    annonces, annonces_post_13h = get_calendar_announcements()
    print(f"[DEBUG] Annonces majeures aujourd’hui : {len(annonces)} | Après 13h UTC : {len(annonces_post_13h)}")
    for a in annonces_post_13h:
        print(f"- {a['title']} ({a['country']}) à {a['time']}")
    nb_annonces = len(annonces)
    only_post_13h = len(annonces_post_13h) == nb_annonces

    if only_post_13h:
        score[0] += 1; score[1] += 2; score[2] += 3
    if nb_annonces == 0:
        score[2] += 1
    elif nb_annonces == 1:
        score[0] += 1; score[1] += 2; score[2] += 2
    elif nb_annonces >= 2:
        score[0] += 0; score[1] += 2; score[2] += 3

    # 4. Jour précédent (à remplacer par historique réel si on le stocke)
    # Exemple temporaire : cluster d’hier = 1
    prev = 1
    if prev == 0:
        score[0] += 3; score[1] += 1; score[2] += 1
    elif prev == 1:
        score[0] += 2; score[1] += 1; score[2] += 1
    elif prev == 2:
        score[0] += 3; score[1] += 1; score[2] += 1

    # 5. Delta spread
    delta = get_delta_spread()
    if delta > 0:
        score[0] += 2; score[1] += 1; score[2] += 2

    # 6. Directionnalité du jour (jour de semaine)
    weekday = dt.datetime.now(pytz.UTC).weekday()
    if 1 <= weekday <= 3:
        score[0] += 2; score[1] += 1; score[2] += 3

    total = sum(score)
    proba = [round(s/total*100, 1) for s in score]
    return proba

def send_telegram_message(message):
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# === EXECUTION PRINCIPALE ===
if __name__ == "__main__":
    proba = determine_cluster()
    message = (
        f"📊 Probabilité des clusters GBP/USD pour aujourd'hui :\n"
        f"Cluster 0 (calme, opportuniste) : {proba[0]}%\n"
        f"Cluster 1 (range, piégeux) : {proba[1]}%\n"
        f"Cluster 2 (directionnel) : {proba[2]}%\n"
    )
    send_telegram_message(message)

