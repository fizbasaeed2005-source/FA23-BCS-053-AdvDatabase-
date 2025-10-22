import requests
from datetime import datetime, timedelta
import time
import random
import math

API_URL = "http://127.0.0.1:5000/api/ingest"

AIRPORTS = {
    "LHE": {"lat": 31.5216, "lon": 74.4036, "name": "Allama Iqbal International Airport"},
    "ISB": {"lat": 33.6217, "lon": 73.0551, "name": "Islamabad International Airport"},
    "KHI": {"lat": 24.9060, "lon": 67.1600, "name": "Jinnah International Airport"},
    "DXB": {"lat": 25.2532, "lon": 55.3657, "name": "Dubai International Airport"},
    "JFK": {"lat": 40.6413, "lon": -73.7781, "name": "John F. Kennedy International Airport"},
    "LHR": {"lat": 51.4700, "lon": -0.4543, "name": "London Heathrow Airport"},
    "CDG": {"lat": 49.0097, "lon": 2.5479, "name": "Charles de Gaulle Airport"},
    "FRA": {"lat": 50.0379, "lon": 8.5622, "name": "Frankfurt Airport"}
}

AIRCRAFT_TYPES = ["B737", "A320", "B777", "A380", "B787", "A350"]

AIRLINES = {
    "PIA": "Pakistan International Airlines",
    "EK": "Emirates",
    "BA": "British Airways",
    "AF": "Air France",
    "LH": "Lufthansa",
    "AA": "American Airlines"
}


def calculate_distance(lat1, lon1, lat2, lon2):

    R = 6371

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def calculate_bearing(lat1, lon1, lat2, lon2):
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)

    x = math.sin(delta_lon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)

    bearing = math.atan2(x, y)
    bearing = math.degrees(bearing)
    bearing = (bearing + 360) % 360

    return bearing


class RealisticFlightSimulator:

    def __init__(self, flight_id, callsign, source_code, dest_code, aircraft_type, tail_number, start_time):
        self.flight_id = flight_id
        self.callsign = callsign
        self.source_code = source_code
        self.dest_code = dest_code
        self.aircraft_type = aircraft_type
        self.tail_number = tail_number
        self.start_time = start_time

        source = AIRPORTS[source_code]
        dest = AIRPORTS[dest_code]

        self.start_lat = source["lat"]
        self.start_lon = source["lon"]
        self.dest_lat = dest["lat"]
        self.dest_lon = dest["lon"]

        self.total_distance = calculate_distance(
            self.start_lat, self.start_lon,
            self.dest_lat, self.dest_lon
        )
        self.bearing = calculate_bearing(
            self.start_lat, self.start_lon,
            self.dest_lat, self.dest_lon
        )

        if self.total_distance < 1000:  # Short haul
            self.cruise_altitude = random.randint(8000, 10000)
            self.cruise_speed = random.randint(400, 500)
            self.num_updates = random.randint(8, 12)
        elif self.total_distance < 3000:  # Medium haul
            self.cruise_altitude = random.randint(10000, 12000)
            self.cruise_speed = random.randint(450, 550)
            self.num_updates = random.randint(12, 18)
        else:  # Long haul
            self.cruise_altitude = random.randint(11000, 13000)
            self.cruise_speed = random.randint(500, 600)
            self.num_updates = random.randint(18, 25)

        self.current_lat = self.start_lat
        self.current_lon = self.start_lon
        self.current_altitude = 0
        self.current_speed = 0

        print(f"\n🛫 Flight {self.flight_id} ({self.callsign})")
        print(f"   Route: {source_code} → {dest_code}")
        print(f"   Distance: {self.total_distance:.0f} km")
        print(f"   Aircraft: {aircraft_type} ({tail_number})")
        print(f"   Updates: {self.num_updates}")

    def get_phase(self, update_num):

        takeoff_end = int(self.num_updates * 0.15)
        landing_start = int(self.num_updates * 0.85)

        if update_num <= takeoff_end:
            return "TAKEOFF"
        elif update_num >= landing_start:
            return "LANDING"
        else:
            return "CRUISE"

    def calculate_next_position(self, update_num):
        phase = self.get_phase(update_num)

        progress = update_num / (self.num_updates - 1)

        self.current_lat = self.start_lat + (self.dest_lat - self.start_lat) * progress
        self.current_lon = self.start_lon + (self.dest_lon - self.start_lon) * progress

        self.current_lat += random.uniform(-0.01, 0.01)
        self.current_lon += random.uniform(-0.01, 0.01)

        if phase == "TAKEOFF":

            climb_progress = update_num / (self.num_updates * 0.15)
            self.current_altitude = int(self.cruise_altitude * climb_progress)
            self.current_speed = int(150 + (self.cruise_speed - 150) * climb_progress)
            vertical_rate = random.randint(1500, 2500)

        elif phase == "LANDING":
            landing_progress = (update_num - self.num_updates * 0.85) / (self.num_updates * 0.15)
            self.current_altitude = int(self.cruise_altitude * (1 - landing_progress))
            self.current_speed = int(self.cruise_speed - (self.cruise_speed - 150) * landing_progress)
            vertical_rate = random.randint(-2000, -1000)

        else:
            self.current_altitude = self.cruise_altitude + random.randint(-100, 100)
            self.current_speed = self.cruise_speed + random.randint(-20, 20)
            vertical_rate = random.randint(-50, 50)

        self.current_altitude = max(0, self.current_altitude)

        current_heading = self.bearing + random.uniform(-10, 10)
        current_heading = current_heading % 360

        return {
            "lat": round(self.current_lat, 4),
            "lon": round(self.current_lon, 4),
            "altitude": self.current_altitude,
            "speed": self.current_speed,
            "heading": round(current_heading, 1),
            "vertical_rate": vertical_rate,
            "phase": phase
        }

    def generate_and_send_updates(self, delay_between_updates=0.5):
        for i in range(self.num_updates):
            position = self.calculate_next_position(i)

            if i == self.num_updates - 1:
                status = "completed"
            else:
                status = "active"


            timestamp = (self.start_time + timedelta(minutes=i * 5)).isoformat() + 'Z'
            data = {
                "flight_id": self.flight_id,
                "callsign": self.callsign,
                "lat": position["lat"],
                "lon": position["lon"],
                "altitude_m": position["altitude"],
                "spd_kts": position["speed"],
                "heading": position["heading"],
                "vertical_rate": position["vertical_rate"],
                "status": status,
                "receiver_id": f"R-{self.source_code}-{random.randint(1, 5):03d}",
                "source": self.source_code,
                "destination": self.dest_code,
                "aircraft_type": self.aircraft_type,
                "tail_number": self.tail_number
            }

            try:
                response = requests.post(API_URL, json=data, timeout=5)

                if response.status_code in [200, 201]:
                    phase_emoji = {
                        "TAKEOFF": "🛫",
                        "CRUISE": "✈️",
                        "LANDING": "🛬"
                    }
                    print(f"   {phase_emoji.get(position['phase'], '✈️')} Update {i + 1}/{self.num_updates} "
                          f"[{position['phase']}] - Alt: {position['altitude']}m, Spd: {position['speed']}kts")
                else:
                    try:
                        error = response.json()
                    except:
                        error = response.text
                    print(f"   ❌ Error ({response.status_code}): {error}")

            except requests.exceptions.RequestException as e:
                print(f"   ❌ Connection error: {e}")
                print(f"   💡 Make sure Flask server is running at {API_URL}")
                return False

            if i < self.num_updates - 1:
                time.sleep(delay_between_updates)

        print(f"   ✅ Flight {self.flight_id} completed!\n")
        return True


