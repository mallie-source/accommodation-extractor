import requests
import base64
import os

pdf_path = r"C:\Users\450215\Downloads\rsv-let-of-conf_anonymous 2.pdf"

if not os.path.exists(pdf_path):
    print(f"PDF not found at {pdf_path}")
    exit(1)

with open(pdf_path, "rb") as f:
    encoded_pdf = base64.b64encode(f.read()).decode("utf-8")

url = "http://127.0.0.1:5000/process"
payload = {
    "fileName": os.path.basename(pdf_path),
    "fileContent": encoded_pdf
}

try:
    response = requests.post(url, json=payload)
    response.raise_for_status()
    print("✅ Flask response:")
    print(response.json())
except requests.exceptions.HTTPError as e:
    print("❌ HTTP error:", e)
    if e.response is not None:
        print(e.response.text)
except Exception as e:
    print("❌ Error:", e)
