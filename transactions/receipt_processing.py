"""Receipt and bank-statement OCR + parsing."""
import json
import logging
import os
import re
import time
from datetime import datetime
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _categorize_merchant(merchant_name):
    """Simple merchant categorization based on keywords."""
    if merchant_name is None:
        return None
    merchant_lower = merchant_name.lower()
    
    category_keywords = {
        'groceries': ['whole foods', 'trader joe', 'costco', 'walmart', 'target', 'grocery', 'market', 'food'],
        'dining': ['starbucks', 'mcdonald', 'restaurant', 'cafe', 'coffee', 'doordash', 'uber eats', 'grubhub'],
        'transportation': ['shell', 'gas', 'exxon', 'chevron', 'uber', 'lyft', 'transport'],
        'entertainment': ['spotify', 'netflix', 'hulu', 'disney', 'movie', 'theater'],
        'healthcare': ['pharmacy', 'cvs', 'walgreens', 'doctor', 'hospital', 'planet fitness', 'gym'],
        'shopping': ['amazon', 'ebay', 'shop', 'store', 'mall'],
        'utilities': ['electric', 'water', 'internet', 'phone', 'utility', 'comcast', 'verizon'],
    }
    
    for category, keywords in category_keywords.items():
        if any(kw in merchant_lower for kw in keywords):
            return category.capitalize()
    return 'Other'


def extract_text_from_file(file_path, content_type=''):
    """Extract text from a document file (PDF, DOCX, TXT) stored in Django storage."""
    from django.core.files.storage import default_storage
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.txt' or content_type.startswith('text/'):
        if default_storage.exists(file_path):
            with default_storage.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        return ''
    
    if ext == '.pdf':
        if default_storage.exists(file_path):
            try:
                import PyPDF2
                with default_storage.open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = []
                    for page in reader.pages:
                        text.append(page.extract_text() or '')
                    return '\n\n'.join(text)
            except Exception as e:
                logger.warning(f"PDF extraction failed: {e}")
        return ''
    
    if ext in ('.docx', '.doc'):
        if default_storage.exists(file_path):
            try:
                from docx import Document
                with default_storage.open(file_path, 'rb') as f:
                    doc = Document(f)
                    return '\n\n'.join(p.text for p in doc.paragraphs)
            except Exception as e:
                logger.warning(f"DOCX extraction failed: {e}")
        return ''
    
    return ''


BANK_STATEMENT_KEYWORDS = (
    'statement', 'chequing', 'checking', 'account summary',
    'opening balance', 'closing balance', 'transaction history',
)


def extract_text_from_image(receipt):
    """
    Extract text from a receipt/statement image.
    Tries local Tesseract first (fast, no network), then PaddleOCR API.
    """
    errors = []

    try:
        text = _extract_local_tesseract(receipt)
        if text and len(text.strip()) > 20:
            logger.info(f"Receipt {receipt.id}: extracted {len(text)} chars via Tesseract")
            return text, 'tesseract'
    except Exception as e:
        errors.append(f'Tesseract: {e}')
        logger.warning(f"Local OCR failed for receipt {receipt.id}: {e}")

    try:
        text = _extract_paddleocr(receipt)
        if text and len(text.strip()) > 10:
            logger.info(f"Receipt {receipt.id}: extracted {len(text)} chars via PaddleOCR")
            return text, 'paddleocr'
    except Exception as e:
        errors.append(f'PaddleOCR: {e}')
        logger.warning(f"PaddleOCR failed for receipt {receipt.id}: {e}")

    raise RuntimeError(
        'Could not read the image. '
        + ('; '.join(errors) if errors else 'Try a clearer photo or PDF export.')
    )


def _extract_local_tesseract(receipt):
    import pytesseract
    from PIL import Image, ImageOps

    cmd = getattr(settings, 'TESSERACT_CMD', None)
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    img = Image.open(receipt.image.path)
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    return pytesseract.image_to_string(img)


