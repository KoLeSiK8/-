import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest

from app.ingestion.schemas import SnapshotInput
from app.ingestion.quality import snapshot_as_of
from app.scoring.context import ScoringContext
from app.scoring.engine import compute_scoring, score_service
from app.scoring.money import compute_money, service_value_cents
from app.scoring.registry import FEATURES
from app.scoring.settings import ScoringSettings


OFFICIAL_DATA = Path(__file__).resolve().parents[3] / "data" / "official.json"
DEMO_DATA = Path(__file__).resolve().parents[3] / "data" / "demo.json"
DEMO_STEP2_DATA = Path(__file__).resolve().parents[3] / "data" / "demo-step2.json"


@pytest.fixture
def snapshot() -> SnapshotInput:
    return SnapshotInput.model_validate(
        json.loads(OFFICIAL_DATA.read_text(encoding="utf-8"))
    )


@pytest.fixture
def settings() -> ScoringSettings:
    return ScoringSettings()


def context_for(
    snapshot: SnapshotInput, service_id: int, as_of=None
) -> ScoringContext:
    service = next(service for service in snapshot.services if service.id == service_id)
    account = next(account for account in snapshot.accounts if account.id == service.owner_id)
    services = [item for item in snapshot.services if item.owner_id == account.id]
    return ScoringContext(
        account=account,
        service=service,
        services=services,
        transactions=snapshot.transactions,
        as_of=as_of or snapshot_as_of(snapshot),
        horizon_days=7,
        suspended_value=0.4,
    )


def feature_value(snapshot: SnapshotInput, service_id: int, key: str, as_of=None) -> float:
    feature = FEATURES[key]()
    result = feature.compute(context_for(snapshot, service_id, as_of))
    assert result.applicable
    return result.value


def test_expiry_proximity_uses_clamped_horizon(snapshot: SnapshotInput) -> None:
    service = next(item for item in snapshot.services if item.id == 1)
    as_of = service.expires_at - timedelta(days=3.5)

    assert feature_value(snapshot, 1, "expiry_proximity", as_of) == pytest.approx(0.5)


def test_autoprolong_off_near_expiry(snapshot: SnapshotInput) -> None:
    service = next(item for item in snapshot.services if item.id == 1)
    as_of = service.expires_at - timedelta(days=3)

    assert feature_value(snapshot, 1, "autoprolong_off_near_expiry", as_of) == 1


def test_funds_deficit_is_high_for_accounts_five_and_nine(
    snapshot: SnapshotInput,
) -> None:
    assert feature_value(snapshot, 5, "funds_deficit") > 0.5
    assert feature_value(snapshot, 9, "funds_deficit") > 0.3


def test_prolong_wait_value_reaches_one_after_five_days(snapshot: SnapshotInput) -> None:
    assert feature_value(snapshot, 5, "prolong_wait_state") == 1


def test_suspended_service_uses_configured_value(snapshot: SnapshotInput) -> None:
    assert feature_value(snapshot, 9, "suspended_paying") == 0.4


def test_withdraw_leak_uses_withdrawable_share(snapshot: SnapshotInput) -> None:
    account = next(item for item in snapshot.accounts if item.id == 1)
    assert feature_value(snapshot, 1, "withdraw_leak") == pytest.approx(
        account.withdraw_balance / account.balance
    )


def test_bonus_dependency_uses_unlocked_bonus_share(snapshot: SnapshotInput) -> None:
    account = next(item for item in snapshot.accounts if item.id == 2)
    assert feature_value(snapshot, 2, "bonus_dependency") == pytest.approx(
        account.bonus_balance / (account.balance + account.bonus_balance)
    )


def test_unperformed_transaction_share(snapshot: SnapshotInput) -> None:
    ctx = context_for(snapshot, 1)
    transactions = ctx.account_transactions
    expected = sum(tx.status == "not_performed" for tx in transactions) / len(transactions)

    assert feature_value(snapshot, 1, "unperformed_tx_share") == expected


def test_billing_anomaly_requires_funded_autoprolong(snapshot: SnapshotInput) -> None:
    payload = json.loads(OFFICIAL_DATA.read_text(encoding="utf-8"))
    payload["services"][4]["autoProlong"] = True
    changed_snapshot = SnapshotInput.model_validate(payload)

    assert feature_value(changed_snapshot, 5, "billing_anomaly") == 1


def test_official_snapshot_golden_scores_and_special_states(
    snapshot: SnapshotInput, settings: ScoringSettings
) -> None:
    result = compute_scoring(snapshot, settings)
    customers = {item.customer_id: item for item in result.customers}

    assert result.as_of.isoformat() == "2026-10-19T14:35:53+00:00"
    assert customers[1].score == pytest.approx(47.86, abs=0.01)
    assert customers[5].score == pytest.approx(80.08, abs=0.01)
    assert customers[5].level == "high"
    assert customers[6].score is not None
    assert {customer_id for customer_id in (2, 3, 7, 8) if customers[customer_id].level == "churned"} == {
        2,
        3,
        7,
        8,
    }
    assert customers[1].reasons


