export type FormValues = {
  amount: string;
  occurred_at: string;
  distance_from_last_km: string;
};

export function localDateTimeValue(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}
