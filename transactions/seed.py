"""Seed demo transaction data for a user."""
from decimal import Decimal
from django.utils import timezone

from transactions.models import Transaction, TransactionCategory, TransactionImport
from transactions.sample_transactions import get_sample_transactions


CATEGORY_NAMES = [
    'Groceries', 'Dining', 'Transportation', 'Shopping',
    'Entertainment', 'Utilities', 'Healthcare', 'Income',
]


def seed_sample_transactions(user, account=None, force=False):
    """
    Import sample transactions for a user.
    Skips if the user already has data unless force=True.
    Returns dict with imported count and status.
    """
    from core.models import FinancialAccount

    if not force and Transaction.objects.filter(user=user).exists():
        return {'imported': 0, 'skipped': True, 'message': 'User already has transactions'}

    account = account or FinancialAccount.objects.filter(user=user, is_active=True).first()
    if not account:
        return {'imported': 0, 'error': 'No financial account found'}

    categories = {}
    for name in CATEGORY_NAMES:
        cat, _ = TransactionCategory.objects.get_or_create(name=name, defaults={'is_system': True})
        categories[name.lower()] = cat

    import_obj = TransactionImport.objects.create(
        user=user,
        account=account,
        source='api',
        filename='sample_seed',
        status='processing',
        started_at=timezone.now(),
    )

    imported = 0
    duplicates = 0
    rows = get_sample_transactions()

    for txn_data in rows:
        parsed_date = txn_data['date']
        if isinstance(parsed_date, str):
            from datetime import datetime
            parsed_date = datetime.strptime(parsed_date, '%Y-%m-%d').date()

        amount = Decimal(str(txn_data['amount']))
        merchant = txn_data['merchant']

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
        Transaction.objects.create(
            user=user,
            account=account,
            amount=abs(amount),
            transaction_type='credit' if amount > 0 else 'debit',
            merchant_name=merchant,
            description=merchant,
            category=categories.get(cat_key),
            date=parsed_date,
            posted_date=parsed_date,
            status='posted',
            metadata={'import_id': str(import_obj.id), 'source': 'sample_seed'},
        )
        imported += 1

    import_obj.total_rows = len(rows)
    import_obj.imported_count = imported
    import_obj.duplicate_count = duplicates
    import_obj.status = 'completed'
    import_obj.completed_at = timezone.now()
    import_obj.save()

    return {
        'imported': imported,
        'duplicates': duplicates,
        'total': len(rows),
        'skipped': False,
    }


def ensure_sample_data(user, account=None):
    """Seed sample data if the user has no transactions at all."""
    if Transaction.objects.filter(user=user).exists():
        return {'imported': 0, 'skipped': True, 'message': 'User already has transactions'}

    from core.models import FinancialAccount as FA
    account = account or FA.objects.filter(user=user, is_active=True).first()
    if not account:
        account = FA.objects.create(
            user=user,
            name='Checking Account',
            account_type='checking',
            institution='Demo Bank',
        )

    return seed_sample_transactions(user, account=account, force=True)
