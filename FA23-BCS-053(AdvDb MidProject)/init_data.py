from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client.flightaware_db

AIRPORTS = [
    {
        "code": "LHE",
        "name": "Allama Iqbal International Airport",
        "city": "Lahore",
        "country": "Pakistan",
        "lat": 31.5216,
        "lon": 74.4036
    },
    {
        "code": "ISB",
        "name": "Islamabad International Airport",
        "city": "Islamabad",
        "country": "Pakistan",
        "lat": 33.6217,
        "lon": 73.0551
    },
    {
        "code": "KHI",
        "name": "Jinnah International Airport",
        "city": "Karachi",
        "country": "Pakistan",
        "lat": 24.9060,
        "lon": 67.1600
    },
    {
        "code": "DXB",
        "name": "Dubai International Airport",
        "city": "Dubai",
        "country": "United Arab Emirates",
        "lat": 25.2532,
        "lon": 55.3657
    },
    {
        "code": "JFK",
        "name": "John F. Kennedy International Airport",
        "city": "New York",
        "country": "United States",
        "lat": 40.6413,
        "lon": -73.7781
    },
    {
        "code": "LHR",
        "name": "London Heathrow Airport",
        "city": "London",
        "country": "United Kingdom",
        "lat": 51.4700,
        "lon": -0.4543
    },
    {
        "code": "CDG",
        "name": "Charles de Gaulle Airport",
        "city": "Paris",
        "country": "France",
        "lat": 49.0097,
        "lon": 2.5479
    },
    {
        "code": "FRA",
        "name": "Frankfurt Airport",
        "city": "Frankfurt",
        "country": "Germany",
        "lat": 50.0379,
        "lon": 8.5622
    }
]


AIRCRAFT = [
    {
        "tail_number": "AP-BLD",
        "aircraft_type": "B737",
        "airline": "Pakistan International Airlines",
        "airline_code": "PIA",
        "manufacturer": "Boeing",
        "model": "737-800"
    },
    {
        "tail_number": "AP-BLE",
        "aircraft_type": "B777",
        "airline": "Pakistan International Airlines",
        "airline_code": "PIA",
        "manufacturer": "Boeing",
        "model": "777-300ER"
    },
    {
        "tail_number": "AP-BMG",
        "aircraft_type": "A320",
        "airline": "Pakistan International Airlines",
        "airline_code": "PIA",
        "manufacturer": "Airbus",
        "model": "A320-200"
    },
    {
        "tail_number": "A6-EUA",
        "aircraft_type": "A380",
        "airline": "Emirates",
        "airline_code": "EK",
        "manufacturer": "Airbus",
        "model": "A380-800"
    },
    {
        "tail_number": "A6-EPF",
        "aircraft_type": "A320",
        "airline": "Emirates",
        "airline_code": "EK",
        "manufacturer": "Airbus",
        "model": "A320-200"
    },
    {
        "tail_number": "G-ZBKA",
        "aircraft_type": "B787",
        "airline": "British Airways",
        "airline_code": "BA",
        "manufacturer": "Boeing",
        "model": "787-9"
    },
    {
        "tail_number": "G-CIVB",
        "aircraft_type": "B747",
        "airline": "British Airways",
        "airline_code": "BA",
        "manufacturer": "Boeing",
        "model": "747-400"
    },
    {
        "tail_number": "F-HPJA",
        "aircraft_type": "A380",
        "airline": "Air France",
        "airline_code": "AF",
        "manufacturer": "Airbus",
        "model": "A380-800"
    },
    {
        "tail_number": "F-GRHZ",
        "aircraft_type": "A319",
        "airline": "Air France",
        "airline_code": "AF",
        "manufacturer": "Airbus",
        "model": "A319-100"
    },
    {
        "tail_number": "D-ABYQ",
        "aircraft_type": "B747",
        "airline": "Lufthansa",
        "airline_code": "LH",
        "manufacturer": "Boeing",
        "model": "747-8"
    },
    {
        "tail_number": "D-AIXP",
        "aircraft_type": "A350",
        "airline": "Lufthansa",
        "airline_code": "LH",
        "manufacturer": "Airbus",
        "model": "A350-900"
    },
    {
        "tail_number": "N12345",
        "aircraft_type": "B777",
        "airline": "American Airlines",
        "airline_code": "AA",
        "manufacturer": "Boeing",
        "model": "777-200"
    },
    {
        "tail_number": "N54321",
        "aircraft_type": "A321",
        "airline": "American Airlines",
        "airline_code": "AA",
        "manufacturer": "Airbus",
        "model": "A321-200"
    }
]


def initialize_database():

    print("=" * 60)
    print("🚀 INITIALIZING FLIGHTAWARE DATABASE")
    print("=" * 60)

    print("\n🗑️  Clearing existing data...")
    db.airports.delete_many({})
    db.aircraft.delete_many({})
    print("✅ Existing data cleared")

    # Insert airports
    print("\n✈️  Inserting airports...")
    try:
        result = db.airports.insert_many(AIRPORTS)
        print(f"✅ Inserted {len(result.inserted_ids)} airports")
        for airport in AIRPORTS:
            print(f"   • {airport['code']} - {airport['name']}")
    except Exception as e:
        print(f"❌ Error inserting airports: {e}")

    print("\n🛩️  Inserting aircraft...")
    try:
        result = db.aircraft.insert_many(AIRCRAFT)
        print(f"✅ Inserted {len(result.inserted_ids)} aircraft")
        for aircraft in AIRCRAFT:
            print(f"   • {aircraft['tail_number']} - {aircraft['aircraft_type']} ({aircraft['airline']})")
    except Exception as e:
        print(f"❌ Error inserting aircraft: {e}")

    print("\n📊 Creating indexes...")
    try:
        db.airports.create_index([("code", 1)], unique=True)
        db.airports.create_index([("name", 1)])
        db.aircraft.create_index([("tail_number", 1)], unique=True)
        db.aircraft.create_index([("airline", 1)])
        print("✅ Indexes created successfully")
    except Exception as e:
        print(f"⚠️  Index creation warning: {e}")

    print("\n✅ VERIFICATION")
    print(f"   Total Airports: {db.airports.count_documents({})}")
    print(f"   Total Aircraft: {db.aircraft.count_documents({})}")

    print("\n" + "=" * 60)
    print("✅ DATABASE INITIALIZATION COMPLETE!")
    print("=" * 60)
    print("\n💡 You can now run: python app.py")


if __name__ == "__main__":
    initialize_database()