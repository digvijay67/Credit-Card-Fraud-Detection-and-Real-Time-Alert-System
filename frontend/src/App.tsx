import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
} from "react";
import {
  Activity,
  AlertTriangle,
  Bell,
  CheckCircle2,
  CircleHelp,
  CreditCard,
  LayoutDashboard,
  Landmark,
  LogOut,
  LockKeyhole,
  Mail,
  MessageCircle,
  Shield,
  ShieldAlert,
  Target,
  TrendingUp,
  Wallet,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  getToken,
  setToken,
  type Alert,
  type Analytics,
  type BankAccount,
  type BankTransaction,
  type Evaluation,
  type NotificationPreview,
  type Transaction,
  type User,
} from "./api";
import { AuthPage, type AuthMode } from "./features/auth/AuthPage";
import { MetricCard } from "./features/dashboard/MetricCard";
import { PaymentPage } from "./features/payments/PaymentPage";
import {
  localDateTimeValue,
  type FormValues,
} from "./features/payments/types";
import { formatINR } from "./shared/formatters";

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [mobile, setMobile] = useState("");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const [bankTransactions, setBankTransactions] = useState<BankTransaction[]>([]);
  const [notificationPreviews, setNotificationPreviews] = useState<
    NotificationPreview[]
  >([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [latest, setLatest] = useState<Transaction | null>(null);
  const [model, setModel] = useState("xgboost");
  const [period, setPeriod] = useState<"daily" | "monthly">("daily");
  const [serviceStatus, setServiceStatus] = useState<
    "checking" | "online" | "offline"
  >("checking");
  const [activeHash, setActiveHash] = useState(
    () => window.location.hash || "#overview",
  );
  const isPaymentPage =
    activeHash === "#payment" || activeHash === "#new-transaction";
  const activeSection = ["#bank", "#history", "#alerts"].includes(activeHash)
    ? activeHash
    : "#overview";
  const sectionTitles: Record<string, string> = {
    "#overview": "Overview",
    "#bank": "Accounts and balances",
    "#history": "Transaction history",
    "#alerts": "Transactions to review",
  };
  const [form, setForm] = useState<FormValues>({
    amount: "145.50",
    occurred_at: localDateTimeValue(new Date()),
    distance_from_last_km: "8",
  });

  useEffect(() => {
    const updatePage = () => setActiveHash(window.location.hash || "#overview");
    window.addEventListener("hashchange", updatePage);
    return () => window.removeEventListener("hashchange", updatePage);
  }, []);

  const refresh = useCallback(
    async (activeUser: User) => {
      const [history, accounts, bankHistory, previews] = await Promise.all([
        api<Transaction[]>("/transactions"),
        api<BankAccount[]>("/bank/accounts"),
        api<BankTransaction[]>("/bank/transactions"),
        api<NotificationPreview[]>("/bank/notifications"),
      ]);
      setTransactions(history);
      setBankAccounts(accounts);
      setBankTransactions(bankHistory);
      setNotificationPreviews(previews);
      setSelectedAccountId((current) => {
        if (accounts.some((account) => String(account.id) === current))
          return current;
        const preferred = accounts.find((account) => account.is_mine) ?? accounts[0];
        return preferred ? String(preferred.id) : "";
      });
      if (activeUser.role === "admin") {
        const [stats, metrics, currentAlerts] = await Promise.all([
          api<Analytics>(`/admin/analytics?period=${period}`),
          api<Evaluation[]>("/admin/model-comparison"),
          api<Alert[]>("/admin/alerts"),
        ]);
        setAnalytics(stats);
        setEvaluations(metrics);
        setAlerts(currentAlerts);
      }
    },
    [period],
  );

  useEffect(() => {
    fetch("/health")
      .then((response) => {
        if (!response.ok) throw new Error("Health check failed");
        setServiceStatus("online");
      })
      .catch(() => setServiceStatus("offline"));
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api<{ user: User }>("/auth/me")
      .then(({ user: activeUser }) => {
        setUser(activeUser);
        refresh(activeUser).catch((reason: unknown) => {
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load dashboard",
          );
        });
      })
      .catch((reason: unknown) => {
        setToken(null);
        setError(
          reason instanceof Error ? reason.message : "Please sign in again",
        );
      });
  }, [refresh]);

  async function authenticate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (authMode === "register") {
        await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({
            email,
            password,
            customer_name: customerName,
            mobile,
          }),
        });
      }
      const result = await api<{ access_token: string; user: User }>(
        "/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ email, password }),
        },
      );
      setToken(result.access_token);
      setUser(result.user);
      await refresh(result.user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  async function submitTransaction(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setLatest(null);
    try {
      if (!selectedAccountId) throw new Error("No demo account is available");
      const idempotencyKey = crypto.randomUUID();
      const result = await api<{
        transaction: Transaction;
        bank_transaction: BankTransaction;
      }>("/bank/transactions", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({
          ...form,
          account_id: Number(selectedAccountId),
          idempotency_key: idempotencyKey,
          amount: Number(form.amount),
          occurred_at: new Date(form.occurred_at).toISOString(),
          distance_from_last_km: Number(form.distance_from_last_km),
          model,
        }),
      });
      setLatest(result.transaction);
      if (user) await refresh(user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Prediction failed");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setToken(null);
    setUser(null);
    setTransactions([]);
    setBankAccounts([]);
    setBankTransactions([]);
    setNotificationPreviews([]);
    setSelectedAccountId("");
    setAnalytics(null);
    setLatest(null);
  }

  async function resolveAlert(alert: Alert) {
    try {
      await api(`/admin/alerts/${alert.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status: "reviewed",
          resolution_note: "Reviewed in dashboard",
        }),
      });
      if (user) await refresh(user);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not update alert",
      );
    }
  }

  if (!user) {
    return (
      <AuthPage
        authMode={authMode}
        email={email}
        password={password}
        customerName={customerName}
        mobile={mobile}
        busy={busy}
        error={error}
        onEmailChange={setEmail}
        onPasswordChange={setPassword}
        onCustomerNameChange={setCustomerName}
        onMobileChange={setMobile}
        onModeChange={() => {
          setError("");
          setAuthMode(authMode === "login" ? "register" : "login");
        }}
        onSubmit={authenticate}
      />
    );
  }

  const fraudCount = transactions.filter(
    (t) => t.prediction?.classification === "fraud",
  ).length;
  const genuineCount = transactions.filter(
    (t) => t.prediction?.classification === "genuine",
  ).length;
  const flagRate =
    analytics?.fraud_percentage ??
    (transactions.length ? (fraudCount / transactions.length) * 100 : 0);
  const bankEventByTransaction = new Map(
    bankTransactions.map((event) => [event.fraud_transaction_id, event]),
  );
  const latestBankEvent = latest
    ? bankEventByTransaction.get(latest.id) ?? null
    : null;
  const selectedAccount =
    bankAccounts.find((account) => String(account.id) === selectedAccountId) ??
    bankAccounts.find((account) => account.is_mine);

  return (
    <div className="app-shell min-h-screen">
      <aside className="sidebar">
        <a className="brand" href="#">
          <span className="brand-mark">
            <CreditCard size={20} />
          </span>
          <span>Payments</span>
        </a>
        <p className="nav-caption">YOUR WORKSPACE</p>
        <a
          className={`nav-link ${!isPaymentPage && activeSection === "#overview" ? "active" : ""}`}
          href="#overview"
          aria-current={!isPaymentPage && activeSection === "#overview" ? "page" : undefined}
        >
          <LayoutDashboard size={17} /> Overview
        </a>
        <a
          className={`nav-link ${isPaymentPage ? "active" : ""}`}
          href="#payment"
          aria-current={isPaymentPage ? "page" : undefined}
        >
          <CreditCard size={17} /> New payment
        </a>
        <a
          className={`nav-link ${!isPaymentPage && activeSection === "#bank" ? "active" : ""}`}
          href="#bank"
          aria-current={!isPaymentPage && activeSection === "#bank" ? "page" : undefined}
        >
          <Landmark size={17} /> Accounts &amp; balances
        </a>
        <a
          className={`nav-link ${!isPaymentPage && activeSection === "#history" ? "active" : ""}`}
          href="#history"
          aria-current={!isPaymentPage && activeSection === "#history" ? "page" : undefined}
        >
          <Activity size={17} /> Transactions
        </a>
        {user.role === "admin" && (
          <a
            className={`nav-link ${!isPaymentPage && activeSection === "#alerts" ? "active" : ""}`}
            href="#alerts"
            aria-current={!isPaymentPage && activeSection === "#alerts" ? "page" : undefined}
          >
            <Bell size={17} /> Review queue{" "}
            <span className="nav-count">
              {alerts.filter((a) => a.status === "open").length}
            </span>
          </a>
        )}
        <div className="sidebar-bottom">
          <div className="secure-box">
            <Shield size={16} />
            <span>
              <b>Secure connection</b>
              <small>Session protected</small>
            </span>
          </div>
          <div className="profile">
            <div className="avatar">{user.email.slice(0, 1).toUpperCase()}</div>
            <span className="profile-name">
              {user.email}
              <small>
                {user.role === "admin" ? "Administrator" : "Account holder"}
              </small>
            </span>
            <button
              aria-label="Sign out"
              className="icon-button"
              onClick={logout}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-content" id="overview">
        <header className="topbar">
          <div>
            <p className="eyebrow">PAYMENTS WORKSPACE</p>
            <h1>{isPaymentPage ? "New payment" : sectionTitles[activeSection]}</h1>
          </div>
          <div className="top-actions">
            <span className={`live-pill ${serviceStatus}`}>
              <i />
              {serviceStatus === "checking"
                ? "Checking service"
                : serviceStatus === "online"
                  ? "Service available"
                  : "Service unavailable"}
            </span>
            <span className="date-label">
              {new Date().toLocaleDateString(undefined, {
                weekday: "short",
                month: "short",
                day: "numeric",
              })}
            </span>
          </div>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <AlertTriangle size={18} />
            {error}
            <button onClick={() => setError("")}>Dismiss</button>
          </div>
        )}
        {isPaymentPage ? (
          <PaymentPage
            accounts={bankAccounts}
            selectedAccountId={selectedAccountId}
            setSelectedAccountId={setSelectedAccountId}
            isAdmin={user.role === "admin"}
            form={form}
            setForm={setForm}
            model={model}
            setModel={setModel}
            busy={busy}
            onSubmit={submitTransaction}
            latest={latest}
            latestBankEvent={latestBankEvent}
          />
        ) : (
          <>
            <div className="notice">
              <CircleHelp size={17} />
              <span>
                Some payments may be held for review. A flag is a prompt to
                check the transaction details, not a finding of fraud. This
                workspace uses simulated payment data.
              </span>
            </div>

        <section className="metric-grid">
          <MetricCard
            icon={<CreditCard />}
            label="Transactions"
            value={
              user.role === "admin"
                ? (analytics?.total_transactions ?? "—")
                : transactions.length
            }
            caption={
              user.role === "admin"
                ? `Last ${analytics?.period_days ?? 30} days`
                : "Latest 200 transactions"
            }
            color="blue"
          />
          <MetricCard
            icon={<ShieldAlert />}
            label="Flagged transactions"
            value={
              user.role === "admin"
                ? (analytics?.fraud_transactions ?? "—")
                : fraudCount
            }
            caption="Requires a closer look"
            color="rose"
          />
          <MetricCard
            icon={<CheckCircle2 />}
            label="Not flagged"
            value={
              user.role === "admin"
                ? (analytics?.genuine_transactions ?? "—")
                : genuineCount
            }
            caption="No additional review indicated"
            color="green"
          />
          <MetricCard
            icon={<Target />}
            label="Flagged share"
            value={`${flagRate.toFixed(1)}%`}
            caption="Transactions set aside for review"
            color="amber"
          />
        </section>

        <section className="panel bank-panel" id="bank">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">DEMO ACCOUNT</p>
              <h2>Demo accounts</h2>
            </div>
            <span className="subtle-chip">
              <Landmark size={14} /> Local simulation only
            </span>
          </div>
          {selectedAccount ? (
            <>
              <div className="bank-account-summary">
                <div>
                  <span className="bank-detail-label">Customer</span>
                  <b>{selectedAccount.customer_name}</b>
                  <small>
                    {selectedAccount.customer_id} · {selectedAccount.account_number}
                  </small>
                </div>
                {user.role === "admin" && bankAccounts.length > 1 && (
                  <label className="bank-account-select">
                    Demo account
                    <select
                      value={selectedAccountId}
                      onChange={(event) => setSelectedAccountId(event.target.value)}
                    >
                      {bankAccounts.map((account) => (
                        <option key={account.id} value={account.id}>
                          {account.customer_name} · {account.customer_id}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <div className="bank-balances">
                  <div>
                    <span className="bank-detail-label">Credit limit</span>
                    <b>{formatINR(selectedAccount.credit_limit)}</b>
                  </div>
                  <div>
                    <span className="bank-detail-label">Used</span>
                    <b>{formatINR(selectedAccount.used_limit)}</b>
                  </div>
                  <div>
                    <span className="bank-detail-label">Available</span>
                    <b>{formatINR(selectedAccount.available_limit)}</b>
                  </div>
                </div>
              </div>
              {user.role === "admin" && bankAccounts.length > 0 && (
                <div className="table-wrap bank-accounts-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Customer</th>
                        <th>App user</th>
                        <th>Customer ID</th>
                        <th>Credit limit</th>
                        <th>Used</th>
                        <th>Available</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bankAccounts.map((account) => (
                        <tr key={account.id}>
                          <td>{account.customer_name}</td>
                          <td>{account.owner_email}</td>
                          <td>{account.customer_id}</td>
                          <td>{formatINR(account.credit_limit)}</td>
                          <td>{formatINR(account.used_limit)}</td>
                          <td>{formatINR(account.available_limit)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="notification-previews">
                <div className="explanation-title">
                  <Bell size={15} /> Message drafts
                  <span>Stored only — nothing is sent</span>
                </div>
                {notificationPreviews.length ? (
                  notificationPreviews.slice(0, 4).map((preview) => (
                    <div className="notification-preview" key={preview.id}>
                      {preview.channel === "email" ? (
                        <Mail size={15} />
                      ) : (
                        <MessageCircle size={15} />
                      )}
                      <div>
                        <b>{preview.channel === "email" ? "Email" : "WhatsApp"} draft</b>
                        <small>
                          {preview.subject} · {preview.status.replace("_", " ")}
                        </small>
                        <small className="preview-message">{preview.message}</small>
                      </div>
                      <span>{preview.recipient}</span>
                    </div>
                  ))
                ) : (
                  <div className="empty-inline">
                    <Wallet size={17} /> Transaction message drafts will appear here.
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="empty-inline">
              <Wallet size={18} /> No demo bank account is available for this user.
            </div>
          )}
        </section>

        <div className="content-grid">
          <section className="panel payment-cta">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">PAYMENTS</p>
                <h2>Make a payment</h2>
              </div>
            </div>
            <p className="muted">
              Submit a payment for an immediate risk check. Payments that need
              attention are held; approved payments update the simulated balance.
            </p>
            {selectedAccount && (
              <div className="payment-context">
                <span>{selectedAccount.customer_name}</span>
                <b>{formatINR(selectedAccount.available_limit)} available</b>
              </div>
            )}
            <a className="primary payment-link" href="#payment">
              <CreditCard size={16} /> Start a payment
            </a>
          </section>

          <section className="panel chart-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">
                  {user.role === "admin"
                    ? `LAST ${analytics?.period_days ?? 30} DAYS`
                    : "YOUR ACTIVITY"}
                </p>
                <h2>Transaction overview</h2>
              </div>
              {user.role === "admin" ? (
                <label className="subtle-chip">
                  View
                  <select
                    value={period}
                    onChange={(event) =>
                      setPeriod(
                        event.target.value === "monthly" ? "monthly" : "daily",
                      )
                    }
                  >
                    <option value="daily">Daily</option>
                    <option value="monthly">Monthly</option>
                  </select>
                </label>
              ) : (
                <span className="subtle-chip">
                  <TrendingUp size={14} /> Rolling trend
                </span>
              )}
            </div>
            {user.role === "admin" && analytics ? (
              <div className="chart-area">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={analytics.daily}>
                    <defs>
                      <linearGradient
                        id="transactions"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stopColor="#5b70ec"
                          stopOpacity={0.22}
                        />
                        <stop
                          offset="95%"
                          stopColor="#5b70ec"
                          stopOpacity={0}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#edf0f5" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(value) =>
                        period === "monthly" ? value : value.slice(5)
                      }
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      allowDecimals={false}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip />
                    <Area
                      type="monotone"
                      dataKey="transactions"
                      stroke="#5b70ec"
                      strokeWidth={2.5}
                      fill="url(#transactions)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="empty-chart">
                <div className="empty-icon">
                  <Activity />
                </div>
                <b>
                  {transactions.length
                    ? `${transactions.length} transactions recorded`
                    : "Your transaction activity will appear here"}
                </b>
                <span>
                  Submit a payment to start building your transaction history.
                </span>
              </div>
            )}
            {user.role === "admin" && (
              <div className="chart-legend">
                <span>
                  <i className="legend-dot blue-dot" /> Transactions per{" "}
                  {period === "daily" ? "day" : "month"}
                </span>
                <span>{period === "daily" ? "30 day" : "12 month"} period</span>
              </div>
            )}
          </section>
        </div>

        {user.role === "admin" && (
          <section className="panel comparison-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">ADMINISTRATION</p>
                <h2>Model evaluation</h2>
              </div>
              <span className="subtle-chip">Evaluation results</span>
            </div>
            {evaluations.length ? (
              <div className="comparison-layout">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Model</th>
                        <th>Accuracy</th>
                        <th>Precision</th>
                        <th>Recall</th>
                        <th>F1 score</th>
                        <th>PR-AUC</th>
                        <th>Threshold</th>
                        <th>TN / FP / FN / TP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evaluations.map((row) => (
                        <tr key={row.model_name}>
                          <td className="model-name">
                            {row.model_name === "xgboost"
                              ? "XGBoost"
                              : row.model_name === "logistic_regression"
                                ? "Logistic Regression"
                                : "Random Forest"}
                            <small>
                              v{row.model_version} ·{" "}
                              {row.metrics.validation_rows
                                ? `${row.metrics.validation_rows.toLocaleString()} validation / `
                                : ""}
                              {row.metrics.test_rows.toLocaleString()} test rows
                            </small>
                          </td>
                          <td>{(row.metrics.accuracy * 100).toFixed(1)}%</td>
                          <td>{(row.metrics.precision * 100).toFixed(1)}%</td>
                          <td>{(row.metrics.recall * 100).toFixed(1)}%</td>
                          <td>
                            <b>{(row.metrics.f1 * 100).toFixed(1)}%</b>
                          </td>
                          <td>{(row.metrics.pr_auc * 100).toFixed(1)}%</td>
                          <td>{row.metrics.threshold.toFixed(2)}</td>
                          <td>
                            {row.metrics.confusion_matrix.true_negative} /{" "}
                            {row.metrics.confusion_matrix.false_positive} /{" "}
                            {row.metrics.confusion_matrix.false_negative} /{" "}
                            {row.metrics.confusion_matrix.true_positive}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="metric-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={evaluations.map((item) => ({
                          name: item.model_name,
                          value: item.metrics.f1,
                        }))}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={55}
                        outerRadius={82}
                        paddingAngle={5}
                      >
                        <Cell fill="#6273ec" />
                        <Cell fill="#20a888" />
                        <Cell fill="#e69a36" />
                      </Pie>
                      <Tooltip
                        formatter={(value: number) =>
                          `${(value * 100).toFixed(1)}% F1`
                        }
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <span>F1 score</span>
                </div>
              </div>
            ) : (
              <div className="empty-inline">
                <CircleHelp size={18} /> No trained model evaluation is
                available yet. Train the models with a labeled CSV dataset.
              </div>
            )}
          </section>
        )}

        {user.role === "admin" && (
          <section className="panel alerts-panel" id="alerts">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">REVIEW QUEUE</p>
                <h2>Transactions to review</h2>
              </div>
              <span className="subtle-chip">
                <Bell size={14} />{" "}
                {alerts.filter((alert) => alert.status === "open").length} open
              </span>
            </div>
            {alerts.length ? (
              <div className="alert-list">
                {alerts.slice(0, 8).map((alert) => (
                  <div className="alert-row" key={alert.id}>
                    <span className="alert-symbol">
                      <AlertTriangle size={17} />
                    </span>
                    <span className="alert-main">
                      <b>Transaction #{alert.transaction_id}</b>
                      <small>
                        {new Date(alert.created_at).toLocaleString()} ·{" "}
                        {alert.severity} priority
                      </small>
                    </span>
                    <span className="risk-tag">Score {alert.risk_score}/100</span>
                    <span className={`status-tag ${alert.status}`}>
                      {alert.status.replace("_", " ")}
                    </span>
                    {alert.status === "open" && (
                      <button
                        className="secondary small-button"
                        onClick={() => resolveAlert(alert)}
                      >
                        Mark reviewed
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-inline">
                <CheckCircle2 size={18} /> No transactions are waiting in the
                review queue.
              </div>
            )}
          </section>
        )}

        <section className="panel history-panel" id="history">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">ACTIVITY</p>
              <h2>Recent transactions</h2>
            </div>
            <span className="subtle-chip">
              {transactions.length} shown · up to 200
            </span>
          </div>
          {transactions.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Transaction</th>
                    <th>Date and time</th>
                    <th>Amount</th>
                    <th>Classification</th>
                    <th>Risk score</th>
                    <th>Bank processing</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((transaction) => (
                    <tr key={transaction.id}>
                      <td className="transaction-id">#{transaction.id}</td>
                      <td>
                        {new Date(transaction.occurred_at).toLocaleString()}
                      </td>
                      <td>{formatINR(transaction.amount)}</td>
                      <td>
                        <span
                          className={`classification ${transaction.prediction?.classification}`}
                        >
                          {transaction.prediction
                            ? transaction.prediction.classification === "fraud"
                              ? "Review needed"
                              : "Not flagged"
                            : "Pending"}
                        </span>
                      </td>
                      <td>
                        <span className="score-cell">
                          {transaction.prediction?.risk_score ?? "—"}
                          {transaction.prediction && <small>/ 100</small>}
                        </span>
                      </td>
                      <td>
                        {bankEventByTransaction.has(transaction.id) ? (
                          <span
                            className={`classification ${bankEventByTransaction.get(transaction.id)?.status}`}
                          >
                            {bankEventByTransaction
                              .get(transaction.id)
                              ?.status.replace(/_/g, " ")}
                          </span>
                        ) : (
                          <span className="muted">Risk check only</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-inline">
              <CreditCard size={18} /> No transactions yet. Submit a payment to
              see it here.
            </div>
          )}
        </section>
          </>
        )}
        <footer className="footer">
          <span>Payments workspace · Demo environment</span>
          <span>
            <LockKeyhole size={13} /> Encrypted connection · Flags support review
          </span>
        </footer>
      </main>
    </div>
  );
}

export default App;
