

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import matplotlib  

matplotlib.use("Agg")
import matplotlib.pyplot as plt  

from app.ingestion.quality import find_quality_warnings  
from app.ingestion.schemas import SnapshotInput  
from app.scoring.context import PERIOD_DAYS  
from app.scoring.engine import compute_scoring  
from app.scoring.money import churn_probability, compute_money, service_value_cents  
from app.scoring.registry import FEATURES  
from app.scoring.settings import ScoringSettings  

DATA = ROOT / "data"
IMG = ROOT / "docs" / "img"
LEVELS = ["low", "medium", "high", "churned", "no_data"]
LEVEL_RU = {
    "low": "низкий",
    "medium": "средний",
    "high": "высокий",
    "churned": "ушёл",
    "no_data": "нет оценки",
}


SERIES_1 = "#2a78d6"
SERIES_2 = "#eb6834"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"


def load(name: str) -> SnapshotInput:
    return SnapshotInput.model_validate(json.loads((DATA / f"{name}.json").read_text("utf-8")))


def style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=MUTED, labelsize=9, length=0, pad=6)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def new_figure(width: float = 7.2, height: float = 3.6):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(width, height), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    style_axes(ax)
    return fig, ax


def save(fig, name: str) -> str:
    IMG.mkdir(parents=True, exist_ok=True)
    path = IMG / name
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return f"img/{name}"


def title(ax, text: str, subtitle: str | None = None) -> None:
    ax.set_title(text, loc="left", color=INK, fontsize=11.5, fontweight="bold", pad=18 if subtitle else 10)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK_2, fontsize=9, va="bottom")





def level_counts(scoring) -> dict[str, int]:
    counts = Counter(item.level for item in scoring.customers)
    return {level: counts.get(level, 0) for level in LEVELS}


def spearman(a: list[float], b: list[float]) -> float:
    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda index: values[index])
        result = [0.0] * len(values)
        position = 0
        while position < len(order):
            end = position
            while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
                end += 1
            for index in range(position, end + 1):
                result[order[index]] = (position + end) / 2
            position = end + 1
        return result

    ra, rb = ranks(a), ranks(b)
    ma, mb = mean(ra), mean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    var = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return cov / var if var else 1.0


def auc(scores_pos: list[float], scores_neg: list[float]) -> float:
    wins = 0.0
    for p in scores_pos:
        for n in scores_neg:
            wins += 1 if p > n else 0.5 if p == n else 0
    return wins / (len(scores_pos) * len(scores_neg))


def dataset_overview(snapshot: SnapshotInput, settings: ScoringSettings) -> dict:
    scoring = compute_scoring(snapshot, settings)
    _, money = compute_money(snapshot.accounts, snapshot.services, scoring, settings)
    scores = [item.score for item in scoring.customers if item.score is not None]
    return {
        "as_of": scoring.as_of.isoformat(),
        "accounts": len(snapshot.accounts),
        "services": len(snapshot.services),
        "transactions": len(snapshot.transactions),
        "service_status": dict(Counter(service.status for service in snapshot.services)),
        "payment_terms": dict(Counter(service.payment_term for service in snapshot.services)),
        "levels": level_counts(scoring),
        "score": {
            "min": round(min(scores), 1),
            "median": round(median(scores), 1),
            "mean": round(mean(scores), 1),
            "max": round(max(scores), 1),
            "distinct": len({round(score, 1) for score in scores}),
        },
        "money_eur": {
            "revenue_at_risk": money.revenue_at_risk_cents / 100,
            "expected_loss": money.expected_loss_cents / 100,
            "recoverable": money.recoverable_cents / 100,
            "lost_revenue_monthly": money.lost_revenue_monthly_cents / 100,
            "hourly_share": round(money.hourly_share, 3),
        },
        "quality_warnings": dict(Counter(item["code"] for item in find_quality_warnings(snapshot))),
    }


def feature_stats(snapshot: SnapshotInput, settings: ScoringSettings) -> list[dict]:
    scoring = compute_scoring(snapshot, settings)
    total_services = len(scoring.services)
    applicable = Counter()
    values = defaultdict(list)
    points = Counter()
    for service in scoring.services:
        for item in service.contributions:
            applicable[item["key"]] += 1
            values[item["key"]].append(item["value"])
            points[item["key"]] += item["scoreContribution"]
    total_points = sum(points.values()) or 1
    rows = []
    for key, feature in FEATURES.items():
        rows.append(
            {
                "key": key,
                "title": feature.title,
                "weight": settings.weights[key],
                "applicable_share": round(applicable[key] / total_services, 3),
                "mean_value": round(mean(values[key]), 3) if values[key] else None,
                "points_share": round(points[key] / total_points, 3),
            }
        )
    return sorted(rows, key=lambda row: row["points_share"], reverse=True)


