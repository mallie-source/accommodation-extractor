import base64
import tempfile
import os
from flask import Flask, request, jsonify
from datetime import datetime
import pdfplumber
import re

app = Flask(__name__)

@app.route("/ping", methods=["GET"])
def ping():
    print("✅ Power Automate reached the app!")
    return jsonify({"message": "pong"}), 200


@app.route("/", methods=["GET"])
def home():
    return "✅ Accommodation Extractor API running"


@app.route("/process", methods=["POST"])
def process_file():
    data = request.get_json()

    file_name = data.get("fileName", "unknown.pdf")
    file_content = data.get("fileContent")
    test_mode = data.get("testMode", False)

    # ---------- TEST MODE ----------
    if test_mode:
        fake_record = [{
            "Reservation No": "TEST12345",
            "Camps": "SKUKUZA REST CAMP",
            "Qty": "1",
            "Facilities Reserved": "BD3 (Bungalow)",
            "Night": "3",
            "Arrival": "2025-11-10",
            "Departure": "2025-11-13",
            "Adult": "2",
            "Child": "1"
        }]
        return jsonify({
            "status": "success",
            "records_found": len(fake_record),
            "data": fake_record,
            "testMode": True
        }), 200

    # ---------- VALIDATE INPUT ----------
    if not file_content:
        return jsonify({"error": "Missing fileContent"}), 400

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, file_name)

        # Save decoded PDF
        try:
            with open(pdf_path, "wb") as f:
                f.write(base64.b64decode(file_content))
        except Exception as e:
            return jsonify({"error": f"Failed to decode base64: {e}"}), 400

        # Extract data
        try:
            extracted_data = extract_accommodation_data(pdf_path)
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"PDF parsing failed: {e}"
            }), 400

    return jsonify({
        "status": "success",
        "records_found": len(extracted_data),
        "data": extracted_data,
        "testMode": False
    }), 200


# -----------------------------------------------------
#              PDF EXTRACTION FUNCTION
# -----------------------------------------------------

def extract_accommodation_data(pdf_path):
    data = []
    reservation_no = None
    reservation_date = None

    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = "\n".join(
                page.extract_text() for page in pdf.pages if page.extract_text()
            )

            # ---------- Extract Reservation No ----------
            match_res = re.search(r"Reservation No:\s*([A-Z0-9]+)", full_text)
            if match_res:
                reservation_no = match_res.group(1)

            # ---------- Extract Original Reservation Date ----------
            match_date = re.search(r"Original Reservation Date\s*:\s*(\d{2}/\d{2}/\d{4})", full_text)
            if match_date:
                raw_date = match_date.group(1)
                try:
                    reservation_date = datetime.strptime(raw_date, "%d/%m/%Y").strftime("%Y-%m-%d")
                except:
                    reservation_date = None

            # ---------------------------------------------------------
            # UNIVERSAL CAMP EXTRACTION PATTERN (works for all camps)
            # ---------------------------------------------------------

            camp_pattern = re.compile(
                r"([A-Z ]+REST CAMP)\s+(\d+)\s+([A-Z0-9() ,\-\/]+)\s+(\d+)\s+"
                r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d+)\s+(\d+)"
            )

            for line in full_text.splitlines():
                m = camp_pattern.search(line)
                if m:
                    data.append({
                        "Reservation No": reservation_no,
                        "Camps": m.group(1).strip(),
                        "Qty": m.group(2),
                        "Facilities Reserved": m.group(3).strip(),
                        "Night": m.group(4),
                        "Arrival": m.group(5),
                        "Departure": m.group(6),
                        "Adult": m.group(7),
                        "Child": m.group(8)
                    })

    except Exception as e:
        raise RuntimeError(f"Error parsing PDF: {e}")

    return data


# -----------------------------------------------------
#                    RUN APP
# -----------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
