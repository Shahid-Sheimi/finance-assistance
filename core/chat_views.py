"""Multi-tenant chat API — every endpoint scoped to request.user."""
import json
import os
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from assistant.conversation_service import ConversationService
from assistant.memory import get_user_memory_summary, delete_user_memory_item, update_conversation_memory
from assistant.services import AssistantService
from transactions.receipt_processing import process_receipt_record
from transactions.seed import ensure_sample_data


def _parse_json(request):
    try:
        return json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return {}


def _conversation_service(user):
    return ConversationService(user)


@login_required
def chat_interface(request):
    ensure_sample_data(request.user)
    return render(request, 'assistant/chat.html', {
        'user_email': request.user.email,
    })


@login_required
@require_GET
def chat_conversations_list(request):
    svc = _conversation_service(request.user)
    conversations = svc.list_conversations()
    return JsonResponse({
        'conversations': [svc.serialize_conversation(c) for c in conversations],
    })


@login_required
@require_POST
def chat_conversation_create(request):
    body = _parse_json(request)
    svc = _conversation_service(request.user)
    conversation = svc.create_conversation(title=body.get('title', 'New Chat'))
    return JsonResponse(svc.serialize_conversation(conversation), status=201)


@login_required
@require_GET
def chat_conversation_detail(request, conversation_id):
    svc = _conversation_service(request.user)
    conversation = svc.get_conversation(conversation_id)
    messages = svc.get_messages(conversation_id, limit=200)
    data = svc.serialize_conversation(conversation)
    data['messages'] = [svc.serialize_message(m) for m in messages]
    return JsonResponse(data)


@login_required
@require_http_methods(['PATCH', 'POST'])
def chat_conversation_rename(request, conversation_id):
    body = _parse_json(request)
    title = body.get('title', '').strip()
    if not title:
        return JsonResponse({'error': 'Title required'}, status=400)
    svc = _conversation_service(request.user)
    conversation = svc.rename_conversation(conversation_id, title)
    return JsonResponse(svc.serialize_conversation(conversation))


@login_required
@require_http_methods(['DELETE', 'POST'])
def chat_conversation_delete(request, conversation_id):
    svc = _conversation_service(request.user)
    svc.hard_delete_conversation(conversation_id)
    remaining = svc.list_conversations()
    default = svc.create_conversation() if not remaining else remaining[0]
    return JsonResponse({
        'deleted': True,
        'active_conversation': svc.serialize_conversation(default),
    })


@login_required
@require_GET
def chat_memory(request):
    return JsonResponse(get_user_memory_summary(request.user))


@login_required
@require_http_methods(['DELETE', 'POST'])
def chat_memory_delete(request, memory_id):
    if delete_user_memory_item(request.user, memory_id):
        return JsonResponse({'deleted': True})
    return JsonResponse({'error': 'Not found'}, status=404)


@login_required
@require_POST
def chat_send(request):
    body = _parse_json(request)
    content = (body.get('message') or request.POST.get('message', '')).strip()
    conversation_id = body.get('conversation_id')

    if not content:
        return JsonResponse({'error': 'Message is required'}, status=400)

    svc = _conversation_service(request.user)
    if conversation_id:
        conversation = svc.get_conversation(conversation_id)
    else:
        conversation = svc.get_or_create_default()

    svc.add_message(conversation.id, 'user', content)

    service = AssistantService(request.user)
    response = service.process_message(content, conversation)

    assistant_msg = svc.add_message(
        conversation.id,
        'assistant',
        response['content'],
        metadata=response.get('metadata', {}),
        tokens_used=response.get('tokens_used', 0),
        model_used=response.get('model_used', ''),
    )

    conversation.refresh_from_db()
    return JsonResponse({
        'content': response['content'],
        'metadata': response.get('metadata', {}),
        'message_id': str(assistant_msg.id),
        'conversation': svc.serialize_conversation(conversation),
    })


@login_required
@require_POST
def chat_upload_receipt(request):
    from transactions.models import Receipt

    image = request.FILES.get('receipt_image')
    if not image:
        return JsonResponse({'error': 'No image provided'}, status=400)

    body = _parse_json(request) if request.content_type == 'application/json' else {}
    conversation_id = body.get('conversation_id') or request.POST.get('conversation_id')

    svc = _conversation_service(request.user)
    if conversation_id:
        conversation = svc.get_conversation(conversation_id)
    else:
        conversation = svc.get_or_create_default()

    receipt = Receipt.objects.create(
        user=request.user,
        image=image,
        original_filename=image.name,
        status='uploaded',
    )

    svc.add_message(
        conversation.id,
        'user',
        f'[Receipt uploaded: {image.name}]',
        metadata={'receipt_id': str(receipt.id)},
    )

    try:
        receipt.status = 'processing'
        receipt.save(update_fields=['status'])
        content = process_receipt_record(receipt)
    except Exception as e:
        receipt.status = 'failed'
        receipt.processing_error = str(e)
        receipt.save(update_fields=['status', 'processing_error'])
        content = (
            f"I couldn't fully read that image: {e}\n\n"
            "Tips: use a clear photo, good lighting, and avoid blur."
        )

    svc.add_message(conversation.id, 'assistant', content)
    update_conversation_memory(conversation)
    conversation.refresh_from_db()

    return JsonResponse({
        'content': content,
        'conversation': svc.serialize_conversation(conversation),
    })


