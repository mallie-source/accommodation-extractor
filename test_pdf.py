import os
from app import extract_accommodation_data  

pdf_path = r"C:\Users\450215\Downloads\rsv-let-of-conf_anonymous 2.pdf"

if not os.path.exists(pdf_path):
    print("PDF not found at", pdf_path)
else:
    data = extract_accommodation_data(pdf_path)
    print("Extraction result:")
    print(data)
