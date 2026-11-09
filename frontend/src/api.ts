export type User = { id: number; email: string; role: "user" | "admin" };
export type Explanation = { feature: string; value: number; impact: number };
export type Prediction = {
  model_name: string;
  model_version: string;
  fraud_probability: number;
  risk_score: number;
  classification: "fraud" | "genuine";
  threshold: number;
  explanation: Explanation[];
};
export type Transaction = {
  id: number;
  amount: number;
  occurred_at: string;
  prediction: Prediction | null;
};
export type BankAccount = {
  id: number;
  bank_name: string;
  bank_code: string;
  environment: "simulation";
  customer_id: string;
  customer_name: string;
  email: string;
  mobile: string;
  account_number: string;
  credit_limit: number;
  used_limit: number;
  available_limit: number;
  status: string;
  is_mine: boolean;
  owner_email?: string;
};
export type BankTransaction = {
  id: number;
  fraud_transaction_id: number;
  customer_id: string;
  customer_name: string;
  owner_email: string;
  amount: number;
  status: "posted" | "fraud_hold" | "declined_limit";
  classification: "fraud" | "genuine";
  risk_score: number;
  model_name: string;
  credit_limit: number;
  used_limit: number;
  available_limit: number;
  created_at: string;
};
export type NotificationPreview = {
  id: number;
  bank_transaction_id: number;
  channel: "email" | "whatsapp";
  recipient: string;
  status: "preview_only";
  subject: string;
  message: string;
  created_at: string;
};
export type Analytics = {
  period: "daily" | "monthly";
  period_days: number;
  total_transactions: number;
  fraud_transactions: number;
  genuine_transactions: number;
  fraud_percentage: number;
  daily: { date: string; transactions: number }[];
};
export type Evaluation = {
  model_name: string;
  model_version: string;
  metrics: {
    accuracy: number;
    precision: number;
    recall: number;
    f1: number;
    pr_auc: number;
    threshold: number;
    validation_rows?: number;
    confusion_matrix: {
      true_negative: number;
      false_positive: number;
      false_negative: number;
      true_positive: number;
    };
    test_rows: number;
    fraud_rate: number;
  };
};
export type Alert = {
  id: number;
  transaction_id: number;
  severity: string;
  status: string;
  risk_score: number;
  created_at: string;
};

const TOKEN_KEY = "sentinel-token";
export const getToken = () => sessionStorage.getItem(TOKEN_KEY);
export const setToken = (token: string | null) => {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
};

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`/api${path}`, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(body.error ?? `Request failed (${response.status})`);
  return body as T;
}