def customer_scores(snapshot, settings) -> dict[int, tuple[str, float | None]]:
    return {
        item.customer_id: (item.level, item.score)
        for item in compute_scoring(snapshot, settings).customers
    }


def sensitivity(snapshot: SnapshotInput, base: ScoringSettings) -> dict:
    base_scores = customer_scores(snapshot, base)
    scored_ids = [cid for cid, (_, score) in base_scores.items() if score is not None]
    base_loss = compute_money(
        snapshot.accounts, snapshot.services, compute_scoring(snapshot, base), base
    )[1].expected_loss_cents

    def compare(settings: ScoringSettings) -> dict:
        scores = customer_scores(snapshot, settings)
        common = [cid for cid in scored_ids if scores[cid][1] is not None]
        changed = sum(scores[cid][0] != base_scores[cid][0] for cid in scored_ids)
        loss = compute_money(
            snapshot.accounts, snapshot.services, compute_scoring(snapshot, settings), settings
        )[1].expected_loss_cents
        return {
            "level_changes": changed,
            "level_changes_share": round(changed / len(scored_ids), 3),
            "rank_spearman": round(
                spearman([base_scores[c][1] for c in common], [scores[c][1] for c in common]), 3
            ),
            "expected_loss_change": round(loss / base_loss - 1, 3) if base_loss else None,
            "levels": level_counts(compute_scoring(snapshot, settings)),
        }

    weights = {}
    for key in FEATURES:
        weights[key] = {}
        for label, factor in (("x0", 0.0), ("x2", 2.0)):
            changed_weights = dict(base.weights)
            changed_weights[key] = min(100.0, base.weights[key] * factor)
            weights[key][label] = compare(base.model_copy(update={"weights": changed_weights}))

    thresholds = {}
    for low, high in ((25, 55), (30, 60), (35, 65), (40, 70), (45, 75)):
        settings = base.model_copy(
            update={"thresholds": base.thresholds.model_copy(update={"low": low, "high": high})}
        )
        thresholds[f"{low}/{high}"] = level_counts(compute_scoring(snapshot, settings))

    horizons = {}
    for days in (3, 7, 14, 30):
        settings = base.model_copy(update={"horizon_days": days})
        result = compare(settings)
        money = compute_money(
            snapshot.accounts, snapshot.services, compute_scoring(snapshot, settings), settings
        )[1]
        horizons[str(days)] = {**result, "recoverable_eur": money.recoverable_cents / 100}

    alphas = {
        str(alpha): compare(base.model_copy(update={"alpha_max_mean": alpha}))
        for alpha in (0.0, 0.5, 0.7, 1.0)
    }
    return {"weights": weights, "thresholds": thresholds, "horizon_days": horizons, "alpha": alphas}


def backtest(step1: SnapshotInput, step2: SnapshotInput, settings: ScoringSettings) -> dict:

    scoring = compute_scoring(step1, settings)
    lost_owner = set()
    old = {service.id: service for service in step1.services}
    for service in step2.services:
        previous = old.get(service.id)
        if (
            previous
            and previous.status not in {"deleted", "blocked"}
            and service.status in {"deleted", "blocked"}
        ):
            lost_owner.add(service.owner_id)
    scored = [item for item in scoring.customers if item.score is not None]
    positives = [item.score for item in scored if item.customer_id in lost_owner]
    negatives = [item.score for item in scored if item.customer_id not in lost_owner]
    by_level = {}
    for level in ("low", "medium", "high"):
        group = [item for item in scored if item.level == level]
        lost = sum(item.customer_id in lost_owner for item in group)
        by_level[level] = {
            "customers": len(group),
            "lost": lost,
            "rate": round(lost / len(group), 3) if group else None,
            "mean_p_churn": round(
                mean(churn_probability(item.score, settings) for item in group), 3
            )
            if group
            else None,
        }
    after = {item.customer_id: item for item in compute_scoring(step2, settings).customers}
    replenished_before = {account.id: account.total_replenished for account in step1.accounts}
    topped_up = {
        account.id
        for account in step2.accounts
        if account.total_replenished > replenished_before[account.id]
    }
    dropped = [
        {
            "customer": item.customer_id,
            "before": round(item.score, 1),
            "after": round(after[item.customer_id].score, 1),
            "level_after": after[item.customer_id].level,
            "topped_up": item.customer_id in topped_up,
            "lost_service": item.customer_id in lost_owner,
        }
        for item in scored
        if item.level == "high"
        and after[item.customer_id].score is not None
        and after[item.customer_id].level in {"low", "medium"}
    ]
    rescued = [row for row in dropped if row["topped_up"]]
    partially_lost = [row for row in dropped if row["lost_service"] and not row["topped_up"]]
    return {
        "customers_scored": len(scored),
        "customers_lost_service": len(positives),
        "auc": round(auc(positives, negatives), 3) if positives and negatives else None,
        "by_level": by_level,
        "high_to_lower_level": len(dropped),
        "rescued_high_customers": rescued,
        "high_lost_risky_service": partially_lost,
    }


