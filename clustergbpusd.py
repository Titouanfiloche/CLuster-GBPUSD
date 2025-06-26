# === IMPORTS ===
import requests
import pandas as pd
import datetime as dt
import numpy as np
import pytz
from bs4 import BeautifulSoup
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

def get_calendar_announcements():
    events = []

    # === ForexFactory ===
    try:
        r = requests.get("https://www.forexfactory.com/calendar?day=today", timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")
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
    except Exception as e:
        print(f"[ERREUR ForexFactory] {e}")

    # === Investing.com ===
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get("https://www.investing.com/economic-calendar/", headers=headers, timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")
        for row in soup.select("tr.js-event-item"):
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
                time_obj = dt.datetime.combine(today, converted_time).replace(tzinfo=pytz.UTC)
                events.append({
                    "source": "Investing",
                    "impact": impact,
                    "country": country,
                    "event": title,
                    "time": time_obj
                })
            except Exception as e:
                print(f"[ERREUR PARSING Investing] {e}")
                continue
    except Exception as e:
        print(f"[ERREUR Investing] {e}")

    after_13h = [e for e in events if e["time"].hour >= 13]
    return events, after_13h

def determine_cluster():
    score = [0, 0, 0]

    vol_london = get_volatility("GBP/USD") * 10000
    if vol_london < 45:
        score[0] += 3; score[1] += 0; score[2] += 2
    elif 45 <= vol_london <= 65:
        score[0] += 1; score[1] += 3; score[2] += 2
    else:
        score[0] += 0; score[1] += 3; score[2] += 2

    lunch_vol = get_lunch_volatility("GBP/USD") * 10000
    if lunch_vol > vol_london:
        score[0] += 3; score[1] += 2; score[2] += 1
    else:
        score[0] += 1; score[1] += 3; score[2] += 2

    annonces, annonces_post_13h = get_calendar_announcements()
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

    prev = 1
    if prev == 0:
        score[0] += 3; score[1] += 1; score[2] += 1
    elif prev == 1:
        score[0] += 2; score[1] += 1; score[2] += 1
    elif prev == 2:
        score[0] += 3; score[1] += 1; score[2] += 1

    delta = get_delta_spread()
    if delta > 0:
        score[0] += 2; score[1] += 1; score[2] += 2

    weekday = dt.datetime.utcnow().weekday()
    if 1 <= weekday <= 3:
        score[0] += 2; score[1] += 1; score[2] += 3

    total = sum(score)
    proba = [round(s / total * 100, 1) for s in score]
    return proba

def send_telegram_message(message):
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# === EXECUTION PRINCIPALE ===
if __name__ == "__main__":
    proba = determine_cluster()
    message = (
        f"\U0001F4CA Probabilité des clusters GBP/USD pour aujourd'hui :\n"
        f"Cluster 0 (calme, opportuniste) : {proba[0]}%\n"
        f"Cluster 1 (range, piégeux) : {proba[1]}%\n"
        f"Cluster 2 (directionnel) : {proba[2]}%\n"
    )
    annonces, annonces_post_13h = get_calendar_announcements()
    print(f"[DEBUG] Annonces majeures aujourd’hui : {len(annonces)} | Après 13h UTC : {len(annonces_post_13h)}")
    for a in annonces_post_13h:
        print(f"- {a['event']} ({a['country']}) à {a['time'].strftime('%H:%M')} [{a['source']}]")

    send_telegram_message(message)
