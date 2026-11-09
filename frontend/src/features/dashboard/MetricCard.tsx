import type { ReactNode } from "react";

type MetricCardProps = {
  icon: ReactNode;
  label: string;
  value: string | number;
  caption: string;
  color: string;
};

export function MetricCard({
  icon,
  label,
  value,
  caption,
  color,
}: MetricCardProps) {
  return (
    <article className="metric-card">
      <span className={`metric-icon ${color}`}>{icon}</span>
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
      <div className="metric-caption">{caption}</div>
    </article>
  );
}