def official_table(snapshot: SnapshotInput, settings: ScoringSettings) -> list[dict]:
    scoring = compute_scoring(snapshot, settings)
    accounts = {account.id: account for account in snapshot.accounts}
    rows = []
    for item in scoring.customers:
        account = accounts[item.customer_id]
        rows.append(
            {
                "customer": item.customer_id,
                "level": item.level,
                "score": round(item.score, 1) if item.score is not None else None,
                "balance_eur": account.balance / 100,
                "top_reason": item.reasons[0]["explanation"] if item.reasons else None,
            }
        )
    return rows


def revenue_by_term(snapshot: SnapshotInput, settings: ScoringSettings) -> dict[str, float]:
    scoring = compute_scoring(snapshot, settings)
    risky = {item.customer_id for item in scoring.customers if item.level in {"medium", "high"}}
    totals = Counter()
    for service in snapshot.services:
        if service.owner_id in risky and service.status in {"active", "suspended", "prolong_wait"}:
            totals[service.payment_term] += service_value_cents(service, settings) / 100
    return {term: round(totals.get(term, 0), 2) for term in PERIOD_DAYS}





def chart_score_distribution(snapshot, settings) -> str:
    scores = [
        item.score for item in compute_scoring(snapshot, settings).customers if item.score is not None
    ]
    fig, ax = new_figure()
    bins = list(range(0, 101, 5))
    ax.hist(scores, bins=bins, color=SERIES_1, edgecolor=SURFACE, linewidth=1.5)
    for value, label in ((settings.thresholds.low, "порог 35"), (settings.thresholds.high, "порог 65")):
        ax.axvline(value, color=INK_2, linewidth=1)
        ax.text(value + 1, ax.get_ylim()[1] * 0.92, label, color=INK_2, fontsize=8.5)
    ax.set_xlim(0, 100)
    ax.set_xlabel("score клиента", color=INK_2, fontsize=9)
    ax.set_ylabel("клиентов", color=INK_2, fontsize=9)
    title(ax, "Распределение score, демо-набор", f"{len(scores)} клиентов с оценкой, шаг 5 баллов")
    return save(fig, "analysis-score-distribution.png")


def chart_feature_points(rows: list[dict]) -> str:
    fig, ax = new_figure(7.2, 3.9)
    ordered = list(reversed(rows))
    labels = [row["title"] for row in ordered]
    values = [row["points_share"] * 100 for row in ordered]
    bars = ax.barh(labels, values, color=SERIES_1, height=0.6)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    for bar, value in zip(bars, values):
        ax.text(bar.get_width() + 0.6, bar.get_y() + bar.get_height() / 2, f"{value:.1f}%",
                va="center", color=INK_2, fontsize=8.5)
    ax.set_xlim(0, max(values) * 1.18)
    ax.tick_params(axis="y", colors=INK_2)
    title(ax, "Вклад признаков в сумму баллов риска", "доля от всех баллов score по услугам, демо-набор")
    return save(fig, "analysis-feature-points.png")


def chart_weight_sensitivity(sens: dict) -> str:
    keys = sorted(
        FEATURES, key=lambda key: sens["weights"][key]["x0"]["level_changes"], reverse=False
    )
    labels = [FEATURES[key].title for key in keys]
    zero = [sens["weights"][key]["x0"]["level_changes"] for key in keys]
    double = [sens["weights"][key]["x2"]["level_changes"] for key in keys]
    fig, ax = new_figure(7.2, 4.2)
    positions = range(len(keys))
    height = 0.36
    ax.barh([p + height / 2 + 0.02 for p in positions], zero, height=height, color=SERIES_1, label="вес → 0")
    ax.barh([p - height / 2 - 0.02 for p in positions], double, height=height, color=SERIES_2, label="вес × 2")
    ax.set_yticks(list(positions), labels)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.tick_params(axis="y", colors=INK_2)
    ax.set_xlabel("клиентов сменили уровень риска", color=INK_2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="lower right", labelcolor=INK_2)
    title(ax, "Чувствительность уровней к весам", "демо-набор, остальные настройки по умолчанию")
    return save(fig, "analysis-weight-sensitivity.png")


