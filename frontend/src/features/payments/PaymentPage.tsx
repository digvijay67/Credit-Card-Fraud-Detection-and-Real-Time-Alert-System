import type { Dispatch, FormEvent, SetStateAction } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  CircleHelp,
  LockKeyhole,
  Plus,
  Shield,
  Wallet,
} from "lucide-react";
import type {
  BankAccount,
  BankTransaction,
  Transaction,
} from "../../api";
import { formatINR } from "../../shared/formatters";
import { featureLabels } from "../dashboard/featureLabels";
import type { FormValues } from "./types";

type PaymentPageProps = {
  accounts: BankAccount[];
  selectedAccountId: string;
  setSelectedAccountId: Dispatch<SetStateAction<string>>;
  isAdmin: boolean;
  form: FormValues;
  setForm: Dispatch<SetStateAction<FormValues>>;
  model: string;
  setModel: Dispatch<SetStateAction<string>>;
  busy: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  latest: Transaction | null;
  latestBankEvent: BankTransaction | null;
};

function displayModelName(name: string) {
  if (name === "random_forest") return "Random Forest";
  if (name === "logistic_regression") return "Logistic Regression";
  return "XGBoost";
}

export function PaymentPage({
  accounts,
  selectedAccountId,
  setSelectedAccountId,
  isAdmin,
  form,
  setForm,
  model,
  setModel,
  busy,
  onSubmit,
  latest,
  latestBankEvent,
}: PaymentPageProps) {
  const prediction = latest?.prediction;
  const score = prediction?.risk_score ?? 0;

  return (
    <>
      <div className="notice">
        <CircleHelp size={17} />
        <span>
          Demo environment: no real bank is connected, and no funds or messages
          are sent. A review flag is not a finding of fraud.
        </span>
      </div>
      <section className="panel payment-page">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">PAYMENT DETAILS</p>
            <h2>Enter payment information</h2>
          </div>
          <span className="model-badge">Demo account</span>
        </div>
        {!accounts.length ? (
          <div className="empty-inline">
            <Wallet size={18} /> No demo bank account is available for this user.
          </div>
        ) : (
          <form onSubmit={onSubmit}>
            <div className="form-grid">
              <label>
                Demo account
                <select
                  value={selectedAccountId}
                  onChange={(event) => setSelectedAccountId(event.target.value)}
                  required
                >
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.customer_name} · available{" "}
                      {formatINR(account.available_limit)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Payment amount (INR)
                <input
                  type="number"
                  min="0.01"
                  max="999999999.99"
                  step="0.01"
                  required
                  value={form.amount}
                  onChange={(event) =>
                    setForm({ ...form, amount: event.target.value })
                  }
                />
              </label>
              <label>
                Date and time
                <input
                  type="datetime-local"
                  required
                  value={form.occurred_at}
                  onChange={(event) =>
                    setForm({ ...form, occurred_at: event.target.value })
                  }
                />
              </label>
              <label>
                Distance from previous transaction (km)
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  required
                  value={form.distance_from_last_km}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      distance_from_last_km: event.target.value,
                    })
                  }
                />
              </label>
              {isAdmin && (
                <label>
                  Model used for this test
                  <select
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                  >
                    <option value="xgboost">XGBoost</option>
                    <option value="random_forest">Random Forest</option>
                    <option value="logistic_regression">
                      Logistic Regression
                    </option>
                  </select>
                </label>
              )}
            </div>
            <div className="form-footer">
              <span>
                <LockKeyhole size={15} />
                This demo does not use real card details or funds.
              </span>
              <button className="primary" disabled={busy}>
                <Plus size={17} />
                {busy ? "Checking payment…" : "Review and submit payment"}
              </button>
            </div>
          </form>
        )}
        {prediction && latest && (
          <div
            className={`result-card ${prediction.classification} ${latestBankEvent?.status ?? ""}`}
            aria-live="polite"
          >
            <div className="result-top">
              <div
                className={`result-icon ${prediction.classification === "fraud" ? "danger" : latestBankEvent?.status === "declined_limit" ? "warning" : "success"}`}
              >
                {prediction.classification === "fraud" ||
                latestBankEvent?.status === "declined_limit" ? (
                  <AlertTriangle />
                ) : (
                  <CheckCircle2 />
                )}
              </div>
              <div>
                <p className="eyebrow">
                  Transaction #{latest.id} ·{" "}
                  {displayModelName(prediction.model_name)}
                </p>
                <h3>
                  {latestBankEvent?.status === "declined_limit"
                    ? "Payment declined — limit exceeded"
                    : latestBankEvent?.status === "fraud_hold"
                      ? "Payment held for review"
                      : latestBankEvent?.status === "posted"
                        ? "Payment approved"
                        : prediction.classification === "fraud"
                          ? "Payment flagged for review"
                          : "No additional review indicated"}
                </h3>
                {latestBankEvent && (
                  <small className="payment-outcome">
                    Account update: {latestBankEvent.status.replace(/_/g, " ")}
                  </small>
                )}
              </div>
              <div className="score-pill">
                <b>{score}</b>
                <small>risk score / 100</small>
              </div>
            </div>
            <div className="risk-track">
              <span style={{ width: `${score}%` }} />
            </div>
            <div className="explanation-title">
              <CircleHelp size={15} /> Factors affecting this review score
            </div>
            <div className="explanation-list">
              {prediction.explanation.map((item) => (
                <div className="explanation-row" key={item.feature}>
                  <span>{featureLabels[item.feature] ?? item.feature}</span>
                  <b className={item.impact >= 0 ? "impact-up" : "impact-down"}>
                    {item.impact >= 0 ? (
                      <ArrowUpRight size={14} />
                    ) : (
                      <ArrowDownRight size={14} />
                    )}
                    {item.impact >= 0
                      ? "Raised review score"
                      : "Lowered review score"}
                  </b>
                </div>
              ))}
            </div>
            <p className="explanation-disclaimer">
              The score is a review aid, not proof of fraud. A payment may be
              flagged incorrectly; check the transaction context before taking
              action.
            </p>
          </div>
        )}
        <div className="payment-footer">
          <a href="#overview">Back to overview</a>
          <span>
            <Shield size={13} /> Payments are processed in this local demo only.
          </span>
        </div>
      </section>
    </>
  );
}
