# utils.py
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import re

def extract_pdf_data(file):
    text = ''
    items = []
    vendor = None

    # Extract text
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ''
    except:
        pass

    # OCR fallback
    if not text.strip():
        pages = convert_from_path(file)
        for page in pages:
            text += pytesseract.image_to_string(page)

    # Vendor extraction
    vendor_match = re.search(r'Vendor[:\s]*(.+)', text, re.IGNORECASE)
    if vendor_match:
        vendor = vendor_match.group(1).strip()

    # Items extraction (basic regex)
    lines = text.splitlines()
    for line in lines:
        match = re.match(r'(.+?)\s+(\d+)\s+([\d,\.]+)', line)
        if match:
            name, qty, price = match.groups()
            items.append({
                'name': name.strip(),
                'qty': int(qty),
                'unit_price': float(price.replace(',', ''))
            })

    total = sum(i['qty'] * i['unit_price'] for i in items)
    return {'vendor': vendor, 'items': items, 'total': total}