def generate_random_flights(num_flights=5):
    flights = []

    airport_codes = list(AIRPORTS.keys())
    airline_codes = list(AIRLINES.keys())

    for i in range(num_flights):
        source = random.choice(airport_codes)
        dest = random.choice([code for code in airport_codes if code != source])

        airline = random.choice(airline_codes)
        flight_number = random.randint(100, 999)

        flight_id = f"{airline}{flight_number}-{datetime.now().strftime('%Y-%m-%d')}"
        callsign = f"{airline}{flight_number}"
        aircraft_type = random.choice(AIRCRAFT_TYPES)
        tail_number = f"{airline}-{random.randint(100, 999)}"

        start_time = datetime.utcnow() - timedelta(minutes=random.randint(0, 120))

        flight = RealisticFlightSimulator(
            flight_id=flight_id,
            callsign=callsign,
            source_code=source,
            dest_code=dest,
            aircraft_type=aircraft_type,
            tail_number=tail_number,
            start_time=start_time
        )

        flights.append(flight)

    return flights


def main():
    print("=" * 60)
    print("🌍 FLIGHTAWARE MOCK FLIGHT SIMULATOR")
    print("=" * 60)

    try:
        response = requests.get("http://127.0.0.1:5000/", timeout=2)
        print("✅ Flask server is running\n")
    except:
        print("❌ ERROR: Flask server is not running!")
        print("   Please start the Flask app first: python app.py")
        return

    try:
        num_flights = int(input("How many flights to simulate? (1-20): "))
        num_flights = max(1, min(20, num_flights))
    except:
        num_flights = 5
        print(f"Using default: {num_flights} flights")

    try:
        delay = float(input("Delay between updates in seconds? (0.1-5.0): "))
        delay = max(0.1, min(5.0, delay))
    except:
        delay = 0.5
        print(f"Using default: {delay}s delay")

    print()
    flights = generate_random_flights(num_flights)

    successful = 0
    for flight in flights:
        if flight.generate_and_send_updates(delay_between_updates=delay):
            successful += 1

    print("=" * 60)
    print(f"✅ SIMULATION COMPLETE: {successful}/{len(flights)} flights")
    print("=" * 60)
    print("\n💡 View flights at: http://127.0.0.1:5000/all-flights")
    print("💡 API docs at: http://127.0.0.1:5000/api-docs")


if __name__ == "__main__":
    main()