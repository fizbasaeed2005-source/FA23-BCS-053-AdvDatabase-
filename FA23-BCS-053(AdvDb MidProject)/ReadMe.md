{
  "flight_updates": {
    "description": "Active flights being tracked",
    "fields": {
      "flight_id": "string (Primary Key)",
      "callsign": "string",
      "aircraft_type": "string",
      "tail_number": "string",
      "first_seen": "ISODate",
      "last_seen": "ISODate",
      "status": "string ('active' or 'completed')",
      "source_airport": "string (IATA code)",
      "destination_airport": "string (IATA code)",
      "updates": [
        {
          "lat": "number",
          "lon": "number",
          "altitude_m": "number",
          "spd_kts": "number",
          "heading": "number",
          "vertical_rate": "number",
          "ts": "ISODate",
          "receiver_id": "string"
        }
      ]
    }
  },
  ----------------------------------------------------
  "flight_logs": {
    "description": "Archived/completed flights",
    "fields": {
      "flight_id": "string (Primary Key)",
      "callsign": "string",
      "aircraft_type": "string",
      "tail_number": "string",
      "first_seen": "ISODate",
      "last_seen": "ISODate",
      "status": "string ('completed')",
      "source_airport": "string (IATA code)",
      "destination_airport": "string (IATA code)",
      "completed_at": "ISODate",
      "total_distance_km": "number",
      "updates": [
        {
          "lat": "number",
          "lon": "number",
          "altitude_m": "number",
          "spd_kts": "number",
          "heading": "number",
          "vertical_rate": "number",
          "ts": "ISODate",
          "receiver_id": "string"
        }
      ]
    }
  },
  --------------------------------------------------
  "airports": {
    "description": "List of airports",
    "fields": {
      "code": "string (Primary Key, IATA code)",
      "name": "string",
      "lat": "number",
      "lon": "number"
    }
  },
  ------------------------------------------------------
  "aircraft": {
    "description": "Aircraft information",
    "fields": {
      "tail_number": "string (Primary Key)",
      "airline": "string",
      "type": "string"
    }
  }
}
