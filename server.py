from flask import Flask, jsonify
import requests
import numpy as np
from flask_cors import CORS
from geopy.distance import geodesic
from scipy.spatial import KDTree
import time

app = Flask(__name__)
CORS(app)  # Allow frontend access

# ✅ Fetch Live Balloon Data from Windborne API (Handling NaN & Inf)
def get_balloon_data():
    url = "https://a.windbornesystems.com/treasure/02.json"
    response = requests.get(url)

    if response.status_code == 200:
        raw_data = response.json()
        balloons = []

        for entry in raw_data:
            if len(entry) == 3:  # Ensure valid format
                lat, lon, alt = entry
                if not (np.isnan(lat) or np.isnan(lon) or np.isnan(alt) or np.isinf(lat) or np.isinf(lon) or np.isinf(alt)):
                    balloons.append({
                        "latitude": lat,
                        "longitude": lon,
                        "altitude": alt * 1000  # Convert km to meters
                    })

        print(f"✅ {len(balloons)} valid weather balloons detected.")
        return balloons
    else:
        print(f"❌ Error fetching balloon data (Status Code: {response.status_code})")
        return []

# ✅ Caching Flight Data (Refreshes every 60 seconds)
cached_flight_data = []
last_flight_fetch_time = 0

def get_flight_data():
    global cached_flight_data, last_flight_fetch_time
    current_time = time.time()

    if current_time - last_flight_fetch_time < 60:
        print("✅ Using cached flight data")
        return cached_flight_data

    url = "https://opensky-network.org/api/states/all"
    response = requests.get(url)

    if response.status_code == 200:
        flight_data = response.json().get("states", [])
        flights = []

        for flight in flight_data:
            if flight[5] and flight[6] and flight[7]:  # Ensure valid lat, lon, alt
                flights.append({
                    "callsign": flight[1].strip() if flight[1] else "Unknown",
                    "latitude": flight[6],
                    "longitude": flight[5],
                    "altitude": flight[7]
                })

        cached_flight_data = flights
        last_flight_fetch_time = time.time()
        print(f"✅ {len(flights)} aircraft detected and cached.")
        return flights
    else:
        print("❌ Error fetching flight data")
        return cached_flight_data  # Return last known data instead of failing

# ✅ Optimized Risk Detection (Handles Missing Data)
def detect_risks(flights, balloons):
    alerts = []
    if not balloons or not flights:
        print("⚠️ No valid data for risk detection.")
        return []

    # ✅ Build KDTree for fast lookup (Handles missing balloon positions)
    try:
        balloon_positions = [(b["latitude"], b["longitude"]) for b in balloons]
        if len(balloon_positions) > 0:
            balloon_tree = KDTree(balloon_positions)
        else:
            print("⚠️ No valid balloon positions to build KDTree.")
            return []
    except Exception as e:
        print(f"❌ KDTree Error: {e}")
        return []

    for flight in flights:
        flight_pos = (flight["latitude"], flight["longitude"])

        # ✅ Find nearby balloons (~100 km radius)
        if len(balloon_positions) > 0:
            nearby_balloon_indices = balloon_tree.query_ball_point(flight_pos, 1.0)  # 1.0 ≈ 100 km

            for idx in nearby_balloon_indices:
                balloon = balloons[idx]
                altitude_diff = abs(flight["altitude"] - balloon["altitude"])

                if altitude_diff < 2000:  # Threshold for altitude risk
                    alert = {
                        "aircraft": flight["callsign"],
                        "latitude": flight["latitude"],
                        "longitude": flight["longitude"],
                        "altitude": flight["altitude"],
                        "risk": "⚠️ Possible Airspace Violation",
                        "distance_km": round(geodesic((balloon["latitude"], balloon["longitude"]), flight_pos).km, 2),
                        "altitude_diff": altitude_diff
                    }
                    alerts.append(alert)

    print(f"⚠️ {len(alerts)} risks detected.")
    return alerts

# ✅ API Routes
@app.route('/api/weather-data', methods=['GET'])
def get_weather_data():
    balloons = get_balloon_data()
    return jsonify(balloons)

@app.route('/api/flight-data', methods=['GET'])
def get_live_flights():
    flights = get_flight_data()
    return jsonify(flights)

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    balloons = get_balloon_data()
    flights = get_flight_data()
    alerts = detect_risks(flights, balloons)
    return jsonify(alerts)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
