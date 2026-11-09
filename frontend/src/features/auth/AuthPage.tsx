import type { FormEvent } from "react";
import { CreditCard, Shield } from "lucide-react";

export type AuthMode = "login" | "register";

type AuthPageProps = {
  authMode: AuthMode;
  email: string;
  password: string;
  customerName: string;
  mobile: string;
  busy: boolean;
  error: string;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onCustomerNameChange: (value: string) => void;
  onMobileChange: (value: string) => void;
  onModeChange: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function AuthPage({
  authMode,
  email,
  password,
  customerName,
  mobile,
  busy,
  error,
  onEmailChange,
  onPasswordChange,
  onCustomerNameChange,
  onMobileChange,
  onModeChange,
  onSubmit,
}: AuthPageProps) {
  const isRegistering = authMode === "register";

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="brand-mark">
          <CreditCard size={22} />
        </div>
        <p className="eyebrow">PAYMENTS WORKSPACE</p>
        <h1>
          {isRegistering
            ? "Open a demo credit account"
            : "Sign in to your account"}
        </h1>
        <p className="muted">
          {isRegistering
            ? "Create a sign-in and a simulated MGM Bank account with a ₹5,000 credit limit."
            : "Review payments, account activity, and transactions that need attention."}
        </p>
        <form onSubmit={onSubmit} className="stack-form">
          {isRegistering && (
            <>
              <label>
                Customer name
                <input
                  type="text"
                  required
                  minLength={2}
                  maxLength={120}
                  autoComplete="name"
                  value={customerName}
                  onChange={(event) => onCustomerNameChange(event.target.value)}
                />
              </label>
              <label>
                Mobile number
                <input
                  type="tel"
                  required
                  autoComplete="tel"
                  value={mobile}
                  onChange={(event) => onMobileChange(event.target.value)}
                />
              </label>
            </>
          )}
          <label>
            Email address
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => onEmailChange(event.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              required
              minLength={isRegistering ? 12 : 1}
              autoComplete={isRegistering ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button className="primary full" disabled={busy}>
            {busy
              ? "Please wait…"
              : isRegistering
                ? "Open demo account"
                : "Sign in"}
          </button>
        </form>
        <button className="text-button" onClick={onModeChange}>
          {isRegistering
            ? "Already registered? Sign in"
            : "New here? Open a demo account"}
        </button>
        <p className="auth-note">
          <Shield size={14} />{" "}
          {isRegistering
            ? "Simulation only — no real card or funds are issued"
            : "Protected by encrypted HTTPS connection"}
        </p>
      </section>
    </main>
  );
}