def test_customer_without_services_is_no_data(
    snapshot: SnapshotInput, settings: ScoringSettings
) -> None:
    remaining_services = [service for service in snapshot.services if service.owner_id != 1]
    remaining_ids = {service.id for service in remaining_services}
    reduced = snapshot.model_copy(
        update={
            "services": remaining_services,
            "transactions": [
                tx for tx in snapshot.transactions if tx.service_id in remaining_ids
            ],
        }
    )

    result = compute_scoring(reduced, settings)
    customer = next(item for item in result.customers if item.customer_id == 1)

    assert customer.level == "no_data"
    assert customer.score is None


def test_money_formulas_match_official_golden_values(
    snapshot: SnapshotInput, settings: ScoringSettings
) -> None:
    scoring = compute_scoring(snapshot, settings)
    _, summary = compute_money(snapshot.accounts, snapshot.services, scoring, settings)

    assert service_value_cents(snapshot.services[0], settings) == 68_400
    assert summary.revenue_at_risk_cents == 1_155_577
    assert summary.expected_loss_cents == 510_588
    assert summary.recoverable_cents == 0
    assert summary.lost_revenue_monthly_cents == 735_386
    assert summary.hourly_share == pytest.approx(0.997527642, abs=1e-8)


def test_zero_weights_make_service_unscorable(
    snapshot: SnapshotInput, settings: ScoringSettings
) -> None:
    context = context_for(snapshot, 1)
    no_weights = settings.model_copy(update={"weights": {key: 0 for key in settings.weights}})

    assert score_service(context, no_weights).score is None


def test_demo_data_has_all_states_and_required_scenarios(
    settings: ScoringSettings,
) -> None:
    demo = SnapshotInput.model_validate(
        json.loads(DEMO_DATA.read_text(encoding="utf-8"))
    )
    result = compute_scoring(demo, settings)
    levels = Counter(customer.level for customer in result.customers)
    accounts = {account.id: account for account in demo.accounts}
    churned_ids = {
        customer.customer_id for customer in result.customers if customer.level == "churned"
    }
    funded_prolong_wait = [
        service
        for service in demo.services
        if service.status == "prolong_wait"
        and service.auto_prolong
        and accounts[service.owner_id].balance >= service.price
    ]
    statuses_by_owner: dict[int, set[str]] = {}
    for service in demo.services:
        statuses_by_owner.setdefault(service.owner_id, set()).add(service.status)

    assert all(levels[level] > 0 for level in ("low", "medium", "high", "churned", "no_data"))
    assert funded_prolong_wait
    assert all(accounts[customer_id].total_replenished >= 350000 for customer_id in churned_ids)
    assert any(len(statuses) > 1 for statuses in statuses_by_owner.values())

    assert any(
        service.payment_term == "hour"
        and service.status == "active"
        and accounts[service.owner_id].balance < service.price * 24
        for service in demo.services
    )

    scores = {round(item.score, 1) for item in result.customers if item.score is not None}
    assert len(scores) > 50


def test_demo_step2_lowers_risk_and_records_churn(settings: ScoringSettings) -> None:
    demo = SnapshotInput.model_validate(json.loads(DEMO_DATA.read_text(encoding="utf-8")))
    step2 = SnapshotInput.model_validate(json.loads(DEMO_STEP2_DATA.read_text(encoding="utf-8")))
    before = {item.customer_id: item for item in compute_scoring(demo, settings).customers}
    after = {item.customer_id: item for item in compute_scoring(step2, settings).customers}
    old_status = {service.id: service.status for service in demo.services}

    assert step2.captured_at - demo.captured_at == timedelta(days=1)
    assert [account.id for account in step2.accounts] == [account.id for account in demo.accounts]
    rescued = [
        customer_id
        for customer_id, item in before.items()
        if item.level == "high" and after[customer_id].level in {"low", "medium"}
    ]
    assert rescued, "some high-risk customers top up and their risk drops"
    assert any(
        old_status[service.id] not in {"deleted", "blocked"}
        and service.status in {"deleted", "blocked"}
        for service in step2.services
    ), "some services are lost between the snapshots"

def test_recoverable_includes_prolong_wait_in_grace_period(
    snapshot: SnapshotInput, settings: ScoringSettings
) -> None:
    as_of = snapshot_as_of(snapshot)
    services = [
        service.model_copy(update={"expires_at": as_of - timedelta(days=1)})
        if service.id == 5  
        else service
        for service in snapshot.services
    ]
    accounts = [
        account.model_copy(update={"balance": 0, "bonus_balance": 0})
        if account.id == 5
        else account
        for account in snapshot.accounts
    ]
    changed = snapshot.model_copy(update={"services": services, "accounts": accounts})
    scoring = compute_scoring(changed, settings)
    _, summary = compute_money(changed.accounts, changed.services, scoring, settings)
    service = next(item for item in services if item.id == 5)

    assert summary.recoverable_cents >= service_value_cents(service, settings)
