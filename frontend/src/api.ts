export type Level = "low" | "medium" | "high" | "churned" | "no_data";

export interface CustomerRow {
  id: number;
  email: string;
  balanceCents: number;
  totalReplenishedCents: number;
  score: number | null;
  level: Level;
  loyalty: number | null;
  topReason: string | null;
  expectedLossCents: number;
}

export interface CustomerPage {
  items: CustomerRow[];
  total: number;
  page: number;
  size: number;
}

export interface Summary {
  counts: Record<Level, number>;
  revenueAtRiskCents: number;
  expectedLossCents: number;
  recoverableCents: number;
  lostRevenueMonthlyCents: number;
  hourlyShare: number;
  averageScore: number | null;
  modelVersion: number;
  asOf: string;
  calculatedAt: string | null;
}

export interface TimelinePoint {
  date: string;
  value: number;
}

export interface TimelineSeries {
  type: "observed" | "estimated" | "forecast";
  points: TimelinePoint[];
}

export interface Timeline {
  asOf: string;
  asOfDate: string;
  series: TimelineSeries[];
}

export interface FeatureDescription {
  key: string;
  title: string;
  description: string;
  scope: "service" | "account";
  default_weight: number;
}

export interface ModelSettings {
  weights: Record<string, number>;
  horizon_days: number;
  horizon_money_days: number;
  thresholds: { low: number; high: number };
  alpha_max_mean: number;
  churn_curve: { k: number; midpoint: number };
  balance_shield: number;
  suspended_value: number;
  as_of_mode: "snapshot" | "now" | "fixed";
  as_of_fixed: string | null;
}

export interface ModelSettingsResponse {
  settings: ModelSettings;
  version: number;
  features: FeatureDescription[];
  ranges: Record<string, number[]>;
}

export interface CustomerDetail extends CustomerRow {
  withdrawBalanceCents: number;
  bonusBalanceCents: number;
  bonusState: string;
  reasons: Array<{ explanation: string; scoreContribution: number }>;
  dataWarnings: Array<{ code: string; message: string; serviceId: number }>;
  services: Array<{
    id: number;
    name: string;
    paymentTerm: string;
    autoProlong: boolean;
    createdAt: string;
    expiresAt: string;
    status: string;
    priceCents: number;
    score: number | null;
    featureContributions: Array<{
      key: string;
      title: string;
      value: number;
      weight: number;
      scoreContribution: number;
      explanation: string;
    }>;
    valueCents: number;
    expectedLossCents: number;
  }>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (response.status === 401) window.dispatchEvent(new Event("auth-expired"));
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(response.status, payload?.detail ?? response.statusText);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const formatEur = (cents: number) =>
  new Intl.NumberFormat("ru-RU", { style: "currency", currency: "EUR" }).format(cents / 100);

export const formatDate = (value: string) =>
  new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(value),
  );

export const levelLabels: Record<Level, string> = {
  low: "\u041d\u0438\u0437\u043a\u0438\u0439",
  medium: "\u0421\u0440\u0435\u0434\u043d\u0438\u0439",
  high: "\u0412\u044b\u0441\u043e\u043a\u0438\u0439",
  churned: "\u0423\u0448\u0451\u043b",
  no_data: "\u041d\u0435\u0442 \u043e\u0446\u0435\u043d\u043a\u0438",
};