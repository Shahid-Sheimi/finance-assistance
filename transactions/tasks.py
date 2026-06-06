from celery import shared_task
from django.utils import timezone
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_transaction_import(self, import_id):
    from transactions.models import TransactionImport, Transaction, FinancialAccount
    from transactions.models import TransactionCategory

    try:
        import_obj = TransactionImport.objects.get(id=import_id)
        import_obj.status = 'processing'
        import_obj.started_at = timezone.now()
        import_obj.save()

        if import_obj.source in ('csv', 'api'):
            process_csv_import(import_obj)
        elif import_obj.source in ('txt', 'pdf', 'docx', 'doc'):
            process_document_import(import_obj)

        import_obj.status = 'completed'
        import_obj.completed_at = timezone.now()
        import_obj.save()

    except Exception as exc:
        import_obj.status = 'failed'
        import_obj.errors = [str(exc)]
        import_obj.completed_at = timezone.now()
        import_obj.save()
        logger.error(f"Import {import_id} failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


def process_document_import(import_obj):
    """Process uploaded text/PDF/DOCX files: extract text, parse, import transactions."""
    from transactions.models import Transaction, FinancialAccount, TransactionCategory
    from transactions.receipt_processing import extract_text_from_file, parse_document_text, _categorize_merchant
    from django.core.files.storage import default_storage
    from datetime import datetime as dt

    user = import_obj.user
    account = import_obj.account or FinancialAccount.objects.filter(user=user, is_active=True).first()

    if not account:
        account = FinancialAccount.objects.create(
            user=user,
            name='Checking Account',
            account_type='checking',
            institution='Demo Bank',
        )

    categories = {}
    for name in ['Groceries', 'Dining', 'Transportation', 'Shopping', 'Entertainment', 'Utilities', 'Healthcare', 'Income']:
        cat, _ = TransactionCategory.objects.get_or_create(name=name, defaults={'is_system': True})
        categories[name.lower()] = cat

    imported = 0
    duplicates = 0
    errors = []

    if not import_obj.filename or not default_storage.exists(import_obj.filename):
        import_obj.errors = ['File not found']
        import_obj.status = 'failed'
        import_obj.save()
        return

    try:
        raw_text = extract_text_from_file(import_obj.filename)
    except Exception as e:
        import_obj.errors = [f'Text extraction failed: {e}']
        import_obj.status = 'failed'
        import_obj.save()
        return

    parsed = parse_document_text(raw_text, import_obj.filename)

    if parsed.get('document_type') == 'bank_statement' and parsed.get('transactions'):
        for txn in parsed['transactions']:
            amount = txn.get('amount', 'non')
            if amount == 'non':
                continue
            merchant = txn.get('merchant', 'Unknown')
            if merchant == 'non':
                merchant = 'Unknown'
            date_val = txn.get('date', 'non')
            txn_date = None
            if date_val and date_val != 'non':
                try:
                    txn_date = dt.strptime(date_val, '%Y-%m-%d').date()
                except ValueError:
                    txn_date = None
            if not txn_date:
                txn_date = timezone.now().date()

            exists = Transaction.objects.filter(
                user=user,
                date=txn_date,
                amount=abs(float(amount)),
                merchant_name=merchant,
            ).exists()
            if exists:
                duplicates += 1
                continue

            cat_key = str(txn.get('category', '')).lower()
            category = categories.get(cat_key)
            txn_type = 'credit' if float(amount) > 0 else 'debit'

            Transaction.objects.create(
                user=user,
                account=account,
                amount=Decimal(str(abs(float(amount)))),
                transaction_type=txn_type,
                merchant_name=merchant[:200],
                description=merchant[:200],
                category=category,
                date=txn_date,
                posted_date=txn_date,
                status='posted',
                metadata={'import_id': str(import_obj.id), 'source': 'document_upload'},
            )
            imported += 1
    else:
        amount = parsed.get('amount', 'non')
        merchant = parsed.get('merchant', 'non')
        if amount != 'non' and merchant != 'non':
            date_val = parsed.get('date', 'non')
            txn_date = None
            if date_val and date_val != 'non':
                try:
                    txn_date = dt.strptime(date_val, '%Y-%m-%d').date()
                except ValueError:
                    txn_date = None
            if not txn_date:
                txn_date = timezone.now().date()

            exists = Transaction.objects.filter(
                user=user,
                date=txn_date,
                amount=abs(float(amount)),
                merchant_name=merchant,
            ).exists()
            if exists:
                duplicates += 1
            else:
                cat_key = str(parsed.get('category', '')).lower()
                category = categories.get(cat_key)
                Transaction.objects.create(
                    user=user,
                    account=account,
                    amount=Decimal(str(abs(float(amount)))),
                    transaction_type='debit',
                    merchant_name=merchant[:200],
                    description=merchant[:200],
                    category=category,
                    date=txn_date,
                    posted_date=txn_date,
                    status='posted',
                    metadata={'import_id': str(import_obj.id), 'source': 'document_upload'},
                )
                imported += 1

    import_obj.total_rows = imported + duplicates
    import_obj.imported_count = imported
    import_obj.duplicate_count = duplicates
    import_obj.error_count = len(errors)
    import_obj.errors = errors[:50]
    import_obj.save()


def process_csv_import(import_obj):
    from transactions.models import Transaction, FinancialAccount, TransactionCategory
    from django.core.files.storage import default_storage
    import io

    user = import_obj.user
    account = import_obj.account or FinancialAccount.objects.filter(user=user, is_active=True).first()

    if not account:
        account = FinancialAccount.objects.create(
            user=user,
            name='Checking Account',
            account_type='checking',
            institution='Demo Bank',
        )

    categories = {}
    for name in ['Groceries', 'Dining', 'Transportation', 'Shopping', 'Entertainment', 'Utilities', 'Healthcare', 'Income']:
        cat, _ = TransactionCategory.objects.get_or_create(name=name, defaults={'is_system': True})
        categories[name.lower()] = cat

    imported = 0
    duplicates = 0
    errors = []
    rows = []

    if import_obj.filename and default_storage.exists(import_obj.filename):
        try:
            with default_storage.open(import_obj.filename, 'rb') as f:
                df = pd.read_csv(f)
            rows = _normalize_csv_rows(df)
        except Exception as e:
            errors.append(f"CSV parse error: {e}")
    else:
        from transactions.sample_transactions import get_sample_transactions
        rows = [
            {
                'date': t['date'],
                'merchant': t['merchant'],
                'amount': t['amount'],
                'category': t['category'],
            }
            for t in get_sample_transactions()
        ]

    for i, txn_data in enumerate(rows):
        try:
            parsed_date = _parse_import_date(txn_data.get('date'))
            amount = Decimal(str(txn_data['amount']))
            merchant = str(txn_data.get('merchant', txn_data.get('description', 'Unknown')))[:200]

            if not parsed_date:
                errors.append(f"Row {i + 1}: invalid date")
                continue

            exists = Transaction.objects.filter(
                user=user,
                date=parsed_date,
                amount=abs(amount),
                merchant_name=merchant,
            ).exists()

            if exists:
                duplicates += 1
                continue

            cat_key = str(txn_data.get('category', '')).lower()
            category = categories.get(cat_key)
            txn_type = 'credit' if amount > 0 else 'debit'

            Transaction.objects.create(
                user=user,
                account=account,
                amount=Decimal(str(abs(amount))),
                transaction_type=txn_type,
                merchant_name=merchant,
                description=merchant,
                category=category,
                date=parsed_date,
                posted_date=parsed_date,
                status='posted',
                metadata={'import_id': str(import_obj.id)},
            )
            imported += 1
        except Exception as e:
            errors.append(f"Row {i + 1}: {str(e)}")

    import_obj.total_rows = len(rows)
    import_obj.imported_count = imported
    import_obj.duplicate_count = duplicates
    import_obj.error_count = len(errors)
    import_obj.errors = errors[:50]
    import_obj.save()


def _normalize_csv_rows(df):
    """Map common CSV column names to a standard shape."""
    col_map = {}
    for col in df.columns:
        lower = col.strip().lower()
        if lower in ('date', 'transaction date', 'posted date', 'posting date'):
            col_map['date'] = col
        elif lower in ('amount', 'transaction amount', 'debit', 'credit'):
            col_map['amount'] = col
        elif lower in ('merchant', 'merchant name', 'description', 'payee', 'name'):
            col_map['merchant'] = col
        elif lower in ('category', 'type', 'transaction type'):
            col_map['category'] = col

    rows = []
    for _, row in df.iterrows():
        if row.isna().all():
            continue
        amount_val = row.get(col_map.get('amount', ''), 0)
        try:
            amount = float(str(amount_val).replace(',', '').replace('$', ''))
        except (ValueError, TypeError):
            continue
        if amount == 0:
            continue
        rows.append({
            'date': row.get(col_map.get('date', ''), ''),
            'amount': amount,
            'merchant': row.get(col_map.get('merchant', ''), 'Unknown'),
            'category': row.get(col_map.get('category', ''), ''),
        })
    return rows


def _parse_import_date(value):
    from datetime import datetime
    if not value or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, 'date'):
        return value.date()
    text = str(value).strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y', '%Y/%m/%d', '%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(text).date()
    except Exception:
        return None


@shared_task(bind=True, max_retries=2)
def process_receipt(self, receipt_id):
    from transactions.models import Receipt
    from transactions.receipt_processing import process_receipt_record

    try:
        receipt = Receipt.objects.get(id=receipt_id)
        receipt.status = 'processing'
        receipt.save(update_fields=['status'])
        process_receipt_record(receipt)
    except Exception as exc:
        receipt = Receipt.objects.get(id=receipt_id)
        receipt.status = 'failed'
        receipt.processing_error = str(exc)
        receipt.save(update_fields=['status', 'processing_error'])
        logger.error(f"Receipt {receipt_id} processing failed: {exc}")
        raise self.retry(exc=exc, countdown=30)


# Backwards-compatible exports used elsewhere
from transactions.receipt_processing import (  # noqa: E402
    parse_receipt_text,
    create_transaction_from_receipt,
    extract_text_from_image,
)


def process_receipt_with_paddleocr(receipt):
    text, _engine = extract_text_from_image(receipt)
    return text