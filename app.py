from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import requests
import re
import asyncio
import httpx
from functools import wraps

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36",
    "Referer": "https://vahanx.in/",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br"
}

# ---------- Helper functions for RC info ----------
def extract_card(soup, label):
    """Extract value from card by label"""
    for div in soup.select(".hrcd-cardbody"):
        span = div.find("span")
        if span and label.lower() in span.text.lower():
            return div.find("p").get_text(strip=True)
    return ""

def extract_from_section(soup, header_text, keys):
    """Extract data from a specific section"""
    section = soup.find("h3", string=lambda s: s and header_text.lower() in s.lower())
    section_card = section.find_parent("div", class_="hrc-details-card") if section else None
    result = {}
    for key in keys:
        span = section_card.find("span", string=lambda s: s and key in s) if section_card else None
        if span:
            val = span.find_next("p")
            result[key.lower().replace(" ", "_")] = val.get_text(strip=True) if val else ""
    return result

# ---------- RC Info Endpoint ----------
@app.route("/api/vehicle-info", methods=["GET"])
def get_vehicle_info():
    rc = request.args.get("rc")
    if not rc:
        return jsonify({"error": "Missing rc parameter"}), 400

    try:
        url = f"https://vahanx.in/rc-search/{rc}"
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        registration_number = soup.find("h1").text.strip()
        modal_name = extract_card(soup, "Modal Name")
        owner_name = extract_card(soup, "Owner Name")
        code = extract_card(soup, "Code")
        city = extract_card(soup, "City Name")
        phone = extract_card(soup, "Phone")
        website = extract_card(soup, "Website")
        address = extract_card(soup, "Address")

        ownership = extract_from_section(soup, "Ownership Details", [
            "Owner Name", "Owner Serial No", "Registration Number", "Registered RTO"
        ])

        vehicle = extract_from_section(soup, "Vehicle Details", [
            "Model Name", "Maker Model", "Vehicle Class", "Fuel Type", "Fuel Norms"
        ])

        insurance_expired_box = soup.select_one(".insurance-alert-box.expired .title")
        expired_days = int(re.search(r"(\d+)", insurance_expired_box.text).group(1)) if insurance_expired_box else None
        insurance_data = extract_from_section(soup, "Insurance Information", ["Insurance Expiry"])
        insurance = {
            "status": "Expired" if insurance_expired_box else "Active",
            "expiry_date": insurance_data.get("insurance_expiry", ""),
            "expired_days_ago": expired_days
        }

        validity = extract_from_section(soup, "Important Dates", [
            "Registration Date", "Vehicle Age", "Fitness Upto", "Insurance Upto", "Insurance Expiry In"
        ])

        other = extract_from_section(soup, "Other Information", [
            "Financer Name", "Cubic Capacity", "Seating Capacity", "Permit Type", "Blacklist Status", "NOC Details"
        ])

        data = {
            "registration_number": registration_number,
            "modal_name": modal_name,
            "owner_name": owner_name,
            "code": code,
            "city": city,
            "phone": phone,
            "website": website,
            "address": address,
            "ownership_details": {
                "owner_name": ownership.get("owner_name", ""),
                "serial_no": ownership.get("owner_serial_no", ""),
                "rto": ownership.get("registered_rto", "")
            },
            "vehicle_details": {
                "maker": vehicle.get("model_name", ""),
                "model": vehicle.get("maker_model", ""),
                "vehicle_class": vehicle.get("vehicle_class", ""),
                "fuel_type": vehicle.get("fuel_type", ""),
                "fuel_norms": vehicle.get("fuel_norms", "")
            },
            "insurance": insurance,
            "validity": {
                "registration_date": validity.get("registration_date", ""),
                "vehicle_age": validity.get("vehicle_age", ""),
                "fitness_upto": validity.get("fitness_upto", ""),
                "insurance_upto": validity.get("insurance_upto", ""),
                "insurance_status": validity.get("insurance_expiry_in", "")
            },
            "other_info": {
                "financer": other.get("financer_name", ""),
                "cubic_capacity": other.get("cubic_capacity", ""),
                "seating_capacity": other.get("seating_capacity", ""),
                "permit_type": other.get("permit_type", ""),
                "blacklist_status": other.get("blacklist_status", ""),
                "noc": other.get("noc_details", "")
            }
        }

        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- DL Extraction ----------
