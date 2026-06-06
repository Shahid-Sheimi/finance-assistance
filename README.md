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
- Django 5.0+ with SQLite (configurable for PostgreSQL)
- Django REST Framework 3.15+ for API endpoints
- Celery 5.4+ for async task processing (receipt OCR, anomaly detection)
- Redis 5.0+ as broker for task queue
- PaddleOCR API for receipt OCR processing
- Google Gemini 1.12+ for conversational AI
- dj-rest-auth 2.6+ for authentication endpoints

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

## Features Covered & Completion Level

### Completed ✓
- **Core App**: Custom User model with email auth, UserProfile, FinancialAccount, UserPreference, UserContext
- **Transactions App**: Transaction CRUD, Receipt model with OCR, TransactionImport, MerchantCache
- **Assistant App**: Conversation/Message system, Subscription detection, Anomaly detection
- **Budgets App**: Budget with period tracking, Alert system
- **Insights App**: Spending insights, Savings recommendations, Cash flow projections
- **API Layer**: DRF routers with all endpoints under `/api/v1/`
- **Async Processing**: Celery setup with Redis broker for OCR and detection tasks

### Stubbed ○
- Insights generation tasks (missing implementations)
- LLM context extraction integration
- Multi-language receipt processing

## Key Architectural & Technical Decisions

### 1. Custom User Model
- Extended `AbstractUser` with email as username field
- Added explicit `related_name` to groups/user_permissions to avoid Django auth clashes
- Rationale: Enables future extensibility while maintaining Django's auth system compatibility

### 2. Receipt Processing Architecture
- PaddleOCR API chosen for better accuracy over local pytesseract/OpenCV
- Regex-based parsing for structured data extraction
- Trade-off: External API dependency vs. higher accuracy and less maintenance

### 3. Subscription Detection Algorithm
- Pattern-based detection using date intervals and amount consistency
- Confidence scoring (0-100) based on interval variance and amount patterns
- Supports monthly, weekly, quarterly, yearly patterns

### 4. Anomaly Detection Strategy
- Z-score statistical analysis (threshold 2.5) for unusual amounts
- Merchant novelty detection for first-time merchants
- Duplicate charge detection within 3-day windows

### 5. Async Task Architecture
- Celery with Redis broker for horizontal scaling capability
- Separate tasks for receipt OCR and detection algorithms
- Pattern allows worker scaling independent of web processes

### 6. Data Privacy & Security
- `.env` file for secrets (excluded from version control)
- SQLite for development, PostgreSQL configurable for production
- All user data isolated by foreign key relationships

## Assumptions, Trade-offs & Limitations

### Assumptions
- Users have stable internet connection for PaddleOCR API calls
- Receipts are primarily in English (multi-language support stubbed)
- Single currency per user (CurrencyField in UserProfile)
- Redis server available for Celery broker

### Trade-offs
- SQLite in dev vs. PostgreSQL in production (simplicity vs. scalability)
- External OCR service vs. local processing (accuracy vs. autonomy)
- Regex parsing vs. ML-based parsing (speed vs. robustness)

### Limitations
- No frontend UI implemented
- Limited external API integrations (no Plaid, Google Places)
- No comprehensive test suite
- Receipt OCR limited to English text
- Single-user focus (no family/organization sharing)

## What Was Intentionally Skipped or Stubbed

| Feature | Status | Reason |
|---------|--------|--------|
| Frontend UI | Skipped | Focus on backend/API first |
| Production deployment | Skipped | Out of scope for initial implementation |
| Plaid bank integration | Skipped | Requires external API keys |
| Google Places merchant lookup | Skipped | Would add API costs |
| Comprehensive tests | Skipped | Time constraint |
| Multi-language OCR | Stubbed | PaddleOCR supports it, not implemented |
| Insights task implementation | Stubbed | Placeholder for future work |

## Challenges Faced & How They Were Handled

1. **User model clashes**: Fixed M2M field reverse accessor conflicts by adding `related_name` to groups/user_permissions

2. **Admin configuration**: Removed non-existent `currency` field from UserPreferenceAdmin

3. **Allauth deprecation warnings**: Updated to newer `ACCOUNT_LOGIN_METHODS` and `ACCOUNT_SIGNUP_FIELDS` settings

4. **Missing static directory**: Created `/static` directory to satisfy Django's staticfiles check

5. **Missing URL configurations**: Created app-level `urls.py` files for core, transactions, assistant, budgets, and insights apps with DRF routers

6. **Missing task file**: Created `insights/tasks.py` with stub implementations for report generation functions

## My Thinking Process & Decision Rationale

### Backend-First Approach
- Prioritized API and models first because frontend can be swapped independently
- Focused on data integrity and async processing patterns early
- Chose Django for rapid development and built-in admin

### Technology Selection
- **Gemini over OpenAI**: Google's API for cost-effective conversational AI
- **PaddleOCR over Tesseract**: Better accuracy, less maintenance overhead
- **Redis/Celery**: Industry standard for Django async processing

### Modularity Decisions
- Separated apps by domain (core, transactions, assistant, budgets, insights)
- Each app has isolated models and serializers for clean boundaries
- Task queue allows horizontal scaling without code changes

## Robustness Design

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