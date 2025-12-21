from flask import Flask, jsonify, request
import requests
import os

app = Flask(__name__)

# ---------------- CONFIGURATION ----------------
OWNER = os.environ.get("OWNER")
PRIMARY_API_URL = os.environ.get("PRIMARY_API_URL")

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
            "/vehicle-merge?reg=<vehicle_no>": "Get vehicle details",
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

    # -------- PRIMARY API ONLY --------
    try:
        primary_url = f"{PRIMARY_API_URL}?rc={vehicle_no}"
        response = requests.get(primary_url, timeout=8)

        if response.status_code == 200:
            api_response = response.json()
            
            # Return the API response as is if successful
            return jsonify({
                "owner": OWNER,
                "success": True,
                "vehicle": vehicle_no,
                "data": api_response
            })
        else:
            # Don't expose the API URL, just show status code
            return jsonify({
                "owner": OWNER,
                "success": False,
                "vehicle": vehicle_no,
                "error": f"External API returned status code {response.status_code}",
                "status_code": response.status_code
            }), 502  # Bad Gateway
    
    except requests.exceptions.Timeout:
        return jsonify({
            "owner": OWNER,
            "success": False,
            "vehicle": vehicle_no,
            "error": "External API request timeout",
            "message": "The request took too long to process"
        }), 504  # Gateway Timeout
    
    except requests.exceptions.ConnectionError:
        return jsonify({
            "owner": OWNER,
            "success": False,
            "vehicle": vehicle_no,
            "error": "Connection error",
            "message": "Could not connect to the external service"
        }), 503  # Service Unavailable
    
    except Exception as e:
        # Generic error - don't expose internal details
        return jsonify({
            "owner": OWNER,
            "success": False,
            "vehicle": vehicle_no,
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }), 500

if __name__ == "__main__":
    app.run(debug=True)