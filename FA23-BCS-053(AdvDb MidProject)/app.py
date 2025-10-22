from flask import jsonify
from flask_pymongo import PyMongo
from datetime import datetime, timedelta
import math
import requests
from flask import Flask, request, redirect, render_template_string


app = Flask(__name__)
app.config["MONGO_URI"] = "mongodb://localhost:27017/flightaware_db"
mongo = PyMongo(app)



def serialize_doc(doc):
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def is_near_airport(lat, lon, airport_code, threshold_km=50):
    db = mongo.db
    airport = db.airports.find_one({"code": airport_code})

    if not airport:
        return False

    distance = calculate_distance(lat, lon, airport['lat'], airport['lon'])
    return distance <= threshold_km


def should_archive_flight(flight):
    status = flight.get('status')
    if status == 'completed':
        return True

    updates = flight.get('updates', [])
    if not updates:
        return False

    last_update = updates[-1]
    altitude = last_update.get('altitude_m', 0)
    speed = last_update.get('spd_kts', 0)
    lat = last_update.get('lat')
    lon = last_update.get('lon')
    dest = flight.get('destination_airport')


    if altitude < 100 and speed < 50 and dest and is_near_airport(lat, lon, dest):
        return True


    last_seen = flight.get('last_seen')
    if last_seen:
        try:
            last_time = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
            if datetime.utcnow() - last_time > timedelta(hours=2):
                return True
        except:
            pass

    return False


def check_and_archive_flight(flight_id):
    db = mongo.db
    flight = db.flight_updates.find_one({"flight_id": flight_id})

    if not flight:
        return False

    if should_archive_flight(flight):
        updates = flight.get('updates', [])
        total_distance = 0
        for i in range(1, len(updates)):
            prev = updates[i - 1]
            curr = updates[i]
            total_distance += calculate_distance(
                prev['lat'], prev['lon'],
                curr['lat'], curr['lon']
            )

        flight['total_distance_km'] = round(total_distance, 2)
        flight['status'] = 'completed'
        flight['completed_at'] = datetime.utcnow().isoformat() + 'Z'

        db.flight_logs.insert_one(flight)
        db.flight_updates.delete_one({"flight_id": flight_id})
        print(f"✅ Archived flight: {flight_id}")
        return True

    return False


