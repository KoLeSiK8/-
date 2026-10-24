import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  CloudUpload,
  Database,
  FileJson2,
  Gauge,
  LogOut,
  Moon,
  Search,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sun,
  Users,
  X,
} from "lucide-react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  ApiError,
  api,
  CustomerDetail,
  CustomerPage,
  FeatureDescription,
  formatCount,
  formatDate,
  formatEur,
  Level,
  levelLabels,
  ModelSettings,
  ModelSettingsResponse,
  statusLabels,
  Summary,
  termLabels,
  Timeline,
  toLocalInput,
} from "./api";

const t = {
  overview: "Обзор",
  customers: "Клиенты",
  model: "Модель",
  data: "Данные",
  loginTitle: "Войти в систему",
  loginHint: "Введите данные администратора",
  continue: "Продолжить",
  busy: "Входим…",
  loginError: "Неверный логин или пароль",
  loginFailed: "Не удалось войти. Проверьте соединение.",
  riskSystem: "СИСТЕМА АНАЛИТИКИ",
  riskVisible: "Риск становится",
  visible: "видимым.",
  retention: "Анализ удержания и потенциальных потерь по каждому клиенту.",
  workspace: "РАБОЧЕЕ ПРОСТРАНСТВО",
  protected: "Защищённая сессия",
  analytics: "Аналитика",
  modelActive: "Модель активна",
  admin: "Администратор",
  logout: "Выйти",
  live: "Нет связи",
  snapshot: "Срез данных",
  metrics: "Сводка",
  summary: "Сводка на 30 дней",
  loading: "Загрузка…",
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
  churned: "Ушёл",
  noData: "Нет оценки",
  atRisk: "Выручка под риском",
  expectedLoss: "Ожидаемые потери",
  recoverable: "Можно предотвратить",
  lostMonthly: "Потерянная выручка / мес.",
  liveServices: "Живые услуги со средним и высоким риском",
  formula: "Формула",
  dynamics: "Динамика",
  churnEvents: "События оттока",
  observed: "Факт",
  estimated: "Оценка даты",
  forecast: "Прогноз",
  modelScore: "Текущая оценка",
  averageRisk: "Средний риск",
  byScored: "по клиентам с оценкой",
  hourly: "Почасовые услуги в риске",
  scoredCustomers: "Клиенты с оценкой",
  updated: "Обновлено",
  openCustomers: "Открыть клиентов",
  findCustomer: "ID или email",
  allCustomers: "Все клиенты",
  filterLevel: "Уровень",
  reset: "Сбросить",
  noResults: "Клиенты не найдены",
  reasons: "Причины риска",
  services: "Услуги",
  balance: "Баланс",
  loyalty: "Лояльность",
  warnings: "Предупреждения",
  loadingList: "Загрузка списка…",
  shown: "Показано",
  of: "из",
  previous: "Предыдущая страница",
  next: "Следующая страница",
  weights: "Веса сигналов",
  features: "Признаки",
  settings: "Настройки модели",
  saved: "Сохранено",
  saving: "Сохранение…",
  saveError: "Ошибка сохранения",
  resetDefaults: "Сбросить к умолчанию",
  thresholds: "Пороги риска",
  lowMedium: "Низкий / средний",
  mediumHigh: "Средний / высокий",
  horizon: "Горизонты",
  riskHorizon: "Оценка риска",
  moneyHorizon: "Денежная оценка",
  alpha: "Вес максимума α",
  curve: "Кривая оттока",
  midpoint: "Середина s₀",
  shield: "Защита балансом",
  asOf: "Точка отсчёта",
  mode: "Режим оценки",
  snapshotMode: "Время снимка",
  nowMode: "Сейчас",
  fixedMode: "Фиксированная дата",
  points: "баллов",
  days: "дней",
  weight: "вес",
  service: "УСЛУГА",
  account: "АККАУНТ",
  source: "Источник / snapshot",
  replaceSource: "Замена источника",
  upload: "Загрузить снимок",
  chooseFile: "Выберите JSON-файл",
  dropFile: "или перетащите его сюда",
  presets: "Или загрузить набор",
  demo: "Демо-данные",
  official: "Официальный набор",
  validating: "Проверка и пересчёт…",
  noFile: "Файл не является корректным JSON.",
  close: "Закрыть",
  notAvailable: "Нет данных",
  reason: "Причина",
  amount: "Баланс",
  dataError: "Не удалось загрузить данные",
  dataLoaded: "Загружено",
  formulaNote: "Сумма стоимости услуг клиентов уровней medium и high.",
  noEvents: "Нет событий для графика",
  detail: "Карточка клиента",
  uploadSuccess: "Снимок загружен",
  formulaText: "Все суммы в евро",
  services_unit: "услуг",
};

/** Plain-language formulas shown next to every dashboard number (PLAN.md, 4.5). */
const formulas = {
  atRisk:
    "Сумма стоимости живых услуг у клиентов со средним и высоким риском за денежный горизонт (по умолчанию 30 дней): цена × горизонт / длина периода оплаты.",
  expectedLoss:
    "Для каждой услуги: стоимость × P(отток | score) × (1 − защита_балансом × покрытие). P — логистическая кривая от score, покрытие — доля стоимости живых услуг, которую закрывают доступные средства.",
  recoverable:
    "Сколько клиентам не хватает, чтобы продлить услуги, истекающие в горизонте оценки риска: сумма max(0, стоимость истекающих услуг − доступные средства) по клиентам.",
  lostMonthly:
    "Месячная стоимость удалённых и заблокированных услуг у ушедших клиентов: цена × 30 / длина периода оплаты.",
  chart:
    "Все линии считаются в услугах. Факт — услуги, перешедшие в deleted/blocked между загрузками снимков. Оценка даты — удалённые услуги, датированные окончанием + 5 суток. Прогноз — ожидаемое число потерянных услуг по дням окончания в ближайшие 30 дней (сумма вероятностей оттока). Вертикальная линия — момент оценки as_of.",
};

