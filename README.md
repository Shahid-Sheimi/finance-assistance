# Personal Finance Assistant

A Django-based personal finance application with AI-powered receipt processing, transaction categorization, budget tracking, and anomaly detection.

## Setup Instructions

```bash
# Clone the repository
git clone https://github.com/Shahid-Sheimi/finance-assistance.git
cd finance-assistance

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your values

# Run migrations
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

## Architecture

### Apps Structure
- **core**: User management, profiles, financial accounts, user preferences and context
- **transactions**: Transaction CRUD, receipt OCR processing, transaction imports, merchant cache
- **assistant**: Chat conversations, messages, subscriptions, anomaly detection
- **budgets**: Budgets and alerts
- **insights**: Spending insights, savings recommendations, cash flow projections

### Tech Stack
- Django 4.2 with SQLite (configurable for PostgreSQL)
- Django REST Framework for API endpoints
- Celery for async task processing (receipt OCR, anomaly detection)
- PaddleOCR API for receipt OCR processing
- Google Gemini 2.0 Flash for conversational AI
- dj-rest-auth for authentication endpoints

### Conversational Assistant powered by Gemini
- Natural language queries about spending, budgets, and transactions
- Intent detection for spending queries, budget tracking, subscriptions
- Context-aware responses using user's transaction history
- Receipt upload guidance and processing integration

## Features Implemented

### Core App
- Custom User model with email authentication
- UserProfile for phone, timezone, currency preferences
- FinancialAccount for bank accounts
- UserPreference for payday and notification settings
- UserContext for storing extracted facts/rules/goals

### Transactions App
- Transaction model with categories, merchants, amounts
- Receipt model with image upload and OCR processing
- TransactionImport for CSV/bank API imports
- MerchantCache for merchant categorization

### Assistant App
- Conversation/Message system for chat interface
- Subscription detection via pattern analysis
- Anomaly detection for unusual spending

### Budgets App
- Budget with period-based tracking (weekly/monthly/quarterly/yearly)
- Alert system for threshold notifications

### Insights App
- Spending insights generation
- Savings recommendations
- Cash flow projections

## API Endpoints

All endpoints are under `/api/v1/`:

| Resource | Endpoints |
|----------|-----------|
| Users | `/users/`, `/users/me/` |
| Profiles | `/profiles/`, `/profiles/{id}/` |
| Accounts | `/accounts/`, `/accounts/sync_balance/` |
| Transactions | `/transactions/`, `/transactions/summary/`, `/transactions/monthly_trend/` |
| Receipts | `/receipts/`, `/receipts/reprocess/` |
| Categories | `/categories/` |
| Conversations | `/conversations/`, `/conversations/send_message/`, `/conversations/active/` |
| Subscriptions | `/subscriptions/`, `/subscriptions/detect/`, `/subscriptions/total_monthly/` |
| Anomalies | `/anomalies/`, `/anomalies/unreviewed/` |
| Budgets | `/budgets/`, `/budgets/overview/`, `/budgets/check_alerts/` |

## Decisions & Trade-offs

### 1. Custom User Model
- Extended `AbstractUser` with email as username field
- Added explicit `related_name` to groups/user_permissions to avoid clashes with auth.User
- Decision: Custom user allows future extensibility while keeping Django's auth system

### 2. Receipt Processing
- PaddleOCR API for high-accuracy OCR text extraction
- Regex-based parsing for merchant, date, total, tax, tip extraction
- Trade-off: Using external OCR service for better accuracy vs. local pytesseract/OpenCV

### 3. Subscription Detection
- Pattern-based detection using date intervals and amount consistency
- Detects monthly, weekly, quarterly, yearly patterns
- Confidence scoring based on interval variance and amount consistency

### 4. Anomaly Detection
- Statistical analysis using z-scores for unusual amounts
- Merchant novelty detection
- Duplicate charge detection within 3-day windows

### 5. Celery Tasks
- Async processing for receipt OCR and detection tasks
- Redis broker for task queue
- Pattern allows for horizontal scaling

### 6. Missing Features (Time Constraints)
- No frontend (would use React/Vue with the DRF API)
- Limited external API integrations (Plaid, Google Places, etc.)
- No comprehensive tests
- OCR limited to English text (could add language detection)

## Challenges Handled

1. **User model clashes**: Fixed M2M field reverse accessor conflicts by adding `related_name` to groups/user_permissions

2. **Admin configuration**: Removed non-existent `currency` field from UserPreferenceAdmin

3. **Allauth deprecation warnings**: Updated to newer `ACCOUNT_LOGIN_METHODS` and `ACCOUNT_SIGNUP_FIELDS` settings

4. **Missing static directory**: Created `/static` directory to satisfy Django's staticfiles check

5. **Missing URL configurations**: Created app-level `urls.py` files for core, transactions, assistant, budgets, and insights apps with DRF routers

6. **Missing task file**: Created `insights/tasks.py` with stub implementations for report generation functions

## Edge Case Handling

### Receipt Processing
- **Blurry images**: PaddleOCR API handles various image qualities
- **Rotated receipts**: PaddleOCR automatically handles orientation
- **Cut-off receipts**: Falls back gracefully with partial data extraction
- **Non-English text**: PaddleOCR supports multi-language text extraction

### Transaction Import
- **Duplicates**: Detected by matching date, amount, and merchant
- **Missing fields**: Handled with defaults and optional fields
- **Odd formatting**: CSV parsing with pandas handles various formats
- **Junk rows**: Skipped during processing with error logging

### Subscription Detection
- **Insufficient data**: Requires minimum 2 transactions to detect patterns
- **Irregular patterns**: Low confidence scores filter out noise
- **Contradictory data**: Confidence scoring weighs multiple factors

### Anomaly Detection
- **Ambiguous patterns**: Uses z-scores (threshold 2.5) for statistical significance
- **Insufficient baseline**: Requires minimum 10 transactions for analysis
- **Unknown categories**: Gracefully handles uncategorized transactions

## Completion Status

### Completed ✓
- Project structure with 5 Django apps
- All models defined with proper relationships
- REST API endpoints via DRF routers
- Receipt OCR processing pipeline
- Subscription and anomaly detection algorithms
- Budget tracking with alerts
- Async task processing setup

### Not Started ✗
- Frontend UI
- Production deployment configuration
- External API integrations (Plaid, external merchant lookup)
- Comprehensive test suite

### Stubbed/Half-Implemented ○
- Insights generation tasks (stub implementations)
- LLM integration for context extraction
- Receipt language handling beyond English

## Robustness Design (Handling "Unexpected" Cases)

### 1. Blurry/Rotated/Cut-off Receipts
- **PaddleOCR API**: Handles image preprocessing, orientation, and quality automatically
- **Confidence scoring**: Each receipt gets a confidence score based on extracted fields; low-confidence receipts go to manual review
- **Graceful degradation**: Missing fields don't crash the system; partial data is saved

### 2. Messy Transaction Data
- **Duplicate detection**: Same date/amount/merchant combinations are rejected
- **Optional fields**: Most transaction fields allow null/blank values
- **Multiple date formats**: Receipt parser handles MM/DD/YYYY, DD/MM/YYYY, and text dates

### 3. Ambiguous User Questions
- **Context extraction**: UserContext model stores facts/rules/goals that guide responses
- **Confidence scores**: Assistant can indicate uncertainty levels
- **Action suggestions**: Recommendations include action steps when data supports them

### 4. Insufficient Data
- **Minimum thresholds**: Subscription detection requires 2+ transactions; anomaly detection requires 10+ baseline transactions
- **Clear error messages**: Tasks log when insufficient data exists for analysis

### 5. Contradictory Information
- **Confidence weighting**: Multiple data points are weighted; inconsistent patterns get lower scores
- **Source tracking**: All context records track their source for traceability

### 6. Performance Optimization
- **Async processing**: Heavy tasks (OCR, detection) run in Celery workers
- **Database indexes**: Optimized for common queries (user+date, user+category)
- **Pagination**: API defaults to 20 items per page