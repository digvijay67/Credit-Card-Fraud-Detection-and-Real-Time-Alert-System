# Credit Card Fraud Detection and Real-Time Alert System

A local demonstration of transaction fraud scoring and review workflows. Users
can create an account, submit a simulated payment, and immediately see a model
classification, relative risk score, and feature explanation. Administrators can
review alerts, analytics, and model metrics.

> **Demo only:** This project does not connect to a real bank, issue cards, move
> funds, or send email or WhatsApp messages. Notification screens show stored
> previews only. Model predictions are decision-support signals, not proof of
> fraud.

## Features

- User registration and login, with administrator-only analytics and alert
  review.
- Per-transaction predictions from Random Forest, XGBoost, or Logistic
  Regression.
- Risk scores from 0 to 100, model-specific feature explanations, and
  transaction history.
- Simulated MGM Bank accounts with an atomic transaction ledger and idempotent
  payment processing.
- Email and WhatsApp notification previews, fraud alerts, and daily/monthly
  dashboard analytics.
- INR (₹) display for account limits, balances, transactions, and notification
  previews. Existing demo amounts are displayed as INR; no currency conversion
  is performed.

## Demo

[![Watch the project walkthrough](docs/media/03-payment-result.png)](docs/media/project-demo.webm)

[Watch or download the 18-second walkthrough (WebM)](docs/media/project-demo.webm).
It covers the payment flow, risk review, simulated accounts, alerts, and history.

### Screenshots

- [Project overview](docs/media/01-overview.png)
- [Payment form](docs/media/02-payment-form.png)
- [Payment result and explainable risk score](docs/media/03-payment-result.png)
- [Accounts, balances, and notification previews](docs/media/04-accounts-notifications.png)
- [Transaction history](docs/media/05-transactions.png)
- [Dashboard and INR balances](docs/media/dashboard.png)

The screenshots and video show a local simulation. Email and WhatsApp entries
are previews only; no messages are sent, and no real funds are moved.

## Technology

| Component | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Charts | Recharts |
| Backend | Python, Flask, REST API |
| Data and models | Pandas, NumPy, scikit-learn, XGBoost |
| Database | MySQL |
| Local HTTPS and containers | Nginx, Docker Compose |
| Tests | Pytest; TypeScript/Vite production build |

## Architecture

```text
React + TypeScript
       │ HTTPS / JSON
       ▼
Nginx reverse proxy ─── Flask API
                            ├── Authentication and transaction APIs
                            ├── Random Forest, XGBoost, Logistic Regression
                            └── MySQL
                                 ├── Users and predictions
                                 ├── Simulated accounts and ledger
                                 └── Alerts and message previews
```

The API derives behavioral features from the user's transaction history and
scores a submitted transaction synchronously. A failed prediction is reported
as an error rather than as a genuine result.

## Project layout

```text
.
├── backend/
│   ├── app/                 Flask API, models, prediction, training
│   ├── mgm_bank/            Simulated bank accounts and ledger
│   ├── tests/               Backend tests
│   ├── data/                Optional local training data
│   └── models/              Generated model artifacts
├── frontend/
│   └── src/                 React UI and shared utilities
├── nginx/                   Local HTTPS reverse proxy
├── scripts/                 Local development helpers
├── tls/                     Local development certificates
├── docker-compose.yml
└── README.md
```

## Run locally with HTTPS

### Prerequisites

- Docker Desktop with Docker Compose
- PowerShell

### Start the application

From the project directory:

1. Copy `.env.example` to `.env`. Set `JWT_SECRET_KEY` to a unique, strong
   secret. The example database credentials are for local development only;
   never expose MySQL outside the private Compose network or reuse demo
   credentials in production. Do not commit `.env`.
2. Generate a local certificate:

   ```powershell
   .\scripts\generate-dev-certs.ps1
   ```

3. Build and start the services:

   ```powershell
   docker compose up --build
   ```

