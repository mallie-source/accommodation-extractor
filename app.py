# app.py
import base64
import tempfile
import os
import logging
from flask import Flask, request, jsonify
from datetime import datetime
import pdfplumber
import re

# Optional: enable OCR fallback via pytesseract if installed.
# If you want OCR fallback, install `pytesseract` and Tesseract binary,
# then set USE_OCR_FALLBACK = True
USE_OCR_FALLBACK = False
try:
    if USE_OCR_FALLBACK:
        import pytesseract
        from PIL import Image
except Exception:
    USE_OCR_FALLBACK = False

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = Flask(__name__)

# ------------------------------
# Helper: robust text extraction
# ------------------------------
def extract_text_from_pdf(pdf_path, ocr_fallback=USE_OCR_FALLBACK):
    """
    Extract text from PDF using pdfplumber; optionally fallback to OCR for pages with no text.
    Returns single string of text from all pages.
    """
    text_pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text_pages.append(page_text)
                elif ocr_fallback:
                    try:
                        # Render page to image and OCR (pytesseract)
                        im = page.to_image(resolution=150).original
                        ocr_text = pytesseract.image_to_string(im)
                        text_pages.append(ocr_text or "")
                    except Exception as e:
                        logging.warning("OCR fallback failed for a page: %s", e)
                        text_pages.append("")
    except Exception as e:
        logging.exception("pdfplumber failed to open PDF: %s", e)
        raise

    full_text = "\n".join(p for p in text_pages if p)
    return full_text

# ------------------------------
# Robust extraction function
# ------------------------------
def extract_accommodation_data(pdf_path):
    """
    Return a list of dicts representing extracted reservation rows.
    Each dict fields:
      Reservation No, Camps, Qty, Facilities Reserved, Night,
      Arrival, Departure, Adult, Child
    """
    data = []
    reservation_no = None

    # Extract raw text
    raw_text = extract_text_from_pdf(pdf_path)

    if not raw_text or not raw_text.strip():
        # Nothing to extract
        logging.info("No text extracted from PDF.")
        return data

    # Normalize whitespace but keep line boundaries
    # Collapse multiple spaces and trim
    normalized = re.sub(r"[ \t]{2,}", " ", raw_text)
    # Ensure lines are separate
    lines = [ln.strip() for ln in normalized.splitlines() if ln.strip()]

    # Extract reservation number (several possible label variants)
    # e.g. "Reservation No: R12345" or "Reservation No R12345"
    m_res = re.search(r"Reservation\s*No[:\s]*([A-Z0-9-]+)", normalized, flags=re.IGNORECASE)
    if m_res:
        reservation_no = m_res.group(1).strip()
        logging.info("Found Reservation No: %s", reservation_no)

    # Some PDFs show "Reservation No" on its own line or with trailing text — attempt more patterns
    if not reservation_no:
        for ln in lines[:30]:  # search first 30 lines for efficiency
            m = re.search(r"Reservation\s*No[:\s]*([A-Z0-9-]+)", ln, flags=re.IGNORECASE)
            if m:
                reservation_no = m.group(1).strip()
                break

    # Build a joined text that preserves spaces between nearby lines to help match rows that split across lines
    joined_text = " \n".join(lines)

    # Universal camp row regex:
    # - camp name: SUPPORTS "RESEARCH CAMPS", "<NAME> REST CAMP", "<NAME> CAMP", etc.
    # - qty: integer
    # - facilities: non-greedy capture of anything until we reach Night numeric
    # - night: integer
    # - arrival & departure: dd/mm/yyyy
    # - adult & child: integers (or missing, handled)
    camp_pattern = re.compile(
        r"((?:[A-Z &/']+REST CAMP)|(?:RESEARCH CAMPS)|(?:[A-Z &/']+CAMP))\s+"
        r"(\d+)\s+"
        r"(.+?)\s+"
        r"(\d+)\s+"
        r"(\d{2}/\d{2}/\d{4})\s+"
        r"(\d{2}/\d{2}/\d{4})\s+"
        r"(\d+)\s+"
        r"(\d+)",
        flags=re.IGNORECASE | re.DOTALL
    )

    # We'll search both line-by-line and whole-text fallback
    matches = []
    # 1) Try line-by-line first
    for ln in lines:
        m = camp_pattern.search(ln)
        if m:
            matches.append(m)

    # 2) If not found, attempt to find across joined_text (helps when facility description wraps lines)
    if not matches:
        for m in camp_pattern.finditer(joined_text):
            matches.append(m)

    # 3) Additional fallback: look for "Qty Arrival Camps" style grid rows by detecting date patterns + numbers
    # This is a looser approach: find date pairs and then try to capture adjacent tokens
    if not matches:
        date_pair_pattern = re.compile(r"(\d{2}/\d{2}/\d{4}).{0,50}?(\d{2}/\d{2}/\d{4})", flags=re.IGNORECASE)
        for mdp in date_pair_pattern.finditer(joined_text):
            # Take a window around the match to try to parse tokens
            start = max(0, mdp.start() - 120)
            end = min(len(joined_text), mdp.end() + 120)
            window = joined_text[start:end]
            # attempt to split tokens and heuristically map fields
            tokens = re.split(r"\s{2,}|\t", window)
            # naive heuristic: if tokens contain a camp name and numbers, accept as a row
            for t in tokens:
                if re.search(r"(REST CAMP|RESEARCH CAMPS| CAMP)", t, flags=re.IGNORECASE) and re.search(r"\d{2}/\d{2}/\d{4}", t):
                    # attempt to extract numbers and dates inside t using smaller regex
                    small = re.search(
                        r"((?:[A-Z &/']+REST CAMP)|(?:RESEARCH CAMPS)|(?:[A-Z &/']+CAMP)).*?(\d+).*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4}).*?(\d+).*?(\d+)",
                        t, flags=re.IGNORECASE | re.DOTALL
                    )
                    if small:
                        matches.append(small)

    # Build final data objects
    for m in matches:
        try:
            camps_raw = m.group(1).strip()
            qty = m.group(2).strip()
            facilities = m.group(3).strip()
            night = m.group(4).strip()
            arrival = m.group(5).strip()
            departure = m.group(6).strip()
            adult = m.group(7).strip()
            child = m.group(8).strip()

            # Normalize date format to ISO YYYY-MM-DD for easier storage (but keep original too if you prefer)
            def to_iso(d):
                try:
                    return datetime.strptime(d, "%d/%m/%Y").strftime("%Y-%m-%d")
                except Exception:
                    return d

            data.append({
                "Reservation No": reservation_no or "",
                "Camps": camps_raw.upper(),
                "Qty": qty,
                "Facilities Reserved": facilities,
                "Night": night,
                "Arrival": arrival,
                "Arrival_ISO": to_iso(arrival),
                "Departure": departure,
                "Departure_ISO": to_iso(departure),
                "Adult": adult,
                "Child": child
            })
        except Exception as e:
            logging.exception("Failed to parse a match: %s", e)
            continue

    # Deduplicate rows (some PDFs may create duplicate matches)
    unique = []
    seen = set()
    for row in data:
        key = (row.get("Camps"), row.get("Arrival"), row.get("Departure"), row.get("Qty"), row.get("Facilities Reserved"))
        if key not in seen:
            seen.add(key)
            unique.append(row)

    return unique

