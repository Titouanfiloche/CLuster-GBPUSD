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
            time_cell = row.select_one(".calendar__time")
            country_cell = row.select_one(".calendar__flag")
            impact_cell = row.select_one(".impact span")
            event_cell = row.select_one(".calendar__event")

            time_str = time_cell.text.strip()
            country = country_cell['title'].strip()
            impact = impact_cell['title'].strip()
            title = event_cell.text.strip()

            if impact != "High":
                continue
            if country not in ["United States", "United Kingdom", "European Union"]:
                continue
            if time_str.lower() in ["all day", "tentative", ""]:
                continue

            today = dt.datetime.now(pytz.UTC).strftime("%Y-%m-%d")
            full_time = f"{today} {time_str}"
            try:
                time_obj = dt.datetime.strptime(full_time, "%Y-%m-%d %I:%M%p").replace(tzinfo=pytz.UTC)
            except:
                try:
                    time_obj = dt.datetime.strptime(full_time, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
                except:
                    continue

            events.append({
                "source": "ForexFactory",
                "impact": impact,
                "country": country,
                "event": title,
                "time": time_obj
            })
        except:
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
            country = row.get("data-country", "").strip()
            impact_level = len(row.select(".grayFullBullishIcon"))
            title = row.select_one(".event").text.strip()
            time_str = row.select_one(".first.left.time").text.strip()

            if impact_level < 3:
                continue
            if country not in ["United Kingdom", "United States", "European Union"]:
                continue

            today = dt.datetime.now(pytz.UTC).strftime("%Y-%m-%d")
            full_time = f"{today} {time_str}"
            try:
                time_obj = dt.datetime.strptime(full_time, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
            except:
                continue

            events.append({
                "source": "Investing",
                "impact": "High",
                "country": country,
                "event": title,
                "time": time_obj
            })
        except:
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

