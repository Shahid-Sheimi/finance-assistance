from django.test import TestCase
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal


class CategorizeMerchantTest(TestCase):
    def test_groceries_merchant(self):
        from transactions.receipt_processing import _categorize_merchant
        self.assertEqual(_categorize_merchant('Whole Foods Market'), 'Groceries')
        self.assertEqual(_categorize_merchant('Trader Joes'), 'Groceries')

    def test_dining_merchant(self):
        from transactions.receipt_processing import _categorize_merchant
        self.assertEqual(_categorize_merchant('Starbucks Coffee'), 'Dining')
        self.assertEqual(_categorize_merchant('McDonalds'), 'Dining')

    def test_transportation_merchant(self):
        from transactions.receipt_processing import _categorize_merchant
        self.assertEqual(_categorize_merchant('Shell Gas Station'), 'Transportation')
        self.assertEqual(_categorize_merchant('Uber Ride'), 'Transportation')

    def test_entertainment_merchant(self):
        from transactions.receipt_processing import _categorize_merchant
        self.assertEqual(_categorize_merchant('Netflix Subscription'), 'Entertainment')
        self.assertEqual(_categorize_merchant('Spotify Premium'), 'Entertainment')

    def test_healthcare_merchant(self):
        from transactions.receipt_processing import _categorize_merchant
        self.assertEqual(_categorize_merchant('CVS Pharmacy'), 'Healthcare')
        self.assertEqual(_categorize_merchant('Planet Fitness'), 'Healthcare')

    def test_shopping_merchant(self):
        from transactions.receipt_processing import _categorize_merchant
        self.assertEqual(_categorize_merchant('Amazon Purchase'), 'Shopping')
        self.assertEqual(_categorize_merchant('Ebay'), 'Shopping')

    def test_utilities_merchant(self):
        from transactions.receipt_processing import _categorize_merchant
        self.assertEqual(_categorize_merchant('Electric Bill'), 'Utilities')
        self.assertEqual(_categorize_merchant('Comcast Internet'), 'Utilities')

    def test_unknown_merchant(self):
        from transactions.receipt_processing import _categorize_merchant
        self.assertEqual(_categorize_merchant('Unknown Merchant XYZ'), 'Other')
        self.assertEqual(_categorize_merchant('Something Random'), 'Other')


class ExtractTextFromFileTest(TestCase):
    @patch('transactions.receipt_processing.default_storage')
    def test_txt_file_extraction(self, mock_storage):
        from transactions.receipt_processing import extract_text_from_file
        mock_storage.exists.return_value = True
        mock_file = MagicMock()
        mock_file.__enter__ = Mock(return_value='Sample receipt text\nMerchant: Test Store\nTotal: $25.00')
        mock_file.__exit__ = Mock(return_value=False)
        mock_storage.open.return_value = mock_file
        
        result = extract_text_from_file('test.txt')
        self.assertIn('Sample receipt text', result)

    def test_unknown_extension(self):
        from transactions.receipt_processing import extract_text_from_file
        result = extract_text_from_file('/path/to/file.xyz')
        self.assertEqual(result, '')


class ParseReceiptTextTest(TestCase):
    def test_extracts_total_amount(self):
        from transactions.receipt_processing import parse_receipt_text
        text = 'Test Store\nTotal: $42.99\nThank you!'
        result = parse_receipt_text(text)
        self.assertEqual(result['total_amount'], Decimal('42.99'))

    def test_extracts_date(self):
        from transactions.receipt_processing import parse_receipt_text
        text = 'Store\n03/15/2024\nTotal: $10.00'
        result = parse_receipt_text(text)
        self.assertIsNotNone(result['date'])

    def test_extracts_merchant(self):
        from transactions.receipt_processing import parse_receipt_text
        text = 'Whole Foods Market\nTotal: $50.00'
        result = parse_receipt_text(text)
        self.assertEqual(result['merchant_name'], 'Whole Foods Market')

    def test_extracts_items(self):
        from transactions.receipt_processing import parse_receipt_text
        text = 'Apples $3.50\nBread $2.99\nTotal: $6.49'
        result = parse_receipt_text(text)
        self.assertGreaterEqual(len(result['items']), 1)