def extract_dl_data(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    def get_value(label: str):
        el = soup.find("span", string=lambda x: x and x.strip().lower() == label.lower())
        if el:
            p_tag = el.find_next("p")
            return p_tag.get_text(strip=True) if p_tag else None
        return None

    return {
        "license_number": get_value("License Number"),
        "holder_name": get_value("Holder Name"),
        "father_name": get_value("Father's Name"),
        "dob": get_value("Date of Birth"),
        "holder_age": get_value("Holder Age"),
        "citizen": get_value("Citizen"),
        "gender": get_value("Gender"),
        "status": get_value("Current Status"),
        "date_of_issue": get_value("Date of Issue"),
        "last_transaction_at": get_value("Last Transaction At"),
        "validity": {
            "non_transport": {
                "from": (get_value("Non-Transport Validity") or "").split(" to ")[0],
                "to": (get_value("Non-Transport Validity") or "").split(" to ")[-1]
            },
            "transport": {
                "from": (get_value("Transport Validity") or "").split(" to ")[0],
                "to": (get_value("Transport Validity") or "").split(" to ")[-1]
            }
        },
        "class_of_vehicle": [
            li.get_text(strip=True) for li in soup.select(".hrc-details-card ul li")
        ]
    }

# ---------- Challan Extraction ----------
def extract_challan_data(html: str, vehicle_number: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    detail_map = [
        "model_name", "owner_name", "rto_code", "rto_city",
        "phone", "website", "address"
    ]
    details = soup.select(".hrcd-cardbody")
    vehicle_info = {}
    for idx, key in enumerate(detail_map):
        try:
            vehicle_info[key] = details[idx].get_text(strip=True)
        except:
            vehicle_info[key] = None

    challans = []
    challan_cards = soup.select(".echallan-card")
    for idx, card in enumerate(challan_cards, start=1):
        challan_id_raw = card.select_one(".echallan-card-header p").get_text(strip=True)
        challan_id = challan_id_raw.replace("#", "").strip()
        status = card.select_one(".echallan-card-header span").get_text(strip=True)

        ecb_lists = card.select(".ecb-list")
        challan_date = None
        offence = "Unknown"
        location = None

        for ecb in ecb_lists:
            label = ecb.select_one("span")
            value = ecb.select_one("p")
            if not label or not value:
                continue
            label_text = label.get_text(strip=True).lower()
            value_text = value.get_text(strip=True)

            if "challan date" in label_text:
                challan_date = value_text
            elif "offence" in label_text or "violation" in label_text:
                offence = value_text
            elif "location" in label_text or "place" in label_text:
                location = value_text

        amounts = [amt.get_text(strip=True) for amt in card.select(".challan-amount-content .amount")]
        amount = amounts[0] if amounts else None

        challans.append({
            "challan_no": f"Challan {idx}",
            "number": challan_id,
            "datetime": challan_date,
            "amount": amount,
            "offence": offence,
            "location": location,
            "status": status.upper()
        })

    return {
        "vehicle": vehicle_number,
        "vehicle_info": vehicle_info,
        "total_challans": len(challans),
        "challans": challans
    }

# ---------- Async wrapper for sync functions ----------
def async_handler(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return decorated_function

# ---------- Unified DL & Challan Endpoint ----------
@app.route("/api/search", methods=["GET"])
@async_handler
async def unified_search():
    dl = request.args.get("dl")
    challan = request.args.get("challan")
    
    if dl:
        try:
            url = f"https://vahanx.in/dl-search/{dl}"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=HEADERS)
                if resp.status_code != 200:
                    return jsonify({"error": "License not found or service unavailable"}), 404
                data = extract_dl_data(resp.text)
                if not data["license_number"]:
                    return jsonify({"error": "License details not found"}), 404
                return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    elif challan:
        try:
            url = f"https://vahanx.in/challan-search/{challan}"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=HEADERS)
                if resp.status_code != 200:
                    return jsonify({"error": "Vehicle not found or service unavailable"}), 404
                data = extract_challan_data(resp.text, challan)
                return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    else:
        return jsonify({"error": "Please provide either ?dl= or ?challan= parameter"}), 400

# ---------- Health Check ----------
@app.route("/", methods=["GET"])
def health_check():
    return jsonify({
        "status": "active",
        "service": "VahanX Data API",
        "endpoints": {
            "/api/vehicle-info?rc=VEHICLE_NUMBER": "Get vehicle RC details",
            "/api/search?dl=DL_NUMBER": "Get driving license details",
            "/api/search?challan=VEHICLE_NUMBER": "Get challan details"
        }
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=True)