const levels: Level[] = ["high", "medium", "low", "churned", "no_data"];
const loginLabel = "Логин";
const passwordLabel = "Пароль";
const dataDescription = "Снапшот будет проверен и пересчитан до применения.";
const atomicDataHint = "Загрузка и пересчёт выполняются одной транзакцией.";
const sortOptions = [
  ["id", "ID"],
  ["email", "Email"],
  ["balance", t.balance],
  ["total_replenished", "Пополнения"],
  ["score", "Score"],
  ["expected_loss", t.expectedLoss],
] as const;
type Theme = "light" | "dark";

function useSummary() {
  return useQuery({
    queryKey: ["summary"],
    queryFn: () => api<Summary>("/api/v1/analytics/summary"),
  });
}

function readTheme(): Theme {
  return window.localStorage.getItem("churn-theme") === "dark" ? "dark" : "light";
}

function useLiveUpdates(enabled: boolean) {
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    const source = new EventSource("/api/v1/events", { withCredentials: true });
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("recomputed", () => client.invalidateQueries());
    return () => source.close();
  }, [enabled, client]);
  return connected;
}

export default function AppFixed() {
  const client = useQueryClient();
  const [expired, setExpired] = useState(false);
  const [theme, setTheme] = useState<Theme>(() => readTheme());
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<{ login: string }>("/api/v1/auth/me"),
    retry: false,
  });
  const live = useLiveUpdates(Boolean(me.data) && !expired);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("churn-theme", theme);
  }, [theme]);
  useEffect(() => {
    const expire = () => setExpired(true);
    window.addEventListener("auth-expired", expire);
    return () => window.removeEventListener("auth-expired", expire);
  }, []);
  async function onLogin() {
    setExpired(false);
    await me.refetch();
  }
  async function logout() {
    try {
      await api<void>("/api/v1/auth/logout", { method: "POST" });
    } finally {
      setExpired(true);
      client.clear();
    }
  }
  if (me.isLoading)
    return (
      <div className="boot-screen">
        <span className="brand-mark">CR</span>
      </div>
    );
  if (!me.data || expired)
    return (
      <Login
        onLogin={onLogin}
        theme={theme}
        toggleTheme={() => setTheme(theme === "light" ? "dark" : "light")}
      />
    );
  return (
    <div className="app-frame">
      <Sidebar login={me.data.login} logout={logout} />
      <main className="main-column">
        <Topbar
          live={live}
          login={me.data.login}
          theme={theme}
          toggleTheme={() => setTheme(theme === "light" ? "dark" : "light")}
        />
        <div className="page-wrap">
          <Routes>
            <Route path="/" element={<Dashboard theme={theme} />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/model" element={<Model />} />
            <Route path="/data" element={<Data />} />
            <Route path="*" element={<Dashboard theme={theme} />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}

function ThemeToggle({ theme, toggleTheme }: { theme: Theme; toggleTheme: () => void }) {
  const dark = theme === "dark";
  return (
    <button
      className="icon-button theme-toggle"
      type="button"
      onClick={toggleTheme}
      title={dark ? "Светлая тема" : "Тёмная тема"}
      aria-label={dark ? "Включить светлую тему" : "Включить тёмную тему"}
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

function Login({
  onLogin,
  theme,
  toggleTheme,
}: {
  onLogin: () => Promise<void>;
  theme: Theme;
  toggleTheme: () => void;
}) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ login, password }) });
      await onLogin();
    } catch (reason) {
      setError(reason instanceof ApiError && reason.status === 401 ? t.loginError : t.loginFailed);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-screen">
      <section className="login-brand-panel">
        <div className="brand-lockup">
          <span className="brand-mark">CR</span>
          <span>CHURN / INSIGHT</span>
        </div>
        <div className="login-brand-copy">
          <p className="eyebrow">{t.riskSystem}</p>
          <h1>
            {t.riskVisible}
            <br />
            <em>{t.visible}</em>
          </h1>
          <div className="brand-rule" />
          <p>{t.retention}</p>
        </div>
        <div className="login-ornament" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
        <span className="brand-foot">CHURN RISK ANALYZER · 01</span>
      </section>
      <section className="login-form-panel">
        <div className="login-form-wrap">
          <div className="login-theme-row">
            <p className="eyebrow">{t.workspace}</p>
            <ThemeToggle theme={theme} toggleTheme={toggleTheme} />
          </div>
          <h2>{t.loginTitle}</h2>
          <p className="muted">{t.loginHint}</p>
          <form onSubmit={submit} className="login-form">
            <label>
              {loginLabel}
              <input
                autoComplete="username"
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                required
              />
            </label>
            <label>
              {passwordLabel}
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            {error && <p className="form-error">{error}</p>}
            <button className="button button-primary login-submit" disabled={busy}>
              {busy ? t.busy : t.continue}
              <ChevronRight size={17} />
            </button>
          </form>
          <p className="login-safe">
            <ShieldCheck size={15} />
            {t.protected}
          </p>
        </div>
      </section>
    </main>
  );
}

