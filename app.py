from flask import Flask, jsonify, request
import requests
import os

app = Flask(__name__)

# ---------------- CONFIGURATION ----------------
OWNER = os.environ.get("OWNER")
PRIMARY_API_URL = os.environ.get("PRIMARY_API_URL")
SECONDARY_API_URL = os.environ.get("SECONDARY_API_URL")
SECONDARY_API_KEY = os.environ.get("SECONDARY_API_KEY")

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "owner": OWNER,
        "config": "loaded"
    })

@app.route("/")
def home():
    return jsonify({
        "api": "Vehicle Merge API",
        "status": "running",
        "owner": OWNER,
        "endpoints": {
            "/vehicle-merge?reg=<vehicle_no>": "Merge APIs using query parameter",
            "/health": "Health check"
        }
    })

@app.route("/vehicle-merge")
def vehicle_merge():
    vehicle_no = request.args.get('reg')

    if not vehicle_no:
        return jsonify({
            "success": False,
            "error": "Missing 'reg' query parameter",
            "example": "/vehicle-merge?reg=UP63BJ8585"
        }), 400

    primary_response = None
    secondary_response = None

    # -------- PRIMARY API --------
    try:
        primary_url = f"{PRIMARY_API_URL}?rc={vehicle_no}"
        p = requests.get(primary_url, timeout=8)

        if p.status_code == 200:
            primary_response = p.json()
        else:
            primary_response = {
                "error": f"Primary API returned status {p.status_code}",
                "status_code": p.status_code
            }
    except Exception as e:
        primary_response = {
            "error": "Primary API failed",
            "details": str(e)
        }

    # -------- SECONDARY API --------
    try:
        secondary_url = f"{SECONDARY_API_URL}?reg={vehicle_no}&key={SECONDARY_API_KEY}"
        s = requests.get(secondary_url, timeout=8)

        if s.status_code == 200:
            secondary_response = s.json()
        else:
            secondary_response = {
                "error": f"Secondary API returned status {s.status_code}",
                "status_code": s.status_code
            }
    except Exception as e:
        secondary_response = {
            "error": "Secondary API failed",
            "details": str(e)
        }

    return jsonify({
        "owner": OWNER,
        "primary": primary_response,
        "secondary": secondary_response,
        "vehicle": vehicle_no
    })

if __name__ == "__main__":
    app.run(debug=True)