@login_required
@require_POST
def chat_upload_document(request):
    """Upload a document (CSV, TXT, PDF, DOCX) and import transactions from it."""
    from transactions.models import TransactionImport, Transaction
    from transactions.receipt_processing import (
        extract_text_from_file,
        parse_document_text,
        _categorize_merchant,
    )
    from django.core.files.storage import default_storage
    from datetime import datetime as dt

    uploaded = request.FILES.get('document') or request.FILES.get('receipt_image')
    if not uploaded:
        return JsonResponse({'error': 'No file provided'}, status=400)

    body = _parse_json(request) if request.content_type == 'application/json' else {}
    conversation_id = body.get('conversation_id') or request.POST.get('conversation_id')

    svc = _conversation_service(request.user)
    if conversation_id:
        conversation = svc.get_conversation(conversation_id)
    else:
        conversation = svc.get_or_create_default()

    svc.add_message(
        conversation.id,
        'user',
        f'[Uploaded document: {uploaded.name}]',
    )

    ext = os.path.splitext(uploaded.name)[1].lower()
    saved_path = default_storage.save(f'imports/{request.user.id}/{uploaded.name}', uploaded)

    try:
        raw_text = extract_text_from_file(saved_path, uploaded.content_type or '')
        parsed = parse_document_text(raw_text, uploaded.name)

        if parsed.get('document_type') == 'bank_statement' and parsed.get('transactions'):
            imported = _import_parsed_transactions(request.user, parsed)
            msg = f"Document processed. Imported {imported} transaction(s) from {uploaded.name}."
            if imported == 0:
                msg = f"Document processed but no new transactions found (duplicates or incomplete data)."
        elif parsed.get('document_type') == 'receipt':
            amount = parsed.get('amount', 'non')
            merchant = parsed.get('merchant', 'non')
            date_val = parsed.get('date', 'non')
            category = parsed.get('category', 'non')
            if amount != 'non' and merchant != 'non':
                _import_single_transaction(request.user, parsed)
                msg = (
                    f"Receipt processed from {uploaded.name}:\n"
                    f"  Merchant: {merchant}\n"
                    f"  Date: {date_val}\n"
                    f"  Amount: ${amount}\n"
                    f"  Category: {category}"
                )
            else:
                parts = [f"Receipt processed from {uploaded.name}:"]
                if merchant != 'non':
                    parts.append(f"  Merchant: {merchant}")
                if date_val != 'non':
                    parts.append(f"  Date: {date_val}")
                if amount != 'non':
                    parts.append(f"  Amount: ${amount}")
                parts.append("Some fields could not be read.")
                msg = '\n'.join(parts)
        else:
            msg = f"Document processed from {uploaded.name}. Text extracted but no transaction data matched."

    except Exception as e:
        msg = f"Could not process {uploaded.name}: {e}"

    svc.add_message(conversation.id, 'assistant', msg)
    update_conversation_memory(conversation)
    conversation.refresh_from_db()

    return JsonResponse({
        'content': msg,
        'conversation': svc.serialize_conversation(conversation),
    })


def _get_or_create_account(user):
    from core.models import FinancialAccount
    account = FinancialAccount.objects.filter(user=user, is_active=True).first()
    if not account:
        account = FinancialAccount.objects.create(
            user=user,
            name='Checking Account',
            account_type='checking',
            institution='Demo Bank',
        )
    return account


def _import_single_transaction(user, parsed):
    from transactions.models import Transaction, TransactionCategory
    from decimal import Decimal

    account = _get_or_create_account(user)

    amount = parsed.get('amount', 'non')
    if amount == 'non':
        return False

    merchant = parsed.get('merchant', 'Unknown')
    if merchant == 'non':
        merchant = 'Unknown'

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
        return False

    category_name = parsed.get('category', 'non')
    category = None
    if category_name and category_name != 'non':
        category, _ = TransactionCategory.objects.get_or_create(
            name=category_name.capitalize(),
            defaults={'is_system': True},
        )

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
        metadata={'source': 'document_upload'},
    )
    return True


def _import_parsed_transactions(user, parsed):
    from transactions.models import Transaction, TransactionCategory

    account = _get_or_create_account(user)
    imported = 0

    for txn in parsed.get('transactions', []):
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
            continue

        category_name = txn.get('category', 'non')
        category = None
        if category_name and category_name != 'non':
            category, _ = TransactionCategory.objects.get_or_create(
                name=category_name.capitalize(),
                defaults={'is_system': True},
            )

        Transaction.objects.create(
            user=user,
            account=account,
            amount=Decimal(str(abs(float(amount)))),
            transaction_type='credit' if float(amount) > 0 else 'debit',
            merchant_name=merchant[:200],
            description=merchant[:200],
            category=category,
            date=txn_date,
            posted_date=txn_date,
            status='posted',
            metadata={'source': 'document_upload'},
        )
        imported += 1

    return imported