function Sidebar({ login, logout }: { login: string; logout: () => void }) {
  const summary = useSummary();
  const items = [
    { to: "/", label: t.overview, icon: Gauge, end: true },
    { to: "/customers", label: t.customers, icon: Users },
    { to: "/model", label: t.model, icon: Settings2 },
    { to: "/data", label: t.data, icon: Database },
  ];
  return (
    <aside className="sidebar">
      <NavLink to="/" className="brand-lockup sidebar-brand">
        <span className="brand-mark">CR</span>
        <span>
          CHURN
          <br />
          INSIGHT
        </span>
      </NavLink>
      <div className="nav-caption">{t.analytics}</div>
      <nav className="side-nav">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-model">
          <span className="status-pulse" />
          <span>{t.modelActive}</span>
          <b>v{summary.data?.modelVersion ?? "—"}</b>
        </div>
        <div className="profile-row">
          <span className="avatar">{login[0]?.toUpperCase()}</span>
          <span className="profile-name">
            {login}
            <small>{t.admin}</small>
          </span>
          <button className="icon-button logout-button" title={t.logout} onClick={logout}>
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}

function Topbar({
  live,
  login,
  theme,
  toggleTheme,
}: {
  live: boolean;
  login: string;
  theme: Theme;
  toggleTheme: () => void;
}) {
  const location = useLocation();
  const titles: Record<string, string> = {
    "/": t.overview,
    "/customers": t.customers,
    "/model": t.settings,
    "/data": t.data,
  };
  return (
    <header className="topbar">
      <div className="breadcrumb">
        <span>{t.analytics}</span>
        <span className="crumb-divider">/</span>
        <strong>{titles[location.pathname] ?? t.overview}</strong>
      </div>
      <div className="topbar-right">
        <span className={`live-status ${live ? "online" : "offline"}`}>
          <span />
          {live ? "Live" : t.live}
        </span>
        <span className="topbar-divider" />
        <span className="topbar-user">{login}</span>
        <ThemeToggle theme={theme} toggleTheme={toggleTheme} />
      </div>
    </header>
  );
}

function PageTitle({
  eyebrow,
  title,
  detail,
  action,
}: {
  eyebrow: string;
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-title-row">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {detail && <p className="page-detail">{detail}</p>}
      </div>
      {action}
    </div>
  );
}

function Dashboard({ theme }: { theme: Theme }) {
  const summary = useSummary();
  const timeline = useQuery({
    queryKey: ["timeline"],
    queryFn: () => api<Timeline>("/api/v1/analytics/churn-timeline"),
  });
  const d = summary.data;
  return (
    <>
      <PageTitle
        eyebrow={t.summary.toUpperCase()}
        title={t.overview}
        detail={d ? `${t.snapshot}: ${d.asOf ? formatDate(d.asOf) : "—"} · v${d.modelVersion}` : t.loading}
        action={
          <div className="as-of-chip">
            <Activity size={15} />
            {t.snapshot}
            <b>{d?.asOf ? new Date(d.asOf).toLocaleString("ru-RU") : "—"}</b>
          </div>
        }
      />
      {summary.isError ? (
        <div className="error-notice">
          <AlertTriangle size={18} />
          {t.dataError}
        </div>
      ) : (
        <>
          <section className="risk-strip">
            {levels.map((level) => (
              <div className={`risk-count ${level}`} key={level}>
                <span className="risk-mark">
                  {level === "high" ? "03" : level === "medium" ? "02" : level === "low" ? "01" : "↘"}
                </span>
                <div>
                  <b>{d?.counts[level] ?? "—"}</b>
                  <span>{levelLabels[level]}</span>
                </div>
                <i />
              </div>
            ))}
          </section>
          <section className="metric-grid">
            <Metric
              label={t.atRisk}
              value={formatEur(d?.revenueAtRiskCents ?? 0)}
              note={t.liveServices}
              formula={formulas.atRisk}
              tone="amber"
              icon={<ShieldAlert size={17} />}
            />
            <Metric
              label={t.expectedLoss}
              value={formatEur(d?.expectedLossCents ?? 0)}
              note="P(churn) · баланс"
              formula={formulas.expectedLoss}
              tone="coral"
              icon={<Activity size={17} />}
            />
            <Metric
              label={t.recoverable}
              value={formatEur(d?.recoverableCents ?? 0)}
              note="Нехватка средств на продление"
              formula={formulas.recoverable}
              tone="teal"
              icon={<ShieldCheck size={17} />}
            />
            <Metric
              label={t.lostMonthly}
              value={formatEur(d?.lostRevenueMonthlyCents ?? 0)}
              note="Ушедшие клиенты"
              formula={formulas.lostMonthly}
              tone="ink"
              icon={<ArrowDown size={17} />}
            />
          </section>
          <section className="dashboard-lower">
            <div className="surface chart-surface">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">{t.dynamics}</p>
                  <h2>{t.churnEvents}</h2>
                </div>
                <Hint text={formulas.chart} label={t.formula} />
              </div>
              <div className="chart-legend">
                <span>
                  <i className="legend-line observed" />
                  {t.observed}
                </span>
                <span>
                  <i className="legend-line estimated" />
                  {t.estimated}
                </span>
                <span>
                  <i className="legend-line forecast" />
                  {t.forecast}
                </span>
                <span>
                  <i className="legend-line as-of" />
                  as_of
                </span>
              </div>
              <div className="timeline-chart">
                {timeline.isLoading ? (
                  <div className="chart-loading">{t.loading}</div>
                ) : (
                  <Chart timeline={timeline.data} theme={theme} />
                )}
              </div>
            </div>
            <div className="surface summary-surface">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">{t.model.toUpperCase()}</p>
                  <h2>{t.modelScore}</h2>
                </div>
                <span className="model-version">v{d?.modelVersion ?? "—"}</span>
              </div>
              <div className="score-summary">
                <span className="score-ring">
                  <b>{d?.averageScore == null ? "—" : Math.round(d.averageScore)}</b>
                  <small>AVG</small>
                </span>
                <div>
                  <strong>{t.averageRisk}</strong>
                  <span>{t.byScored}</span>
                </div>
              </div>
              <div className="summary-divider" />
              <SummaryLine label={t.hourly} value={`${((d?.hourlyShare ?? 0) * 100).toFixed(1)}%`} />
              <SummaryLine
                label={t.scoredCustomers}
                value={String((d?.counts.low ?? 0) + (d?.counts.medium ?? 0) + (d?.counts.high ?? 0))}
              />
              <SummaryLine
                label={t.updated}
                value={d?.calculatedAt ? new Date(d.calculatedAt).toLocaleTimeString("ru-RU") : "—"}
              />
              <NavLink className="text-link" to="/customers">
                {t.openCustomers}
                <ChevronRight size={15} />
              </NavLink>
            </div>
          </section>
        </>
      )}
    </>
  );
}

function Metric({
  label,
  value,
  note,
  formula,
  tone,
  icon,
}: {
  label: string;
  value: string;
  note: string;
  formula: string;
  tone: string;
  icon: ReactNode;
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-top">
        <span>{label}</span>
        <span className="metric-icon">{icon}</span>
      </div>
      <strong>{value}</strong>
      <p>{note}</p>
      <Hint text={formula} label={t.formula} className="metric-hint" withLabel />
    </article>
  );
}

/** Question-mark button that reveals a formula on hover, focus or tap. */
function Hint({
  text,
  label,
  className = "",
  withLabel = false,
}: {
  text: string;
  label: string;
  className?: string;
  withLabel?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className={`hint ${className} ${open ? "open" : ""}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="hint-trigger"
        aria-label={`${label}: ${text}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        onBlur={() => setOpen(false)}
      >
        <CircleHelp size={withLabel ? 13 : 17} />
        {withLabel && label}
      </button>
      {open && (
        <span className="hint-popover" role="tooltip">
          {text}
        </span>
      )}
    </span>
  );
}
function SummaryLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-row">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

const chartPalette: Record<Theme, Record<string, string>> = {
  light: {
    grid: "#dbe2ea",
    tick: "#6d7785",
    observed: "#182d48",
    estimated: "#8a97a8",
    forecast: "#e97c35",
    forecastFill: "#fbe7da",
    asOf: "#c6534b",
  },
  dark: {
    grid: "#2a3d53",
    tick: "#9bacc0",
    observed: "#4cc6f1",
    estimated: "#9bacc0",
    forecast: "#f0a066",
    forecastFill: "#3a2a22",
    asOf: "#f08a80",
  },
};

type ChartRow = { date: string; observed?: number; estimated?: number; forecast?: number };

function dayKey(date: Date) {
  return date.toISOString().slice(0, 10);
}

/**
 * One row per calendar day. A series is 0 on days without events inside its own
 * date range, so lines drop to zero instead of being joined across gaps.
 */
function buildChartRows(timeline: Timeline): ChartRow[] {
  const rows = new Map<string, ChartRow>();
  const ensure = (date: string) => {
    const row = rows.get(date) ?? { date };
    rows.set(date, row);
    return row;
  };
  for (const series of timeline.series) {
    if (!series.points.length) continue;
    const values = new Map(series.points.map((point) => [point.date, point.value]));
    const first = new Date(`${series.points[0].date}T00:00:00Z`);
    const last = new Date(`${series.points[series.points.length - 1].date}T00:00:00Z`);
    for (let day = first; day <= last; day = new Date(day.getTime() + 86_400_000)) {
      const key = dayKey(day);
      ensure(key)[series.type] = values.get(key) ?? 0;
    }
  }
  ensure(timeline.asOfDate);
  return [...rows.values()].sort((a, b) => a.date.localeCompare(b.date));
}

function Chart({ timeline, theme }: { timeline?: Timeline; theme: Theme }) {
  const hasPoints = timeline?.series.some((series) => series.points.length > 0);
  if (!timeline || !hasPoints) return <div className="empty-chart">{t.noEvents}</div>;
  const colors = chartPalette[theme];
  const label = (name: string) => t[name as "observed" | "estimated" | "forecast"] ?? name;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={buildChartRows(timeline)} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={colors.grid} vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(v) => new Date(v).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}
          tickLine={false}
          axisLine={false}
          tick={{ fill: colors.tick, fontSize: 11 }}
          minTickGap={24}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
          tick={{ fill: colors.tick, fontSize: 11 }}
        />
        <Tooltip
          labelFormatter={(v) => formatDate(String(v))}
          formatter={(v: number, name: string) => [
            `${formatCount(Number(v), name === "forecast" ? 2 : 0)} ${t.services_unit}`,
            label(name),
          ]}
        />
        <Area type="monotone" dataKey="forecast" fill={colors.forecastFill} stroke="none" legendType="none" />
        <Line type="monotone" dataKey="observed" stroke={colors.observed} strokeWidth={2.5} dot={false} />
        <Line
          type="monotone"
          dataKey="estimated"
          stroke={colors.estimated}
          strokeWidth={1.8}
          strokeDasharray="5 5"
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="forecast"
          stroke={colors.forecast}
          strokeWidth={2}
          strokeDasharray="2 5"
          dot={false}
        />
        <ReferenceLine
          x={timeline.asOfDate}
          stroke={colors.asOf}
          strokeWidth={1.5}
          strokeDasharray="6 4"
          label={{
            value: "as_of",
            position: "insideTopRight",
            fill: colors.asOf,
            fontSize: 10,
            fontFamily: "DM Mono, monospace",
          }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function scoreText(score: number | null, level: Level) {
  if (score !== null) return score.toFixed(1);
  return level === "churned" ? t.churned : t.noData;
}

const specialStateText: Partial<Record<Level, string>> = {
  churned: "Клиент ушёл / неактивен: живых услуг нет, есть удалённые или заблокированные. Кандидат в win-back.",
  no_data: "Недостаточно данных для оценки: нет услуг или ни один признак не применим.",
};

function Customers() {
  const [level, setLevel] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [selected, setSelected] = useState<number | null>(null);
  const params = new URLSearchParams({ page: String(page), size: "20", sort_by: sortBy, order });
  if (level) params.set("level", level);
  if (search) params.set("q", search);
  const q = useQuery({
    queryKey: ["customers", level, search, page, sortBy, order],
    queryFn: () => api<CustomerPage>(`/api/v1/customers?${params}`),
  });
  function sort(key: string) {
    if (key === sortBy) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSortBy(key);
      setOrder("desc");
    }
  }
  return (
    <>
      <PageTitle eyebrow={t.customers.toUpperCase()} title={t.customers} detail={`${q.data?.total ?? "—"}`} />
      <section className="surface table-surface">
        <div className="table-toolbar">
          <label className="search-box">
            <Search size={16} />
            <input
              placeholder={t.findCustomer}
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </label>
          <label className="select-wrap">
            <span>{t.filterLevel}</span>
            <select
              value={level}
              onChange={(e) => {
                setLevel(e.target.value);
                setPage(1);
              }}
            >
              <option value="">{t.allCustomers}</option>
              {levels.map((v) => (
                <option key={v} value={v}>
                  {levelLabels[v]}
                </option>
              ))}
            </select>
          </label>
          <button
            className="button button-quiet"
            onClick={() => {
              setSearch("");
              setLevel("");
              setPage(1);
            }}
          >
            {t.reset}
          </button>
        </div>
        <div className="table-scroll">
          <table className="customer-table">
            <thead>
              <tr>
                {sortOptions.map(([key, label]) => (
                  <th key={key}>
                    <button className="sort-button" onClick={() => sort(key)}>
                      {label}
                      {sortBy === key ? (
                        order === "asc" ? (
                          <ArrowUp size={13} />
                        ) : (
                          <ArrowDown size={13} />
                        )
                      ) : (
                        <ArrowUpDown size={13} />
                      )}
                    </button>
                  </th>
                ))}
                <th>{t.filterLevel}</th>
                <th>{t.reason}</th>
              </tr>
            </thead>
            <tbody>
              {q.data?.items.map((c) => (
                <tr key={c.id} onClick={() => setSelected(c.id)}>
                  <td>{c.id}</td>
                  <td>{c.email}</td>
                  <td>{formatEur(c.balanceCents)}</td>
                  <td>{formatEur(c.totalReplenishedCents)}</td>
                  <td>{scoreText(c.score, c.level)}</td>
                  <td>{formatEur(c.expectedLossCents)}</td>
                  <td>
                    <span className={`level-badge ${c.level}`}>{levelLabels[c.level]}</span>
                  </td>
                  <td className="reason-cell">{c.topReason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {q.isLoading && <div className="table-empty">{t.loading}</div>}
          {q.data?.items.length === 0 && <div className="table-empty">{t.noResults}</div>}
        </div>
        <div className="table-footer">
          <span>
            {t.shown} {q.data?.items.length ?? 0} {t.of} {q.data?.total ?? 0}
          </span>
          <div className="pagination">
            <button
              className="icon-button"
              disabled={page <= 1}
              title={t.previous}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft size={17} />
            </button>
            {page}
            <button
              className="icon-button"
              disabled={page * 20 >= (q.data?.total ?? 0)}
              title={t.next}
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight size={17} />
            </button>
          </div>
        </div>
      </section>
      {selected !== null && <CustomerPanel id={selected} close={() => setSelected(null)} />}
    </>
  );
}

function CustomerPanel({ id, close }: { id: number; close: () => void }) {
  const q = useQuery({
    queryKey: ["customer", id],
    queryFn: () => api<CustomerDetail>(`/api/v1/customers/${id}`),
  });
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);
  const d = q.data;
  const liveValue = d?.services.reduce((sum, service) => sum + service.valueCents, 0) ?? 0;
  const available = d ? d.balanceCents + (d.bonusState === "unlocked" ? d.bonusBalanceCents : 0) : 0;
  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <aside className="customer-drawer" role="dialog" aria-modal="true" aria-label={t.detail}>
        <div className="drawer-header">
          <span className="eyebrow">{t.detail}</span>
          <button className="icon-button" title={t.close} onClick={close} autoFocus>
            <X size={18} />
          </button>
        </div>
        {q.isError && (
          <div className="error-notice">
            <AlertTriangle size={18} />
            {t.dataError}
          </div>
        )}
        {d ? (
          <>
            <div className="drawer-identity">
              <span className="drawer-avatar">{id}</span>
              <h2>{d.email}</h2>
            </div>
            <div className="drawer-score">
              {scoreText(d.score, d.level)}
              <span className={`level-badge ${d.level}`}>{levelLabels[d.level]}</span>
              <span className="loyalty">
                {t.loyalty} {d.loyalty?.toFixed(0) ?? "—"}
              </span>
            </div>
            {specialStateText[d.level] && <p className="drawer-note">{specialStateText[d.level]}</p>}
            <div className="drawer-stats">
              <div>
                <span>{t.balance}</span>
                <b>{formatEur(d.balanceCents)}</b>
              </div>
              <div>
                <span>Доступно (с бонусом)</span>
                <b>{formatEur(available)}</b>
              </div>
              <div>
                <span>Стоимость живых услуг</span>
                <b>{formatEur(liveValue)}</b>
              </div>
              <div>
                <span>{t.expectedLoss}</span>
                <b>{formatEur(d.expectedLossCents)}</b>
              </div>
            </div>
            <p className="drawer-note">
              Стоимость — цена услуг за денежный горизонт. Ожидаемые потери — стоимость × вероятность
              оттока × (1 − защита балансом × покрытие).
            </p>
            {d.dataWarnings.length > 0 && (
              <section className="drawer-section">
                <h3>{t.warnings}</h3>
                {d.dataWarnings.map((w, i) => (
                  <div className="warning-item" key={`${w.code}-${i}`}>
                    <AlertTriangle size={15} />
                    {w.message}
                  </div>
                ))}
              </section>
            )}
            {d.reasons.length > 0 && (
              <section className="drawer-section">
                <h3>{t.reasons}</h3>
                {d.reasons.map((r, i) => (
                  <div className="reason-item" key={i}>
                    <span className="reason-rank">0{i + 1}</span>
                    <span>
                      {r.explanation}
                      <small className="reason-points"> +{r.scoreContribution.toFixed(1)} балла</small>
                    </span>
                  </div>
                ))}
              </section>
            )}
            <section className="drawer-section">
              <h3>
                {t.services} · {d.services.length}
              </h3>
              {d.services.map((s) => (
                <div className="service-block" key={s.id}>
                  <div className="service-head">
                    <b>{s.name}</b>
                    <span>{s.score === null ? "—" : `score ${s.score.toFixed(1)}`}</span>
                  </div>
                  <div className="service-sub">
                    <span className={`status-tag ${s.status}`}>{statusLabels[s.status] ?? s.status}</span>
                    <span>до {formatDate(s.expiresAt)}</span>
                    <span>
                      {formatEur(s.priceCents)} / {termLabels[s.paymentTerm] ?? s.paymentTerm}
                    </span>
                    <span>автопродление {s.autoProlong ? "вкл." : "выкл."}</span>
                  </div>
                  {s.valueCents > 0 && (
                    <div className="service-money">
                      <span>Стоимость {formatEur(s.valueCents)}</span>
                      <span>Ожидаемые потери {formatEur(s.expectedLossCents)}</span>
                    </div>
                  )}
                  {[...s.featureContributions]
                    .sort((a, b) => b.scoreContribution - a.scoreContribution)
                    .map((f) => (
                      <div className="feature-bar" key={f.key} title={f.explanation}>
                        <span>{f.title}</span>
                        <span>{f.scoreContribution.toFixed(1)}</span>
                        <i style={{ width: `${Math.min(100, Math.max(0, f.scoreContribution))}%` }} />
                      </div>
                    ))}
                </div>
              ))}
            </section>
          </>
        ) : (
          !q.isError && <p>{t.loading}</p>
        )}
      </aside>
    </div>
  );
}

function validateSettings(value: ModelSettings): string[] {
  const errors: string[] = [];
  const inRange = (n: number, min: number, max: number) => Number.isFinite(n) && n >= min && n <= max;
  if (Object.values(value.weights).some((w) => !inRange(w, 0, 100))) errors.push("веса должны быть от 0 до 100");
  if (!inRange(value.thresholds.low, 0, 100) || !inRange(value.thresholds.high, 0, 100))
    errors.push("пороги должны быть от 0 до 100");
  else if (value.thresholds.low >= value.thresholds.high)
    errors.push("порог «низкий / средний» должен быть меньше порога «средний / высокий»");
  if (!(value.horizon_days > 0) || !(value.horizon_money_days > 0)) errors.push("горизонты должны быть больше 0");
  if (!inRange(value.alpha_max_mean, 0, 1)) errors.push("α должна быть от 0 до 1");
  if (!(value.churn_curve.k > 0) || value.churn_curve.k > 10) errors.push("k должен быть больше 0 и не больше 10");
  if (!inRange(value.churn_curve.midpoint, 0, 100)) errors.push("середина кривой должна быть от 0 до 100");
  if (!inRange(value.balance_shield, 0, 1)) errors.push("защита балансом должна быть от 0 до 1");
  if (!inRange(value.suspended_value, 0, 1)) errors.push("значение для приостановленных услуг — от 0 до 1");
  if (value.as_of_mode === "fixed" && !value.as_of_fixed) errors.push("укажите дату для фиксированной точки отсчёта");
  return errors;
}

const sameSettings = (a: ModelSettings | null, b: ModelSettings | null) => JSON.stringify(a) === JSON.stringify(b);

function Model() {
  const client = useQueryClient();
  const q = useQuery({
    queryKey: ["model-settings"],
    queryFn: () => api<ModelSettingsResponse>("/api/v1/model/settings"),
  });
  const [value, setValue] = useState<ModelSettings | null>(null);
  const [state, setState] = useState(t.saved);
  // Last settings the server confirmed. Local edits are compared against it, so a
  // refetch (after our own save or an SSE event) never overwrites what is being typed.
  const synced = useRef<ModelSettings | null>(null);
  const latest = useRef<ModelSettings | null>(null);
  latest.current = value;

  useEffect(() => {
    if (!q.data) return;
    const untouched = latest.current === null || sameSettings(latest.current, synced.current);
    synced.current = q.data.settings;
    if (untouched) setValue(q.data.settings);
  }, [q.data]);

  const errors = value ? validateSettings(value) : [];
  useEffect(() => {
    if (!value || sameSettings(value, synced.current)) return;
    if (validateSettings(value).length) {
      setState("Не сохранено: исправьте значения");
      return;
    }
    setState(t.saving);
    const sent = value;
    const timer = window.setTimeout(async () => {
      try {
        const saved = await api<{ version: number; settings: ModelSettings }>("/api/v1/model/settings", {
          method: "PATCH",
          body: JSON.stringify(sent),
        });
        synced.current = saved.settings;
        // Adopt the server's normalised copy (e.g. timestamp format) unless the user kept typing.
        setValue((current) => (sameSettings(current, sent) ? saved.settings : current));
        client.setQueryData<ModelSettingsResponse>(["model-settings"], (old) =>
          old ? { ...old, settings: saved.settings, version: saved.version } : old,
        );
        await client.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "model-settings" });
        setState(`${t.saved} · v${saved.version}`);
      } catch (error) {
        setState(error instanceof ApiError ? `${t.saveError}: ${error.message}` : t.saveError);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [value, client]);

  if (!q.data || !value)
    return (
      <>
        <PageTitle eyebrow={t.settings} title={t.model} />
        <div className="surface loading-surface">{q.isError ? t.dataError : t.loading}</div>
      </>
    );
  const defaults = q.data.defaults;
  const update = (patch: Partial<ModelSettings>) => setValue((old) => (old ? { ...old, ...patch } : old));
  const nested = (key: "thresholds" | "churn_curve", patch: Record<string, number>) =>
    setValue((old) => (old ? { ...old, [key]: { ...old[key], ...patch } } : old));
  const setWeight = (key: string, weight: number) =>
    setValue((old) => (old ? { ...old, weights: { ...old.weights, [key]: weight } } : old));
  return (
    <>
      <PageTitle
        eyebrow="SCORING"
        title={t.settings}
        detail={`v${q.data.version}`}
        action={
          <button className="button button-quiet" onClick={() => setValue(defaults)}>
            {t.resetDefaults}
          </button>
        }
      />
      {errors.length > 0 && (
        <div className="error-notice settings-errors">
          <AlertTriangle size={18} />
          {errors.join("; ")}
        </div>
      )}
      <div className="model-layout">
        <section className="surface model-main">
          <div className="section-heading">
            <h2>{t.weights}</h2>
            <span className="save-state">{state}</span>
          </div>
          {q.data.features.map((f: FeatureDescription) => (
            <div className="feature-control" key={f.key}>
              <div className="feature-info">
                <div>
                  <strong>{f.title}</strong>
                  <span>{f.description}</span>
                </div>
                <span className={`scope-tag ${f.scope}`}>
                  {f.scope === "service" ? t.service : t.account}
                </span>
              </div>
              <div className="feature-slider-row">
                <input
                  type="range"
                  min="0"
                  max="100"
                  aria-label={`${f.title}: ${t.weight}`}
                  value={value.weights[f.key] ?? f.default_weight}
                  onChange={(e) => setWeight(f.key, Number(e.target.value))}
                />
                <input
                  type="number"
                  min="0"
                  max="100"
                  aria-label={`${f.title}: ${t.weight}`}
                  value={value.weights[f.key] ?? f.default_weight}
                  onChange={(e) => setWeight(f.key, Number(e.target.value))}
                />
              </div>
            </div>
          ))}
        </section>
        <aside className="model-side">
          <SettingsPanel title={t.thresholds}>
            <NumericField
              label={t.lowMedium}
              value={value.thresholds.low}
              onChange={(n) => nested("thresholds", { low: n })}
            />
            <NumericField
              label={t.mediumHigh}
              value={value.thresholds.high}
              onChange={(n) => nested("thresholds", { high: n })}
            />
          </SettingsPanel>
          <SettingsPanel title={t.horizon}>
            <NumericField
              label={`${t.riskHorizon}, ${t.days}`}
              value={value.horizon_days}
              onChange={(n) => update({ horizon_days: n })}
            />
            <NumericField
              label={`${t.moneyHorizon}, ${t.days}`}
              value={value.horizon_money_days}
              onChange={(n) => update({ horizon_money_days: n })}
            />
            <NumericField
              label={t.alpha}
              value={value.alpha_max_mean}
              step={0.05}
              onChange={(n) => update({ alpha_max_mean: n })}
            />
          </SettingsPanel>
          <SettingsPanel title={t.curve}>
            <NumericField
              label="k"
              value={value.churn_curve.k}
              step={0.01}
              onChange={(n) => nested("churn_curve", { k: n })}
            />
            <NumericField
              label={t.midpoint}
              value={value.churn_curve.midpoint}
              onChange={(n) => nested("churn_curve", { midpoint: n })}
            />
            <NumericField
              label={t.shield}
              value={value.balance_shield}
              step={0.05}
              onChange={(n) => update({ balance_shield: n })}
            />
            <NumericField
              label="Значение для приостановленных"
              value={value.suspended_value}
              step={0.05}
              onChange={(n) => update({ suspended_value: n })}
            />
          </SettingsPanel>
          <SettingsPanel title={t.asOf}>
            <select
              value={value.as_of_mode}
              aria-label={t.mode}
              onChange={(e) => update({ as_of_mode: e.target.value as ModelSettings["as_of_mode"] })}
            >
              <option value="snapshot">{t.snapshotMode}</option>
              <option value="now">{t.nowMode}</option>
              <option value="fixed">{t.fixedMode}</option>
            </select>
            {value.as_of_mode === "fixed" && (
              <input
                type="datetime-local"
                aria-label={t.fixedMode}
                value={toLocalInput(value.as_of_fixed)}
                onChange={(e) =>
                  update({ as_of_fixed: e.target.value ? new Date(e.target.value).toISOString() : null })
                }
              />
            )}
          </SettingsPanel>
        </aside>
      </div>
    </>
  );
}
function SettingsPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="surface settings-panel">
      <p className="eyebrow">{title}</p>
      {children}
    </section>
  );
}
function NumericField({
  label,
  value,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="number-control">
      <span>{label}</span>
      <input
        type="number"
        step={step}
        value={Number.isNaN(value) ? "" : value}
        onChange={(e) => onChange(e.target.value === "" ? Number.NaN : Number(e.target.value))}
      />
    </label>
  );
}

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
type SnapshotResult = {
  accounts: number;
  services: number;
  transactions: number;
  changedStatuses: number;
  modelVersion: number;
};

function Data() {
  const client = useQueryClient();
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(request: () => Promise<SnapshotResult>, source: string) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await request();
      setMessage({
        ok: true,
        text:
          `${source}: ${t.dataLoaded} ${result.accounts} аккаунтов, ${result.services} услуг, ` +
          `${result.transactions} транзакций; смен статуса: ${result.changedStatuses}; модель v${result.modelVersion}.`,
      });
      await client.invalidateQueries();
    } catch (error) {
      setMessage({
        ok: false,
        text: error instanceof ApiError ? `${t.dataError}: ${error.message}` : t.dataError,
      });
    } finally {
      setBusy(false);
    }
  }

  const preset = (name: "demo" | "official") =>
    run(
      () => api<SnapshotResult>(`/api/v1/source/presets/${name}`, { method: "POST" }),
      name === "demo" ? t.demo : t.official,
    );

  async function file(selectedFile?: File) {
    if (!selectedFile) return;
    if (selectedFile.size > MAX_UPLOAD_BYTES) {
      setMessage({ ok: false, text: "Файл больше 20 MB." });
      return;
    }
    let payload: unknown;
    try {
      payload = JSON.parse(await selectedFile.text());
    } catch {
      setMessage({ ok: false, text: t.noFile });
      return;
    }
    await run(
      () => api<SnapshotResult>("/api/v1/source/snapshot", { method: "PUT", body: JSON.stringify(payload) }),
      selectedFile.name,
    );
  }

  return (
    <>
      <PageTitle eyebrow={t.source} title={t.data} detail={t.replaceSource} />
      <section className="surface data-layout">
        <div className="data-intro">
          <span className="data-icon">
            <Database size={22} />
          </span>
          <div>
            <p className="eyebrow">{t.replaceSource}</p>
            <h2>{t.upload}</h2>
            <p>{dataDescription}</p>
          </div>
        </div>
        <label className="upload-drop">
          <input
            type="file"
            accept="application/json,.json"
            disabled={busy}
            onChange={(event) => {
              void file(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
          <span className="upload-icon">
            <CloudUpload size={24} />
          </span>
          <strong>{t.chooseFile}</strong>
          <span>{t.dropFile}</span>
          <small>
            <FileJson2 size={13} />
            JSON · 20 MB
          </small>
        </label>
        <div className="preset-row">
          <span>{t.presets}</span>
          <button className="button button-secondary" disabled={busy} onClick={() => void preset("demo")}>
            {t.demo}
          </button>
          <button className="button button-quiet" disabled={busy} onClick={() => void preset("official")}>
            {t.official}
          </button>
        </div>
        {busy && (
          <div className="inline-progress">
            <span />
            {t.validating}
          </div>
        )}
        {message && (
          <div className={`upload-message ${message.ok ? "success" : "error"}`} role="status">
            {message.text}
          </div>
        )}
      </section>
      <div className="data-note">
        <ShieldCheck size={16} />
        {atomicDataHint}
      </div>
    </>
  );
}