4. Open [https://localhost](https://localhost). The local certificate is
   self-signed, so the browser may show a certificate warning. HTTP redirects
   to HTTPS; ports 80 and 443 bind to localhost.
5. In another terminal, create an administrator:

   ```powershell
   docker compose exec backend flask --app app.wsgi:app create-admin
   ```

   Follow the prompts to set the administrator email and password. Regular
   users can register from the sign-in page.

The default `DEMO_MODE=true` trains the models with generated synthetic data
when model files are missing. Startup training may take a few minutes. The
synthetic dataset and its evaluation results are for exercising the demo only;
they are not evidence of real-world fraud performance.

## Train with a labeled dataset

Use data you are legally permitted to process. The trainer expects a CSV at
`backend/data/transactions.csv` with these columns:

| Column | Meaning |
|---|---|
| `amount` | Transaction amount |
| `transaction_hour` | Hour of transaction |
| `transactions_last_24h` | Recent transaction count |
| `avg_amount_30d` | Average transaction amount over 30 days |
| `distance_from_last_km` | Distance from the previous transaction |
| `is_fraud` | Label: `0` genuine, `1` fraud |

If `occurred_at` is provided, data is split chronologically into training,
validation, and test partitions (60/20/20), keeping equal timestamps together.
Without it, stratified 64/16/20 partitions are used. Preprocessing and threshold
selection use training/validation data; the held-out test partition is kept for
evaluation.

1. Place the CSV at `backend/data/transactions.csv`.
2. Stop the services and set `DEMO_MODE=false` in `.env`.
3. Train the models:

   ```powershell
   docker compose run --rm backend python -m app.train --csv /app/data/transactions.csv
   ```

4. Start the services:

   ```powershell
   docker compose up --build
   ```

Model artifacts and metrics are written to `backend/models/` and are excluded
from Git. The dashboard compares accuracy, precision, recall, F1, PR-AUC,
threshold, and confusion-matrix counts for the trained models. Accuracy alone
can be misleading on imbalanced data. The 0–100 risk score is not a calibrated
probability of fraud.

The live API expects these engineered features; it does not ingest raw card
numbers, CVV values, merchant feeds, or benchmark datasets in their original
schema. Do not submit sensitive payment credentials.

## API

All API routes are under `/api`. Protected routes require the bearer token
returned by login.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/auth/register` | Register a user and create a simulated account |
| `POST` | `/api/auth/login` | Authenticate and return a token |
| `GET` | `/api/auth/me` | Get the authenticated user |
| `POST` | `/api/transactions` | Predict and store a transaction |
| `GET` | `/api/transactions` | Get the user's transaction history |
| `GET` | `/api/admin/analytics?period=daily` or `period=monthly` | Get administrator analytics |
| `GET` | `/api/admin/model-comparison` | Get model evaluation metrics |
| `GET` | `/api/admin/alerts` | List alerts |
| `PATCH` | `/api/admin/alerts/{id}` | Update an alert's review status |
| `GET` | `/api/bank/accounts` | Get demo accounts (administrators can see all) |
| `POST` | `/api/bank/transactions` | Score and process a simulated bank transaction |
| `GET` | `/api/bank/transactions` | Get authorized bank transaction history |
| `GET` | `/api/bank/notifications` | Get stored email/WhatsApp previews |
| `GET` | `/health` | Check API health |

Bank transaction requests require an account ID, positive amount, timezone-aware
ISO-8601 transaction time, distance from the previous transaction, model name,
and unique `Idempotency-Key`. The transaction, prediction, account update,
ledger entry (for posted payments), alerts, and notification previews are
handled in one database transaction. Fraud holds and insufficient-limit
declines do not debit the simulated account.

## Testing and build

Run backend tests in the backend container:

```powershell
docker compose run --rm backend python -m pytest -q
```

Build and type-check the frontend:

```powershell
Set-Location .\frontend
npm ci
npm run build
```

GitHub Actions runs backend tests, builds the frontend, and validates the
Docker Compose configuration.

## Model and system limitations

- Demo labels are synthetic and rule-generated. Their scores measure agreement
  with those generated labels, not real fraud-detection performance.
- A model score is not proof of intent or causation. Review flagged transactions
  in context and account for false positives and false negatives.
- Feature explanations describe model inputs that influenced the score; they
  do not establish why a transaction occurred.
- Behavioral features depend on the available user history. New users begin
  with limited history.
- Graph machine learning and automatic/adaptive retraining are not enabled.
  Any retraining should be an audited, evaluated, approved, versioned, and
  reversible offline process.
- The MGM Bank simulator and all notification drafts are local simulations.
  No real bank connection, funds transfer, email, or WhatsApp delivery exists.

## Production considerations

The self-signed certificate is for local development only. A production
deployment needs trusted TLS termination, strong unique secrets, least-privilege
database credentials, migrations, backups, access controls, data retention and
consent policies, monitoring, and an incident-response plan. Do not expose the
development Flask server or MySQL publicly.
