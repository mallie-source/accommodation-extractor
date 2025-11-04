import base64
import tempfile
import os
from flask import Flask, request, jsonify
from datetime import datetime
import pdfplumber
import re

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Accommodation Extractor API running"

@app.route('/process', methods=['POST'])
def process_file():
    data = request.get_json()

    file_name = data.get("fileName", "unknown.pdf")
    file_content = data.get("fileContent")  # base64-encoded PDF string
    test_mode = data.get("testMode", False)  # <-- NEW: test mode flag

    # ---------- TEST MODE ----------
    if test_mode:
        # Return a fake extraction without a PDF
        fake_data = [{
            "Reservation No": "TEST12345",
            "Camps": "RESEARCH CAMPS",
            "Qty": "2",
            "Facilities Reserved": "Tent, Sleeping Bag",
            "Night": "3",
            "Arrival": "2025-11-10",
            "Departure": "2025-11-13",
            "Adult": "2",
            "Child": "1"
        }]
        return jsonify({
            "status": "success",
            "records_found": len(fake_data),
            "data": fake_data,
            "testMode": True
        })

    # ---------- REAL PDF PROCESSING ----------
    if not file_content:
        return jsonify({"error": "Missing fileContent"}), 400

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, file_name)

        try:
            with open(pdf_path, "wb") as f:
                f.write(base64.b64decode(file_content))
        except Exception as e:
            return jsonify({"error": f"Failed to decode base64 file: {e}"}), 400

        try:
            extracted = extract_accommodation_data(pdf_path)
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"Failed to parse PDF: {e}"
            }), 400

    return jsonify({
        "status": "success",
        "records_found": len(extracted),
        "data": extracted,
        "testMode": False
    })


def extract_accommodation_data(pdf_path):
    data = []
    reservation_no = None
    reservation_date = None

    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())

            for line in full_text.splitlines():
                if "Reservation No:" in line:
                    reservation_no = line.split(":")[1].strip()
                if "Original Reservation Date" in line:
                    raw_date = line.split(":")[1].strip()
                    try:
                        reservation_date = datetime.strptime(raw_date, "%d/%m/%Y").strftime("%Y-%m-%d")
                    except ValueError:
                        reservation_date = "unknown"

            for line in full_text.splitlines():
                if line.startswith("RESEARCH CAMPS"):
                    match = re.search(
                        r"RESEARCH CAMPS\s+(\d+)\s+(.*?)\s+(\d+)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d+)\s+(\d+)",
                        line
                    )
                    if match:
                        data.append({
                            "Reservation No": reservation_no,
                            "Camps": "RESEARCH CAMPS",
                            "Qty": match.group(1),
                            "Facilities Reserved": match.group(2),
                            "Night": match.group(3),
                            "Arrival": match.group(4),
                            "Departure": match.group(5),
                            "Adult": match.group(6),
                            "Child": match.group(7)
                        })
    except Exception as e:
        raise RuntimeError(f"Invalid or unreadable PDF: {e}")

    return data


if __name__ == "__main__":
    app.run(debug=True)