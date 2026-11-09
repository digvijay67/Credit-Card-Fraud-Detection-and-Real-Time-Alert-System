const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
});

export function formatINR(amount: number) {
  return inrFormatter.format(amount);
}