def _extract_paddleocr(receipt):
    token = getattr(settings, 'PADDLEOCR_API_TOKEN', '')
    if not token or token == 'sdfghjk':
        raise RuntimeError('PaddleOCR API token not configured')

    job_url = 'https://paddleocr.aistudio-app.com/api/v2/ocr/jobs'
    headers = {'Authorization': f'bearer {token}'}
    optional_payload = {
        'useDocOrientationClassify': True,
        'useDocUnwarping': False,
        'useChartRecognition': False,
    }

    submit_timeout = getattr(settings, 'PADDLEOCR_SUBMIT_TIMEOUT', 20)
    poll_timeout = getattr(settings, 'PADDLEOCR_POLL_TIMEOUT', 15)
    max_wait = getattr(settings, 'PADDLEOCR_MAX_WAIT', 45)

    with open(receipt.image.path, 'rb') as f:
        response = requests.post(
            job_url,
            headers=headers,
            data={
                'model': 'PaddleOCR-VL-1.6',
                'optionalPayload': json.dumps(optional_payload),
            },
            files={'file': f},
            timeout=submit_timeout,
        )

    if response.status_code != 200:
        raise RuntimeError(f'OCR submission failed: {response.text[:200]}')

    job_id = response.json()['data']['jobId']
    deadline = time.time() + max_wait

    while time.time() < deadline:
        poll = requests.get(f'{job_url}/{job_id}', headers=headers, timeout=poll_timeout)
        if poll.status_code != 200:
            raise RuntimeError('Failed to check OCR job status')

        state = poll.json()['data']['state']
        if state == 'done':
            jsonl_url = poll.json()['data']['resultUrl']['jsonUrl']
            jsonl_response = requests.get(jsonl_url, timeout=poll_timeout)
            jsonl_response.raise_for_status()
            parts = []
            for line in jsonl_response.text.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                result = json.loads(line)['result']
                for res in result.get('layoutParsingResults', []):
                    parts.append(res['markdown']['text'])
            return '\n\n'.join(parts)
        if state == 'failed':
            raise RuntimeError(poll.json()['data'].get('errorMsg', 'OCR job failed'))

        time.sleep(3)

    raise RuntimeError(f'OCR timed out after {max_wait}s')


def is_bank_statement(text, filename=''):
    combined = f'{filename} {text}'.lower()
    return any(kw in combined for kw in BANK_STATEMENT_KEYWORDS)


def parse_document_text(text, filename=''):
    if is_bank_statement(text, filename):
        return parse_bank_statement(text, filename)
    return parse_receipt_text(text)


