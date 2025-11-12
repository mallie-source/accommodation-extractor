import requests
import base64

pdf_path = r"C:\Users\450215\Downloads\rsv-let-of-conf_anonymous 2.pdf"

with open(pdf_path, "rb") as f:
    encoded_pdf = base64.b64encode(f.read()).decode("utf-8")

url = "https://accommodation-extractor.onrender.com/process"

payload = {
    "fileName": "real_test.pdf",
    "fileContent": encoded_pdf
}

response = requests.post(url, json=payload)
print(response.status_code)
print(response.text)