def validate_coordinates(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
        return -90 <= lat <= 90 and -180 <= lon <= 180
    except:
        return False


def validate_flight_data(data):
    errors = []

    required = ['flight_id', 'callsign', 'lat', 'lon', 'altitude_m', 'spd_kts', 'heading']
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return False, errors

    if not validate_coordinates(data['lat'], data['lon']):
        errors.append("Invalid coordinates (lat: -90 to 90, lon: -180 to 180)")

    try:
        altitude = float(data['altitude_m'])
        if altitude < 0 or altitude > 20000:
            errors.append("Invalid altitude (must be 0-20000 meters)")
    except:
        errors.append("Altitude must be a number")

    try:
        speed = float(data['spd_kts'])
        if speed < 0 or speed > 1000:
            errors.append("Invalid speed (must be 0-1000 knots)")
    except:
        errors.append("Speed must be a number")

    try:
        heading = float(data['heading'])
        if heading < 0 or heading > 360:
            errors.append("Invalid heading (must be 0-360 degrees)")
    except:
        errors.append("Heading must be a number")

    return len(errors) == 0, errors


def to_geojson_point(lat, lon, properties=None):
    return {
        "type": "Point",
        "coordinates": [float(lon), float(lat)],
        "properties": properties or {}
    }


def init_indexes():
    db = mongo.db

    db.flight_updates.create_index([("flight_id", 1)], unique=True)
    db.flight_updates.create_index([("status", 1)])
    db.flight_updates.create_index([("last_seen", -1)])
    db.flight_updates.create_index([("callsign", 1)])

    db.flight_logs.create_index([("flight_id", 1)])
    db.flight_logs.create_index([("completed_at", -1)])

    db.airports.create_index([("code", 1)], unique=True)
    db.airports.create_index([("name", 1)])

    db.aircraft.create_index([("tail_number", 1)], unique=True)
    db.aircraft.create_index([("airline", 1)])

    db.flight_updates.create_index([("updates.coordinates", "2dsphere")])

    print("✅ Indexes created successfully")

with app.app_context():
    try:
        init_indexes()
    except Exception as e:
        print(f"⚠️ Index initialization warning: {e}")


@app.route("/api/ingest", methods=["POST"])
def ingest_flight_data():
    try:
        data = request.get_json()

        is_valid, errors = validate_flight_data(data)
        if not is_valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        flight_id = data['flight_id']
        timestamp = datetime.utcnow().isoformat() + 'Z'

        update_entry = {
            "lat": float(data['lat']),
            "lon": float(data['lon']),
            "altitude_m": float(data['altitude_m']),
            "spd_kts": float(data['spd_kts']),
            "heading": float(data['heading']),
            "vertical_rate": data.get('vertical_rate', 0),
            "ts": timestamp,
            "receiver_id": data.get('receiver_id', 'UNKNOWN'),
            "coordinates": [float(data['lon']), float(data['lat'])]
        }

        db = mongo.db
        existing_flight = db.flight_updates.find_one({"flight_id": flight_id})

        if existing_flight:
            db.flight_updates.update_one(
                {"flight_id": flight_id},
                {
                    "$push": {"updates": update_entry},
                    "$set": {
                        "last_seen": timestamp,
                        "status": data.get('status', existing_flight.get('status', 'active')),
                        "source_airport": data.get("source", existing_flight.get("source_airport")),
                        "destination_airport": data.get("destination", existing_flight.get("destination_airport"))
                    }
                }
            )
            message = "Flight data updated"
        else:
            new_flight = {
                "flight_id": flight_id,
                "callsign": data['callsign'],
                "aircraft_type": data.get('aircraft_type', 'Unknown'),
                "tail_number": data.get('tail_number', 'N/A'),
                "first_seen": timestamp,
                "last_seen": timestamp,
                "status": data.get('status', 'active'),
                "source_airport": data.get("source", "Unknown"),
                "destination_airport": data.get("destination", "Unknown"),
                "updates": [update_entry]
            }
            db.flight_updates.insert_one(new_flight)
            message = "New flight tracked"

        check_and_archive_flight(flight_id)

        return jsonify({
            "success": True,
            "message": message,
            "flight_id": flight_id,
            "timestamp": timestamp
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/flights/batch-ingest", methods=["POST"])
def batch_ingest():

    try:
        data = request.get_json()
        updates = data.get('updates', [])

        if not updates:
            return jsonify({"error": "No updates provided"}), 400

        results = {
            "success": [],
            "failed": []
        }

        for update in updates:
            is_valid, errors = validate_flight_data(update)
            if is_valid:
                try:
                    flight_id = update['flight_id']
                    timestamp = datetime.utcnow().isoformat() + 'Z'

                    update_entry = {
                        "lat": float(update['lat']),
                        "lon": float(update['lon']),
                        "altitude_m": float(update['altitude_m']),
                        "spd_kts": float(update['spd_kts']),
                        "heading": float(update['heading']),
                        "vertical_rate": update.get('vertical_rate', 0),
                        "ts": timestamp,
                        "receiver_id": update.get('receiver_id', 'UNKNOWN'),
                        "coordinates": [float(update['lon']), float(update['lat'])]
                    }

                    db = mongo.db
                    existing = db.flight_updates.find_one({"flight_id": flight_id})

                    if existing:
                        db.flight_updates.update_one(
                            {"flight_id": flight_id},
                            {"$push": {"updates": update_entry}, "$set": {"last_seen": timestamp}}
                        )
                    else:
                        new_flight = {
                            "flight_id": flight_id,
                            "callsign": update['callsign'],
                            "aircraft_type": update.get('aircraft_type', 'Unknown'),
                            "tail_number": update.get('tail_number', 'N/A'),
                            "first_seen": timestamp,
                            "last_seen": timestamp,
                            "status": update.get('status', 'active'),
                            "source_airport": update.get("source", "Unknown"),
                            "destination_airport": update.get("destination", "Unknown"),
                            "updates": [update_entry]
                        }
                        db.flight_updates.insert_one(new_flight)

                    results["success"].append(flight_id)
                except Exception as e:
                    results["failed"].append({"flight_id": update.get('flight_id'), "error": str(e)})
            else:
                results["failed"].append({
                    "flight_id": update.get('flight_id'),
                    "errors": errors
                })

        return jsonify({
            "total": len(updates),
            "successful": len(results["success"]),
            "failed": len(results["failed"]),
            "details": results
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/track/<flight_id>", methods=["GET"])
def track_flight_api(flight_id):

    try:
        db = mongo.db

        flight = db.flight_updates.find_one({"flight_id": flight_id})
        source = "active"

        if not flight:
            flight = db.flight_logs.find_one({"flight_id": flight_id})
            source = "archived"

        if not flight:
            return jsonify({"error": f"Flight {flight_id} not found"}), 404

        time_param = request.args.get('time')
        updates = flight.get('updates', [])

        if time_param and updates:
            try:
                requested_time = datetime.fromisoformat(time_param.replace('Z', '+00:00'))
                closest_update = min(
                    updates,
                    key=lambda x: abs(datetime.fromisoformat(x['ts'].replace('Z', '+00:00')) - requested_time)
                )
                location = closest_update
            except:
                location = updates[-1] if updates else None
        else:
            location = updates[-1] if updates else None

        use_geojson = request.args.get('format') == 'geojson'

        if use_geojson and location:
            current_location = to_geojson_point(
                location['lat'],
                location['lon'],
                {
                    "altitude_m": location.get('altitude_m'),
                    "spd_kts": location.get('spd_kts'),
                    "heading": location.get('heading'),
                    "timestamp": location.get('ts')
                }
            )
        else:
            current_location = location

        response = {
            "flight_id": flight.get('flight_id'),
            "callsign": flight.get('callsign'),
            "aircraft_type": flight.get('aircraft_type'),
            "tail_number": flight.get('tail_number'),
            "status": flight.get('status'),
            "source": source,
            "source_airport": flight.get('source_airport'),
            "destination_airport": flight.get('destination_airport'),
            "first_seen": flight.get('first_seen'),
            "last_seen": flight.get('last_seen'),
            "total_updates": len(updates),
            "total_distance_km": flight.get('total_distance_km'),
            "current_location": current_location,
            "all_updates": updates if request.args.get('full') == 'true' else None
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/flights", methods=["GET"])
def list_flights():

    try:
        db = mongo.db
        status_filter = request.args.get('status', 'all')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        if status_filter == 'active':
            flights = list(db.flight_updates.find({}, {'_id': 0}).skip(offset).limit(limit))
            return jsonify({"flights": flights, "count": len(flights)}), 200
        elif status_filter == 'completed':
            flights = list(db.flight_logs.find({}, {'_id': 0}).skip(offset).limit(limit))
            return jsonify({"flights": flights, "count": len(flights)}), 200
        else:
            active = list(db.flight_updates.find({}, {'_id': 0}).skip(offset).limit(limit))
            archived = list(db.flight_logs.find({}, {'_id': 0}).skip(offset).limit(limit))
            return jsonify({
                "active_flights": active,
                "archived_flights": archived,
                "total": len(active) + len(archived)
            }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/flights/active", methods=["GET"])
def active_flights():
    try:
        db = mongo.db
        flights = list(db.flight_updates.find({}, {'_id': 0}))
        return jsonify({"active_flights": flights, "count": len(flights)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/flights/nearby", methods=["GET"])
def nearby_flights():

    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        radius_km = float(request.args.get('radius_km', 100))

        db = mongo.db
        flights = list(db.flight_updates.find({}, {'_id': 0}))

        nearby = []
        for flight in flights:
            updates = flight.get('updates', [])
            if updates:
                last = updates[-1]
                distance = calculate_distance(lat, lon, last['lat'], last['lon'])
                if distance <= radius_km:
                    flight['distance_km'] = round(distance, 2)
                    nearby.append(flight)

        nearby.sort(key=lambda x: x['distance_km'])

        return jsonify({
            "location": {"lat": lat, "lon": lon},
            "radius_km": radius_km,
            "flights": nearby,
            "count": len(nearby)
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/statistics", methods=["GET"])
def statistics():
    try:
        db = mongo.db

        total_active = db.flight_updates.count_documents({})
        total_completed = db.flight_logs.count_documents({})

        completed = list(db.flight_logs.find({}, {'_id': 0}))
        durations = []
        total_dist = 0
        for flight in completed:
            try:
                first = datetime.fromisoformat(flight['first_seen'].replace('Z', '+00:00'))
                last = datetime.fromisoformat(flight['last_seen'].replace('Z', '+00:00'))
                duration = (last - first).total_seconds() / 3600  # hours
                durations.append(duration)
                total_dist += flight.get('total_distance_km', 0)
            except:
                pass

        avg_duration = sum(durations) / len(durations) if durations else 0
        avg_distance = total_dist / len(completed) if completed else 0

        return jsonify({
            "total_flights": total_active + total_completed,
            "active_flights": total_active,
            "completed_flights": total_completed,
            "average_flight_duration_hours": round(avg_duration, 2),
            "average_flight_distance_km": round(avg_distance, 2)
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/archive/<flight_id>", methods=["POST"])
def manual_archive(flight_id):
    try:
        archived = check_and_archive_flight(flight_id)
        if archived:
            return jsonify({
                "success": True,
                "message": f"Flight {flight_id} archived"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": f"Flight {flight_id} not found or already archived"
            }), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/airports", methods=["GET"])
def list_airports():
    try:
        db = mongo.db
        airports = list(db.airports.find({}, {'_id': 0}))
        return jsonify({"airports": airports, "count": len(airports)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/airports/<code>", methods=["GET"])
def get_airport(code):
    try:
        db = mongo.db
        airport = db.airports.find_one({"code": code.upper()}, {'_id': 0})

        if not airport:
            return jsonify({"error": f"Airport {code} not found"}), 404

        return jsonify(airport), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route("/api/aircraft", methods=["GET"])
def list_aircraft():

    try:
        db = mongo.db
        aircraft = list(db.aircraft.find({}, {'_id': 0}))
        return jsonify({"aircraft": aircraft, "count": len(aircraft)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/aircraft/<tail_number>", methods=["GET"])
def get_aircraft(tail_number):

    try:
        db = mongo.db
        aircraft = db.aircraft.find_one({"tail_number": tail_number.upper()}, {'_id': 0})

        if not aircraft:
            return jsonify({"error": f"Aircraft {tail_number} not found"}), 404

        return jsonify(aircraft), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

#WEB INTERFACE

@app.route("/")
def home():
    return '''                          
    <html>
    <head>
        <title>FlightAware Tracker</title>
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                text-align: center;
                padding: 50px;
                margin: 0;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                max-width: 500px;
                margin: auto;
            }
            h2 { color: #667eea; margin-bottom: 10px; }
            p { color: #666; margin-bottom: 30px; }
            input {
                padding: 12px; 
                width: 80%; 
                border-radius: 8px; 
                border: 2px solid #ddd;
                font-size: 16px;
                margin-bottom: 15px;
            }
            button {
                padding: 12px 30px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border: none;
                color: white;
                border-radius: 8px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
            }
            button:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102,126,234,0.4); }
            .links { margin-top: 30px; }
            .links a { 
                color: #667eea; 
                text-decoration: none; 
                margin: 0 15px;
                font-weight: 500;
            }
            .links a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✈️ FlightAware Tracker</h2>
            <p>Track any flight in real-time</p>
            <form action="/track" method="get">
                <input type="text" name="flight_id" placeholder="Enter Flight ID (e.g. PK301-2025-10-21)" required>
                <br>
                <button type="submit">Track Flight</button>
            </form>
            <div class="links">
                <a href="/all-flights">✈️ All Flights</a>
                <a href="/api/statistics">📊 Statistics</a>
            </div>
        </div>
    </body>
    </html>
    '''


@app.route("/track", methods=["GET"])
def track_flight_web():
    flight_id = request.args.get("flight_id")
    if not flight_id:
        return redirect("/")

    flight_id = flight_id.strip().upper()
    api_url = f"http://127.0.0.1:5000/api/track/{flight_id}?full=true"
    response = requests.get(api_url)

    if response.status_code != 200:
        return f"""
        <html><head><title>Not Found</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h3>❌ No record found for flight <b>{flight_id}</b></h3>
            <a href="/" style="color: #667eea;">← Go Back</a>
        </body>
        </html>
        """

    flight = response.json()
    updates = flight.get("all_updates", [])
    first_seen = flight.get("first_seen", "N/A")
    last_seen = flight.get("last_seen", "N/A")
    status = flight.get("status", "N/A")
    source_airport = flight.get("source_airport", "N/A")
    destination_airport = flight.get("destination_airport", "N/A")
    callsign = flight.get("callsign", "N/A")
    aircraft_type = flight.get("aircraft_type", "N/A")
    tail_number = flight.get("tail_number", "N/A")

    html_template = """
    <html>
    <head>
        <title>Flight Info - {{ flight_id }}</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background-color: #f0f2f5; padding: 40px; }
            .card { background: white; border-radius: 15px; padding: 30px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); max-width: 700px; margin: auto; }
            h2 { color: #667eea; margin-bottom: 20px; }
            .info { text-align: left; margin-top: 15px; }
            .info p { margin: 10px 0; color: #333; }
            .latest { background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 20px; border-radius: 10px; margin-top: 20px; }
            .latest h3 { color: #1976d2; margin-top: 0; }
            button { padding: 12px 30px; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); border: none; color: white; border-radius: 8px; cursor: pointer; margin-top: 20px; font-size: 16px; font-weight: bold; }
            button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(40,167,69,0.4); }
            a { text-decoration: none; color: #667eea; font-weight: 500; }
            a:hover { text-decoration: underline; }
            .badge { display: inline-block; padding: 5px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; margin-left: 10px; }
            .badge.active { background: #d4edda; color: #155724; }
            .badge.completed { background: #cce5ff; color: #004085; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>✈️ Flight Information</h2>
            <div class="info">
                <p><b>Flight ID:</b> {{ flight_id }}</p>
                <p><b>Callsign:</b> {{ callsign }}</p>
                <p><b>Aircraft Type:</b> {{ aircraft_type }}</p>
                <p><b>Tail Number:</b> {{ tail_number }}</p>
                <p><b>Status:</b> {{ status }} 
                    <span class="badge {{ status.lower() }}">{{ status.upper() }}</span>
                </p>
                <p><b>Source Airport:</b> {{ source_airport }}</p>
                <p><b>Destination Airport:</b> {{ destination_airport }}</p>
                <p><b>First Seen:</b> {{ first_seen }}</p>
                <p><b>Last Seen:</b> {{ last_seen }}</p>
                <p><b>Total Updates:</b> {{ updates|length }}</p>
            </div>

            {% if updates %}
            <div class="latest">
                <h3>📍 Latest Position</h3>
                <p><b>Latitude:</b> {{ updates[-1].lat }}°</p>
                <p><b>Longitude:</b> {{ updates[-1].lon }}°</p>
                <p><b>Altitude:</b> {{ updates[-1].altitude_m }} m</p>
                <p><b>Speed:</b> {{ updates[-1].spd_kts }} knots</p>
                <p><b>Heading:</b> {{ updates[-1].heading }}°</p>
                <p><b>Receiver:</b> {{ updates[-1].receiver_id or 'N/A' }}</p>
                <p><b>Time:</b> {{ updates[-1].ts }}</p>
            </div>
            {% endif %}

            <form action="/map/{{ flight_id }}" method="get">
                <button type="submit">🗺️ VIEW ON MAP</button>
            </form>
            <p style="margin-top: 20px;">
                <a href="/">← Track another flight</a> | 
                <a href="/api/track/{{ flight_id }}" target="_blank">View JSON</a>
            </p>
        </div>
    </body>
    </html>
    """

    return render_template_string(html_template,
                                  flight_id=flight_id,
                                  callsign=callsign,
                                  aircraft_type=aircraft_type,
                                  tail_number=tail_number,
                                  status=status,
                                  source_airport=source_airport,
                                  destination_airport=destination_airport,
                                  first_seen=first_seen,
                                  last_seen=last_seen,
                                  updates=updates)




@app.route("/map/<flight_id>")
def show_map(flight_id):
    db = mongo.db
    flight = db.flight_updates.find_one({"flight_id": flight_id}) or db.flight_logs.find_one({"flight_id": flight_id})
    if not flight:
        return f"<h3>❌ No record found for flight {flight_id}</h3>"

    updates = flight.get("updates", [])
    if not updates:
        return f"<h3>❌ No updates available for flight {flight_id}</h3>"

    start_lat = updates[0]['lat']
    start_lon = updates[0]['lon']
    callsign = flight.get('callsign', 'N/A')
    source_airport = flight.get('source_airport', 'N/A')
    dest_airport = flight.get('destination_airport', 'N/A')

    return f"""
    <html>
    <head>
        <title>Flight Path - {flight_id}</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
        <style>
            body {{ margin: 0; padding: 0; font-family: 'Segoe UI', sans-serif; }}
            h3 {{ text-align: center; color: #333; margin: 10px 0; }}
            #map {{ width: 100%; height: 90vh; }}
            a {{ text-decoration: none; color: #667eea; font-weight: 500; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <h3>🗺️ Flight Path for {flight_id} ({callsign}) 🗺️</h3>
        <p style="text-align: center;">
            Source: {source_airport} | Destination: {dest_airport} <br>
            <a href="/track?flight_id={flight_id}">← Back to Flight Info</a>
        </p>
        <div id="map"></div>

        <script>
        let map = L.map('map').setView([{start_lat}, {start_lon}], 6);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19 }}).addTo(map);

        let flightPath = L.polyline([], {{color: 'blue', weight: 4}}).addTo(map);
        let markers = [];

        async function fetchUpdates() {{
            let res = await fetch('/api/track/{flight_id}?full=true');
            let data = await res.json();
            if (!data.all_updates) return;

            flightPath.setLatLngs([]);
            markers.forEach(m => map.removeLayer(m));
            markers = [];

            let updates = data.all_updates;
            let minAlt = Math.min(...updates.map(u => u.altitude_m));
            let maxAlt = Math.max(...updates.map(u => u.altitude_m));

            for (let i = 0; i < updates.length; i++) {{
                let u = updates[i];
                let tsVal = u.ts ? new Date(u.ts).toLocaleString() : "N/A";

                if (i > 0) {{
                    let ratio = (u.altitude_m - minAlt) / (maxAlt - minAlt + 0.001);
                    let color = ratio < 0.5 
                        ? 'rgb(' + Math.floor(255*ratio*2) + ',255,0)'
                        : 'rgb(255,' + Math.floor(255*(1-(ratio-0.5)*2)) + ',0)';
                    L.polyline([[updates[i-1].lat, updates[i-1].lon],[u.lat,u.lon]], {{color: color, weight:4}}).addTo(map);
                }}

                let markerColor = i == 0 ? 'green' : (i == updates.length-1 ? 'red' : 'blue');
                let marker = L.circleMarker([u.lat,u.lon], {{
                    radius: 5,
                    color: markerColor,
                    fillColor: markerColor,
                    fillOpacity: 0.8
                }}).bindPopup(
                    "<b>Time:</b> " + tsVal +
                    "<br><b>Alt:</b> " + u.altitude_m + " m" +
                    "<br><b>Speed:</b> " + u.spd_kts + " kt" +
                    "<br><b>Receiver:</b> " + (u.receiver_id || "N/A")
                );
                marker.addTo(map);
                markers.push(marker);

                flightPath.addLatLng([u.lat,u.lon]);
            }}
        }}

        setInterval(fetchUpdates, 5000);
        fetchUpdates();
        </script>
    </body>
    </html>
    """


@app.route("/all-flights")
def all_flights_web():
    # Call the API instead of querying MongoDB directly
    api_url = "http://127.0.0.1:5000/api/flights"
    response = requests.get(api_url)
    data = response.json()

    active = data.get("active_flights", [])
    archived = data.get("archived_flights", [])

    html_template = """
    <html>
    <head>
        <title>All Flights</title>
        <style>
            body { font-family: Arial; padding: 40px; background: #f0f2f5; }
            .container { max-width: 1000px; margin: auto; }
            h2 { color: #667eea; }
            table { width: 100%; background: white; border-radius: 10px; overflow: hidden; margin: 20px 0; }
            th { background: #667eea; color: white; padding: 15px; text-align: left; }
            td { padding: 12px 15px; border-bottom: 1px solid #eee; }
            tr:hover { background: #f8f9fa; }
            a { color: #667eea; text-decoration: none; font-weight: bold; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✈️ Active Flights</h2>
            <table>
                <tr><th>Flight ID</th><th>Callsign</th><th>Aircraft</th><th>Status</th><th>Last Seen</th><th>Actions</th></tr>
                {% for f in active %}
                <tr>
                    <td>{{ f.flight_id }}</td>
                    <td>{{ f.callsign }}</td>
                    <td>{{ f.aircraft_type }}</td>
                    <td>{{ f.status }}</td>
                    <td>{{ f.last_seen }}</td>
                    <td><a href="/track?flight_id={{ f.flight_id }}">Track</a></td>
                </tr>
                {% endfor %}
            </table>

            <h2>📦 Archived Flights</h2>
            <table>
                <tr><th>Flight ID</th><th>Callsign</th><th>Aircraft</th><th>Status</th><th>Last Seen</th><th>Actions</th></tr>
                {% for f in archived %}
                <tr>
                    <td>{{ f.flight_id }}</td>
                    <td>{{ f.callsign }}</td>
                    <td>{{ f.aircraft_type }}</td>
                    <td>{{ f.status }}</td>
                    <td>{{ f.last_seen }}</td>
                    <td><a href="/track?flight_id={{ f.flight_id }}">View</a></td>
                </tr>
                {% endfor %}
            </table>
            <p><a href="/">← Back to Home</a></p>
        </div>
    </body>
    </html>
    """

    return render_template_string(html_template, active=active, archived=archived)


if __name__ == "__main__":
    app.run(debug=True)