def parse_receipt_text(text):
    result = {
        'document_type': 'receipt',
        'merchant_name': '',
        'date': None,
        'total_amount': None,
        'tax_amount': None,
        'tip_amount': None,
        'items': [],
        'payment_method': '',
        'transactions': [],
    }

    lines = text.split('\n')
    clean_lines = [l.strip() for l in lines if l.strip()]

    if clean_lines:
        first_line = clean_lines[0]
        if len(first_line) > 2 and not any(x in first_line.lower() for x in ['date', 'total', 'subtotal', 'item']):
            result['merchant_name'] = first_line[:200]

    result['date'] = _find_date_in_lines(clean_lines) or _find_date_in_lines(list(reversed(clean_lines)))

    amounts = []
    for clean_line in clean_lines:
        for m in re.findall(r'\$?([\d,]+\.\d{2})', clean_line):
            try:
                amt = Decimal(m.replace(',', ''))
                if 0 < amt < 50000:
                    amounts.append((amt, clean_line))
            except Exception:
                pass

    total_match = re.search(
        r'(?:total|amount due|balance due|grand total)[:\s]*\$?\s*([\d,]+\.\d{2})',
        text, re.IGNORECASE
    )
    if total_match:
        result['total_amount'] = Decimal(total_match.group(1).replace(',', ''))
    elif amounts:
        result['total_amount'] = max(a[0] for a in amounts)

    tax_match = re.search(r'tax[:\s]*\$?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if tax_match:
        try:
            result['tax_amount'] = Decimal(tax_match.group(1).replace(',', ''))
        except Exception:
            pass

    item_pattern = r'(.+?)\s+\$?([\d,]+\.\d{2})$'
    for clean_line in clean_lines:
        match = re.match(item_pattern, clean_line)
        if match and len(match.group(1)) > 2:
            try:
                price = Decimal(match.group(2).replace(',', ''))
                if 0 < price < 5000:
                    result['items'].append({
                        'name': match.group(1).strip(),
                        'price': str(price),
                    })
            except Exception:
                pass

    return result


def parse_bank_statement(text, filename=''):
    result = {
        'document_type': 'bank_statement',
        'merchant_name': 'Bank Statement',
        'date': None,
        'total_amount': None,
        'tax_amount': None,
        'tip_amount': None,
        'items': [],
        'payment_method': '',
        'transactions': [],
    }

    clean_lines = [l.strip() for l in text.split('\n') if l.strip()]
    result['date'] = _find_date_in_lines(clean_lines)

    txn_patterns = [
        re.compile(
            r'^(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s+(.+?)\s+(-?\$?\s*[\d,]+\.\d{2})\s*$'
        ),
        re.compile(
            r'^(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s+(.+?)\s+(-?\$?\s*[\d,]+\.\d{2})\s*$'
        ),
        re.compile(
            r'^([A-Za-z]{3}\s+\d{1,2})\s+(.+?)\s+(-?\$?\s*[\d,]+\.\d{2})\s*$'
        ),
        re.compile(
            r'^(.+?)\s+(-?\$?\s*[\d,]+\.\d{2})\s+(CR|DR)?\s*$'
        ),
    ]

    for line in clean_lines:
        if any(skip in line.lower() for skip in ('opening balance', 'closing balance', 'page ', 'continued')):
            continue

        for pattern in txn_patterns:
            match = pattern.match(line)
            if not match:
                continue

            groups = match.groups()
            if len(groups) == 3 and groups[0] and re.match(r'[\d/A-Za-z]', groups[0]):
                date_str, desc, amt_str = groups
            elif len(groups) >= 2:
                desc, amt_str = groups[0], groups[1]
                date_str = None
            else:
                continue

            desc = desc.strip()
            if len(desc) < 2 or desc.lower() in ('date', 'description', 'amount', 'balance'):
                continue

            try:
                amount = Decimal(re.sub(r'[^\d.\-]', '', amt_str.replace(',', '')))
            except Exception:
                continue

            if amount == 0:
                continue

            txn_date = _parse_flexible_date(date_str) if date_str else result['date']
            result['transactions'].append({
                'date': txn_date,
                'merchant': desc[:200],
                'amount': amount,
            })
            break

    if result['transactions']:
        debits = [abs(t['amount']) for t in result['transactions'] if t['amount'] < 0]
        result['total_amount'] = max(debits) if debits else abs(result['transactions'][-1]['amount'])
        if not result['date'] and result['transactions'][0].get('date'):
            result['date'] = result['transactions'][0]['date']

    return result


def _find_date_in_lines(lines):
    date_patterns = [
        (r'\d{4}-\d{1,2}-\d{1,2}', ['%Y-%m-%d']),
        (r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', ['%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y']),
        (r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}', ['%b %d, %Y', '%B %d, %Y']),
    ]
    for line in lines:
        for pattern, fmts in date_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                parsed = _parse_flexible_date(match.group(), fmts)
                if parsed:
                    return parsed
    return None


def _parse_flexible_date(text, fmts=None):
    if not text:
        return None
    text = text.strip()
    fmts = fmts or ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y', '%b %d', '%b %d, %Y', '%B %d, %Y']
    for fmt in fmts:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt == '%b %d':
                dt = dt.replace(year=datetime.now().year)
            return dt.date()
        except ValueError:
            continue
    compact = re.search(r'(\d{4})-?(\d{1,2})-?(\d{1,2})', text)
    if compact:
        try:
            return datetime.strptime(compact.group(), '%Y-%m-%d').date()
        except ValueError:
            pass
    return None


def _confidence_score(parsed):
    score = 0.0
    if parsed.get('merchant_name'):
        score += 0.25
    if parsed.get('date'):
        score += 0.2
    if parsed.get('total_amount'):
        score += 0.25
    if parsed.get('items'):
        score += 0.15
    if parsed.get('transactions'):
        score += min(0.3, len(parsed['transactions']) * 0.05)
    return min(score, 1.0)


def import_statement_transactions(receipt, parsed, account):
    from transactions.models import Transaction

    imported = 0
    for txn in parsed.get('transactions', []):
        amount = txn['amount']
        txn_date = txn.get('date') or timezone.now().date()
        merchant = txn.get('merchant', 'Unknown')

        exists = Transaction.objects.filter(
            user=receipt.user,
            date=txn_date,
            amount=abs(amount),
            merchant_name=merchant,
        ).exists()
        if exists:
            continue

        Transaction.objects.create(
            user=receipt.user,
            account=account,
            amount=abs(amount),
            transaction_type='credit' if amount > 0 else 'debit',
            merchant_name=merchant,
            description=merchant,
            date=txn_date,
            posted_date=txn_date,
            status='posted',
            metadata={'receipt_id': str(receipt.id), 'source': 'bank_statement_ocr'},
        )
        imported += 1

    return imported


def create_transaction_from_receipt(receipt, account=None):
    from transactions.models import Transaction, MerchantCache

    if not receipt.total_amount:
        return None

    if account is None:
        from core.models import FinancialAccount
        account = FinancialAccount.objects.filter(user=receipt.user, is_active=True).first()
    if not account:
        return None

    category = None
    if receipt.merchant_name:
        cached = MerchantCache.objects.filter(
            normalized_name__iexact=receipt.merchant_name.strip().lower()
        ).first()
        if cached and cached.category:
            category = cached.category

    txn_date = receipt.date or timezone.now().date()
    exists = Transaction.objects.filter(
        user=receipt.user,
        date=txn_date,
        amount=abs(receipt.total_amount),
        merchant_name__icontains=(receipt.merchant_name or '')[:50],
    ).exists()
    if exists:
        return None

    txn = Transaction.objects.create(
        user=receipt.user,
        account=account,
        amount=abs(receipt.total_amount),
        transaction_type='debit',
        merchant_name=(receipt.merchant_name or 'Receipt')[:200],
        description=f"Receipt: {receipt.merchant_name or 'Unknown'}",
        category=category,
        date=txn_date,
        posted_date=txn_date,
        status='posted',
        metadata={'receipt_id': str(receipt.id), 'source': 'receipt_ocr'},
    )
    receipt.transaction = txn
    receipt.save(update_fields=['transaction'])
    return txn


def process_receipt_record(receipt):
    """
    Full OCR + parse + import pipeline. Returns user-facing message string.
    """
    from core.models import FinancialAccount

    account = FinancialAccount.objects.filter(user=receipt.user, is_active=True).first()
    extracted_text, ocr_engine = extract_text_from_image(receipt)
    parsed = parse_document_text(extracted_text, receipt.original_filename)

    receipt.extracted_text = extracted_text
    receipt.merchant_name = parsed.get('merchant_name', '')[:200]
    receipt.date = parsed.get('date')
    receipt.total_amount = parsed.get('total_amount')
    receipt.tax_amount = parsed.get('tax_amount')
    receipt.tip_amount = parsed.get('tip_amount')
    receipt.items = parsed.get('items', [])
    receipt.payment_method = parsed.get('payment_method', '')
    receipt.extracted_data = {
        'document_type': parsed.get('document_type'),
        'ocr_engine': ocr_engine,
        'transaction_count': len(parsed.get('transactions', [])),
    }
    receipt.confidence_score = _confidence_score(parsed)

    if parsed.get('document_type') == 'bank_statement' and parsed.get('transactions'):
        imported = import_statement_transactions(receipt, parsed, account)
        receipt.status = 'completed' if imported else 'manual_review'
        receipt.processed_at = timezone.now()
        receipt.save()

        if imported:
            return (
                f"Bank statement processed ({ocr_engine}). "
                f"Imported {imported} transaction(s).\n"
                f"Ask me about your spending!"
            )
        return (
            f"I read your bank statement ({ocr_engine}) but couldn't match individual transactions. "
            f"The text was saved for review."
        )

    if receipt.confidence_score >= 0.5 and receipt.total_amount:
        receipt.status = 'completed'
        create_transaction_from_receipt(receipt, account)
    else:
        receipt.status = 'manual_review'

    receipt.processed_at = timezone.now()
    receipt.save()

    lines = [f"Processed ({ocr_engine}) from {receipt.merchant_name or 'uploaded document'}."]
    if receipt.date:
        lines.append(f"Date: {receipt.date}")
    if receipt.total_amount:
        lines.append(f"Amount: ${receipt.total_amount}")
    if receipt.items:
        lines.append(f"Line items: {len(receipt.items)}")
    if receipt.status == 'completed':
        lines.append("\nRecorded as an expense.")
    else:
        lines.append("\nSaved for review — some fields may be incomplete.")
    lines.append("Ask me anything about it!")
    return '\n'.join(lines)
