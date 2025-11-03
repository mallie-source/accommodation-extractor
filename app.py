from flask import Flask, request, jsonify
import pdfplumber
import pandas as pd
import re
import os
import requests
from datetime import datetime
import tempfile

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Accommodation Extractor API running"

@app.route('/process', methods=['POST'])
def process_file():
    data = request.get_json()
    pdf_url = data.get("fileUrl")
    file_name = data.get("fileName", "unknown.pdf")

    if not pdf_url:
        return jsonify({"error": "Missing fileUrl"}), 400

    # Create temp working folder
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, file_name)

        # Download file from OneDrive link
        print(f"⬇️ Downloading {pdf_url}")
        r = requests.get(pdf_url)
        if r.status_code != 200:
            return jsonify({"error": f"Failed to download file: {r.status_code}"}), 400

        with open(pdf_path, "wb") as f:
            f.write(r.content)

        # Extract info from the PDF
        extracted = extract_accommodation_data(pdf_path)

        return jsonify({
            "status": "success",
            "records_found": len(extracted),
            "data": extracted
        })

def extract_accommodation_data(pdf_path):
    """Your original extraction logic, refactored for reusability"""
    data = []
    reservation_no = None
    reservation_date = None

    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())

        # Extract Reservation Number and Date
        for line in full_text.splitlines():
            if "Reservation No:" in line:
                reservation_no = line.split(":")[1].strip()
            if "Original Reservation Date" in line:
                raw_date = line.split(":")[1].strip()
                try:
                    reservation_date = datetime.strptime(raw_date, "%d/%m/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    reservation_date = "unknown"

        # Extract RESEARCH CAMPS rows
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

    return data

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