# ------------------------------
# API endpoints
# ------------------------------
@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"message": "pong"}), 200

@app.route("/", methods=["GET"])
def home():
    return "✅ Accommodation Extractor API running"

@app.route("/process", methods=["POST"])
def process_file():
    req = request.get_json(silent=True)
    if req is None:
        return jsonify({"status": "error", "message": "Invalid JSON body"}), 400

    file_name = req.get("fileName", "unknown.pdf")
    file_content = req.get("fileContent")
    test_mode = req.get("testMode", False)
    rename_on_success = req.get("renameOnSuccess", True)  # optional config

    # Test mode returns a predictable payload for debugging flows
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

    if not file_content:
        return jsonify({"status": "error", "message": "Missing fileContent"}), 400

    # Decode and save to temp file
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, file_name)
            with open(pdf_path, "wb") as f:
                f.write(base64.b64decode(file_content))
            logging.info("Saved uploaded PDF to %s", pdf_path)

            # Extract rows
            extracted = extract_accommodation_data(pdf_path)
            logging.info("Extraction returned %d rows", len(extracted))

            # Optionally rename the uploaded PDF for archival
            saved_name = None
            if extracted and rename_on_success:
                # Choose first reservation no if present
                rn = extracted[0].get("Reservation No") or "NORES"
                date_iso = extracted[0].get("Arrival_ISO") or datetime.utcnow().strftime("%Y-%m-%d")
                saved_name = f"{rn}_{date_iso}.pdf"
                archive_folder = os.environ.get("ARCHIVE_FOLDER")  # optional env var
                if archive_folder:
                    try:
                        os.makedirs(archive_folder, exist_ok=True)
                        target = os.path.join(archive_folder, saved_name)
                        os.replace(pdf_path, target)
                        logging.info("Archived PDF to %s", target)
                    except Exception as e:
                        logging.warning("Failed to archive PDF: %s", e)
                else:
                    # if no archive folder, we won't move the file
                    saved_name = None

            return jsonify({
                "status": "success",
                "records_found": len(extracted),
                "data": extracted,
                "testMode": False,
                "saved_name": saved_name
            }), 200

    except Exception as e:
        logging.exception("Processing failed: %s", e)
        return jsonify({"status": "error", "message": f"Processing failed: {e}"}), 500

# ------------------------------
# Run app
# ------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
