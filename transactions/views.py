from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q, Sum, Count, Avg, StdDev
from django.utils import timezone
from django.core.files.storage import default_storage
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import csv
import io
import os
import pandas as pd

from .models import TransactionCategory, Transaction, Receipt, TransactionImport, MerchantCache
from .serializers import (
    TransactionCategorySerializer, TransactionSerializer, TransactionCreateSerializer,
    TransactionListSerializer, ReceiptSerializer, ReceiptUploadSerializer,
    TransactionImportSerializer, MerchantCacheSerializer
)
from assistant.models import Subscription
from assistant.tasks import detect_subscriptions, detect_anomalies


class TransactionCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TransactionCategory.objects.filter(is_system=True)
    serializer_class = TransactionCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user).select_related('account', 'category')
        
        # Filtering
        account_id = self.request.query_params.get('account')
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        start_date = self.request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        
        end_date = self.request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        merchant = self.request.query_params.get('merchant')
        if merchant:
            queryset = queryset.filter(merchant_name__icontains=merchant)
        
        transaction_type = self.request.query_params.get('type')
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
        
        is_recurring = self.request.query_params.get('is_recurring')
        if is_recurring is not None:
            queryset = queryset.filter(is_recurring=is_recurring.lower() == 'true')
        
        needs_review = self.request.query_params.get('needs_review')
        if needs_review is not None:
            queryset = queryset.filter(needs_review=needs_review.lower() == 'true')
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return TransactionListSerializer
        if self.action == 'create':
            return TransactionCreateSerializer
        return TransactionSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get spending summary for date range"""
        start_date = request.query_params.get('start_date', (date.today() - relativedelta(months=1)).isoformat())
        end_date = request.query_params.get('end_date', date.today().isoformat())
        
        queryset = self.get_queryset().filter(date__gte=start_date, date__lte=end_date)
        
        total_income = queryset.filter(transaction_type='credit').aggregate(Sum('amount'))['amount__sum'] or 0
        total_expenses = queryset.filter(transaction_type='debit').aggregate(Sum('amount'))['amount__sum'] or 0
        
        by_category = queryset.filter(transaction_type='debit').values('category__name', 'category__color').annotate(
            total=Sum('amount'), count=Count('id')
        ).order_by('-total')
        
        by_merchant = queryset.filter(transaction_type='debit').values('merchant_name').annotate(
            total=Sum('amount'), count=Count('id')
        ).order_by('-total')[:10]
        
        return Response({
            'period': {'start': start_date, 'end': end_date},
            'total_income': str(total_income),
            'total_expenses': str(abs(total_expenses)),
            'net': str(total_income + total_expenses),
            'by_category': list(by_category),
            'top_merchants': list(by_merchant),
            'transaction_count': queryset.count(),
        })
    
    @action(detail=False, methods=['get'])
    def monthly_trend(self, request):
        """Get monthly spending trend"""
        months = int(request.query_params.get('months', 12))
        end_date = date.today()
        start_date = end_date - relativedelta(months=months)
        
        queryset = self.get_queryset().filter(date__gte=start_date, date__lte=end_date)
        
        # Group by month
        from django.db.models.functions import TruncMonth
        monthly = queryset.annotate(month=TruncMonth('date')).values('month', 'transaction_type').annotate(
            total=Sum('amount')
        ).order_by('month')
        
        # Format for chart
        result = {}
        for item in monthly:
            month_key = item['month'].strftime('%Y-%m')
            if month_key not in result:
                result[month_key] = {'income': 0, 'expenses': 0}
            if item['transaction_type'] == 'credit':
                result[month_key]['income'] = float(item['total'] or 0)
            else:
                result[month_key]['expenses'] = float(abs(item['total'] or 0))
        
        return Response([
            {'month': k, 'income': v['income'], 'expenses': v['expenses'], 'net': v['income'] - v['expenses']}
            for k, v in sorted(result.items())
        ])
    
    @action(detail=True, methods=['post'])
    def categorize(self, request, pk=None):
        transaction = self.get_object()
        category_id = request.data.get('category_id')
        if category_id:
            try:
                category = TransactionCategory.objects.get(id=category_id)
                transaction.category = category
                transaction.save()
                return Response(TransactionSerializer(transaction).data)
            except TransactionCategory.DoesNotExist:
                return Response({'error': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'error': 'category_id required'}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def bulk_categorize(self, request):
        transaction_ids = request.data.get('transaction_ids', [])
        category_id = request.data.get('category_id')
        if not transaction_ids or not category_id:
            return Response({'error': 'transaction_ids and category_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            category = TransactionCategory.objects.get(id=category_id)
            updated = Transaction.objects.filter(
                id__in=transaction_ids, user=request.user
            ).update(category=category)
            return Response({'updated': updated})
        except TransactionCategory.DoesNotExist:
            return Response({'error': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)


class ReceiptViewSet(viewsets.ModelViewSet):
    serializer_class = ReceiptSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def get_queryset(self):
        return Receipt.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ReceiptUploadSerializer
        return ReceiptSerializer
    
    def perform_create(self, serializer):
        receipt = serializer.save(user=self.request.user)
        # Trigger async OCR processing
        from .tasks import process_receipt
        process_receipt.delay(str(receipt.id))
    
    @action(detail=True, methods=['post'])
    def reprocess(self, request, pk=None):
        receipt = self.get_object()
        receipt.status = 'uploaded'
        receipt.processing_error = ''
        receipt.save()
        from .tasks import process_receipt
        process_receipt.delay(str(receipt.id))
        return Response({'status': 'processing queued'})


class TransactionImportViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionImportSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_queryset(self):
        return TransactionImport.objects.filter(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        source = request.data.get('source', 'csv')
        account_id = request.data.get('account_id')

        if source == 'api':
            return self._import_from_mock_bank(request, account_id)

        if not file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        ext = os.path.splitext(file.name)[1].lower()
        ext_source_map = {
            '.csv': 'csv',
            '.txt': 'txt',
            '.pdf': 'pdf',
            '.docx': 'docx',
            '.doc': 'docx',
        }
        source = ext_source_map.get(ext, source)

        import_obj = TransactionImport.objects.create(
            user=request.user,
            source=source,
            filename=file.name,
            file_size=file.size,
            account_id=account_id if account_id else None,
            status='processing',
            started_at=timezone.now()
        )

        saved_path = default_storage.save(f'imports/{request.user.id}/{file.name}', file)
        import_obj.filename = saved_path
        import_obj.save(update_fields=['filename'])

        from .tasks import process_transaction_import
        try:
            process_transaction_import.delay(str(import_obj.id))
        except Exception:
            process_transaction_import(str(import_obj.id))

        return Response(TransactionImportSerializer(import_obj).data, status=status.HTTP_201_CREATED)

    def _import_from_mock_bank(self, request, account_id):
        """Import transactions from the mock bank endpoint (assessment sample data)."""
        from core.models import FinancialAccount
        from transactions.seed import ensure_sample_data

        account = None
        if account_id:
            account = FinancialAccount.objects.filter(user=request.user, id=account_id).first()
        account = account or FinancialAccount.objects.filter(user=request.user, is_active=True).first()

        if not account:
            account = FinancialAccount.objects.create(
                user=request.user,
                name='Checking Account',
                account_type='checking',
                institution='Demo Bank',
            )

        result = ensure_sample_data(request.user, account=account)
        if result.get('error'):
            return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'status': 'completed',
            'imported_count': result['imported'],
            'duplicate_count': result.get('duplicates', 0),
            'message': (
                f"Imported {result['imported']} transactions."
                if result['imported']
                else 'Sample data already loaded.'
            ),
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        import_obj = self.get_object()
        if import_obj.source == 'csv' and import_obj.filename:
            # Return first few rows for preview
            try:
                path = default_storage.path(import_obj.filename)
                df = pd.read_csv(path, nrows=5)
                return Response({
                    'columns': df.columns.tolist(),
                    'sample': df.to_dict('records')
                })
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'error': 'Preview not available for this source'}, status=status.HTTP_400_BAD_REQUEST)


class MerchantCacheViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MerchantCache.objects.all()
    serializer_class = MerchantCacheSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('q', '')
        if len(query) < 2:
            return Response([])
        
        merchants = MerchantCache.objects.filter(
            Q(name__icontains=query) | Q(normalized_name__icontains=query)
        )[:10]
        return Response(MerchantCacheSerializer(merchants, many=True).data)
    
    @action(detail=False, methods=['post'])
    def enrich(self, request):
        """Enrich merchant info from external API"""
        merchant_name = request.data.get('merchant_name')
        if not merchant_name:
            return Response({'error': 'merchant_name required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # This would call external API (e.g., Google Places, Yelp)
        # For now, create/update cache entry
        from .tasks import enrich_merchant
        enrich_merchant.delay(merchant_name)
        
        return Response({'status': 'enrichment queued'})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mock_bank_transactions(request):
    """
    Mock bank API endpoint returning sample transaction history.
    POST to /api/v1/imports/ with source=api to import into the user's account.
    """
    from transactions.sample_transactions import get_sample_transactions

    txns = get_sample_transactions()
    return Response({
        'account_id': 'mock-checking-001',
        'institution': 'Demo Bank',
        'transactions': txns,
        'count': len(txns),
    })