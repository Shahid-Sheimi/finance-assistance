# Sample transaction templates — dates are generated relative to today
from datetime import date
from dateutil.relativedelta import relativedelta


def get_sample_transactions(reference_date=None):
    """Build ~18 months of sample transactions ending on reference_date (default: today)."""
    if reference_date is None:
        reference_date = date.today()

    transactions = []

    for months_ago in range(17, -1, -1):
        ref = reference_date - relativedelta(months=months_ago)
        y, m = ref.year, ref.month
        last_day = (ref.replace(day=1) + relativedelta(months=1, days=-1)).day

        def d(day):
            return date(y, m, min(day, last_day)).isoformat()

        transactions.extend([
            {'date': d(1), 'merchant': 'Rent Payment', 'amount': -1550.00, 'category': 'utilities'},
            {'date': d(2), 'merchant': 'Salary Deposit', 'amount': 3200.00, 'category': 'income'},
            {'date': d(5), 'merchant': 'Spotify', 'amount': -11.99, 'category': 'entertainment'},
            {'date': d(8), 'merchant': 'Whole Foods', 'amount': -88.50, 'category': 'groceries'},
            {'date': d(12), 'merchant': 'Shell Gas', 'amount': -52.00, 'category': 'transportation'},
            {'date': d(15), 'merchant': 'Starbucks', 'amount': -14.25, 'category': 'dining'},
            {'date': d(17), 'merchant': 'Netflix', 'amount': -17.99, 'category': 'entertainment'},
            {'date': d(20), 'merchant': 'Planet Fitness', 'amount': -29.99, 'category': 'healthcare'},
            {'date': d(22), 'merchant': 'Amazon', 'amount': -67.00, 'category': 'shopping'},
        ])

        if m in (3, 6, 9, 12):
            transactions.append(
                {'date': d(28), 'merchant': 'Electric Bill', 'amount': -135.00, 'category': 'utilities'}
            )

    # Extra activity in the current month up to today
    if reference_date.day >= 3:
        transactions.append(
            {'date': reference_date.replace(day=3).isoformat(), 'merchant': 'Trader Joes', 'amount': -74.20, 'category': 'groceries'}
        )
    if reference_date.day >= 4:
        transactions.append(
            {'date': reference_date.replace(day=4).isoformat(), 'merchant': 'DoorDash', 'amount': -42.00, 'category': 'dining'}
        )
    if reference_date.day >= 6:
        transactions.append(
            {'date': reference_date.isoformat(), 'merchant': 'Unknown Merchant XYZ', 'amount': -250.00, 'category': 'shopping'}
        )

    return transactions


# Backwards-compatible static list (generated at import time)
SAMPLE_TRANSACTIONS = get_sample_transactions()