def chart_backtest(bt: dict) -> str:
    fig, ax = new_figure(6.4, 3.4)
    levels = ["low", "medium", "high"]
    rates = [(bt["by_level"][level]["rate"] or 0) * 100 for level in levels]
    labels = [f"{LEVEL_RU[level]}\n({bt['by_level'][level]['customers']} кл.)" for level in levels]
    bars = ax.bar(labels, rates, color=SERIES_1, width=0.55)
    for bar, value in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.2, f"{value:.0f}%",
                ha="center", color=INK, fontsize=10)
    ax.set_ylim(0, max(100, max(rates) * 1.15))
    ax.set_ylabel("потеряли услугу за сутки, %", color=INK_2, fontsize=9)
    ax.tick_params(axis="x", colors=INK_2)
    title(ax, "Уровень риска в день 1 и потеря услуги к дню 2", "демо → «через сутки», синтетическая проверка")
    return save(fig, "analysis-backtest.png")


def chart_churn_curve(settings: ScoringSettings) -> str:
    fig, ax = new_figure(6.4, 3.3)
    xs = [x / 2 for x in range(0, 201)]
    ys = [churn_probability(x, settings) * 100 for x in xs]
    ax.plot(xs, ys, color=SERIES_1, linewidth=2)
    for x in (settings.thresholds.low, settings.churn_curve.midpoint, settings.thresholds.high):
        y = churn_probability(x, settings) * 100
        ax.plot([x], [y], marker="o", markersize=6, color=SERIES_1, markeredgecolor=SURFACE, markeredgewidth=2)
        ax.text(x + 2, y - 7, f"{x:.0f} → {y:.0f}%", color=INK_2, fontsize=8.5)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel("score услуги", color=INK_2, fontsize=9)
    ax.set_ylabel("P(отток), %", color=INK_2, fontsize=9)
    title(ax, "Кривая вероятности оттока", "логистическая: k = 0,08, середина s₀ = 60")
    return save(fig, "analysis-churn-curve.png")


def chart_revenue_by_term(totals: dict[str, float]) -> str:
    labels_ru = {
        "hour": "час", "week": "неделя", "month": "месяц",
        "quarter_year": "квартал", "half_year": "полгода", "year": "год",
    }
    fig, ax = new_figure(6.4, 3.3)
    terms = list(totals)
    values = [totals[t] / 1000 for t in terms]
    colors = [SERIES_2 if t == "hour" else SERIES_1 for t in terms]
    bars = ax.bar([labels_ru[t] for t in terms], values, color=colors, width=0.55)
    for bar, value in zip(bars, values):
        if value:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.02,
                    f"{value:.1f}", ha="center", color=INK, fontsize=9)
    ax.set_ylabel("тыс. € за 30 дней", color=INK_2, fontsize=9)
    ax.tick_params(axis="x", colors=INK_2)
    title(ax, "Выручка под риском по периоду оплаты", "демо-набор; почасовые выделены")
    return save(fig, "analysis-revenue-by-term.png")


def main() -> None:
    settings = ScoringSettings()
    official, demo, step2 = load("official"), load("demo"), load("demo-step2")
    features = feature_stats(demo, settings)
    sens = sensitivity(demo, settings)
    bt = backtest(demo, step2, settings)
    terms = revenue_by_term(demo, settings)
    result = {
        "settings": settings.model_dump(mode="json"),
        "datasets": {
            "official": dataset_overview(official, settings),
            "demo": dataset_overview(demo, settings),
            "demo-step2": dataset_overview(step2, settings),
        },
        "official_customers": official_table(official, settings),
        "features_demo": features,
        "features_official": feature_stats(official, settings),
        "sensitivity_demo": sens,
        "backtest_demo_to_step2": bt,
        "revenue_at_risk_by_term_demo_eur": terms,
        "charts": {
            "score_distribution": chart_score_distribution(demo, settings),
            "feature_points": chart_feature_points(features),
            "weight_sensitivity": chart_weight_sensitivity(sens),
            "backtest": chart_backtest(bt),
            "churn_curve": chart_churn_curve(settings),
            "revenue_by_term": chart_revenue_by_term(terms),
        },
    }
    out = ROOT / "docs" / "analysis-data.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written {out.relative_to(ROOT)} and {len(result['charts'])} charts in docs/img/")


if __name__ == "__main__":
    main()
