from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import requests
import re
import concurrent.futures
import time
import os

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36",
    "Referer": "https://vahanx.in/",
    "Accept-Language": "en-US,en;q=0.9"
}

def extract_card(soup, label):
    """Helper to extract data from card elements"""
    try:
        for div in soup.select(".hrcd-cardbody"):
            span = div.find("span")
            if span and label.lower() in span.text.lower():
                p_tag = div.find("p")
                return p_tag.get_text(strip=True) if p_tag else ""
    except:
        pass
    return ""

def extract_from_section(soup, header_text, keys):
    """Helper to extract data from section elements"""
    result = {}
    try:
        section = soup.find("h3", string=lambda s: s and header_text.lower() in s.lower())
        if not section:
            return result
            
        section_card = section.find_parent("div", class_="hrc-details-card")
        if not section_card:
            return result
            
        for key in keys:
            span = section_card.find("span", string=lambda s: s and key in s)
            if span:
                val = span.find_next("p")
                result[key.lower().replace(" ", "_")] = val.get_text(strip=True) if val else ""
    except:
        pass
    return result

def fetch_rc_details(rc):
    """Fetch RC details from vahanx.in"""
    try:
        url = f"https://vahanx.in/rc-search/{rc}"
        
        # Add retry logic
        for attempt in range(2):
            try:
                response = requests.get(url, headers=HEADERS, timeout=15)
                response.raise_for_status()
                break
            except requests.exceptions.Timeout:
                if attempt == 1:
                    return {"error": "Request timeout"}
                time.sleep(1)
        
        soup = BeautifulSoup(response.text, "html.parser")

        # Safe extraction
        h1_tag = soup.find("h1")
        registration_number = h1_tag.text.strip() if h1_tag else rc
        
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
        expired_days = None
        if insurance_expired_box and insurance_expired_box.text:
            match = re.search(r"(\d+)", insurance_expired_box.text)
            expired_days = int(match.group(1)) if match else None
            
        insurance = extract_from_section(soup, "Insurance Information", ["Insurance Expiry"])
        
        insurance_info = {
            "status": "Expired" if expired_days else "Active",
            "expiry_date": insurance.get("insurance_expiry", ""),
            "expired_days_ago": expired_days
        }

        validity = extract_from_section(soup, "Important Dates", [
            "Registration Date", "Vehicle Age", "Fitness Upto", "Insurance Upto", "Insurance Expiry In"
        ])

        other = extract_from_section(soup, "Other Information", [
            "Financer Name", "Cubic Capacity", "Seating Capacity", "Permit Type", "Blacklist Status", "NOC Details"
        ])

        return {
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
            "insurance": insurance_info,
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
    except Exception as e:
        return {"error": f"Failed to fetch RC details: {str(e)[:100]}"}

def fetch_challan_details(rc):
    """Fetch challan details from external API"""
    try:
        url = f"https://challan-ecru.vercel.app/api/challan?vehicle_number={rc}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36",
            "Accept": "application/json"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            challans_list = []
            if isinstance(data, dict) and 'data' in data:
                inner_data = data['data']
                
                if isinstance(inner_data, dict) and 'data' in inner_data:
                    challans_list = inner_data['data']
                elif isinstance(inner_data, list):
                    challans_list = inner_data
            
            # Calculate total amount
            total_amount = 0
            if isinstance(challans_list, list) and challans_list:
                for challan in challans_list:
                    if isinstance(challan, dict):
                        amount_value = 0
                        
                        if 'amount' in challan:
                            if isinstance(challan['amount'], dict) and 'total' in challan['amount']:
                                total_val = challan['amount']['total']
                                try:
                                    amount_value = float(str(total_val).replace(',', ''))
                                except:
                                    pass
                            elif isinstance(challan['amount'], (int, float, str)):
                                try:
                                    if isinstance(challan['amount'], str):
                                        amount_value = float(challan['amount'].replace(',', '').replace('₹', '').strip())
                                    else:
                                        amount_value = float(challan['amount'])
                                except:
                                    pass
                        
                        if amount_value == 0 and 'violations' in challan:
                            if isinstance(challan['violations'], dict) and 'amount' in challan['violations']:
                                viol_amount = challan['violations']['amount']
                                try:
                                    amount_value = float(str(viol_amount).replace(',', ''))
                                except:
                                    pass
                        
                        total_amount += amount_value
            
            return {
                "total_challans": len(challans_list) if isinstance(challans_list, list) else 0,
                "total_amount": total_amount,
                "challans": challans_list if isinstance(challans_list, list) else [],
                "status": "success"
            }
        else:
            return {
                "total_challans": 0,
                "total_amount": 0,
                "challans": [],
                "status": "api_error"
            }
            
    except Exception:
        return {
            "total_challans": 0,
            "total_amount": 0,
            "challans": [],
            "status": "error"
        }

@app.route("/api/vehicle-info", methods=["GET"])
def get_vehicle_info():
    rc = request.args.get("rc")
    if not rc:
        return jsonify({"success": False, "error": "Missing rc parameter"}), 400

    # Validate RC format
    if not re.match(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$', rc, re.IGNORECASE):
        return jsonify({"success": False, "error": "Invalid RC number format. Example: MH02AB1234"}), 400
    
    try:
        # Sequential execution instead of parallel (simpler, less error prone)
        rc_data = fetch_rc_details(rc)
        challan_data = fetch_challan_details(rc)

        # Check for RC data error
        if "error" in rc_data and not rc_data.get("registration_number"):
            return jsonify({
                "success": False, 
                "error": rc_data["error"],
                "challan_info": challan_data
            }), 200

        # Combine responses
        combined_data = {
            "success": True,
            "vehicle_info": rc_data,
            "challan_info": challan_data,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        }

        return jsonify(combined_data)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:100]}), 500

@app.route("/api/challan-info", methods=["GET"])
def get_challan_info_only():
    rc = request.args.get("rc")
    if not rc:
        return jsonify({"error": "Missing rc parameter"}), 400
    
    # Validate RC format
    if not re.match(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$', rc, re.IGNORECASE):
        return jsonify({"error": "Invalid RC number format. Example: MH02AB1234"}), 400
    
    try:
        challan_data = fetch_challan_details(rc)
        return jsonify(challan_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/test", methods=["GET"])
def test():
    return jsonify({
        "status": "active",
        "message": "Vehicle API is running",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    })

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Vehicle Information API",
        "version": "1.0.0",
        "endpoints": {
            "/api/vehicle-info?rc=<number>": "Get vehicle RC details with challan info",
            "/api/challan-info?rc=<number>": "Get only challan information",
            "/api/test": "Health check endpoint"
        },
        "example": "https://" + request.host + "/api/vehicle-info?rc=MH02AB1234"
    })

# Vercel requires this
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)