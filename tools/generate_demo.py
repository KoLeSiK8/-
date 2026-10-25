

import argparse
import copy
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

AS_OF = datetime(2026, 10, 24, tzinfo=timezone.utc)
STEP2_AS_OF = AS_OF + timedelta(days=1)
PERIOD_DAYS = {
    "hour": 1 / 24,
    "week": 7,
    "month": 30,
    "quarter_year": 91,
    "half_year": 182,
    "year": 365,
}

PRICE_RANGES = {
    "hour": (40, 400),
    "week": (300, 4000),
    "month": (900, 30000),
    "quarter_year": (2500, 80000),
    "half_year": (5000, 150000),
    "year": (9000, 280000),
}
SEGMENTS = {

    "healthy": 0.38,
    "watch": 0.24,
    "risky": 0.18,
    "churned": 0.12,
    "empty": 0.08,
}


def iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Builder:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.data: dict[str, Any] = {
            "capturedAt": iso(AS_OF),
            "accounts": [],
            "services": [],
            "transactions": [],
        }
        self.next_service = 1
        self.next_transaction = 1

    def price(self, term: str) -> int:
        low, high = PRICE_RANGES[term]
        return int(round(self.rng.uniform(low, high) / 10) * 10)

    def account(self, account_id: int, balance: int, *, replenished: int | None = None) -> dict:
        rng = self.rng
        bonus = rng.choice([0, 0, 0, rng.randint(500, 40000)])
        account = {
            "id": account_id,
            "email": f"demo-{account_id:04d}@example.test",
            "balance": balance,
            "withdrawBalance": int(balance * rng.choice([0, 0, 0.05, 0.1, 0.3, 0.8])),
            "totalReplenished": replenished
            if replenished is not None
            else balance + rng.randint(5000, 600000),
            "bonusBalance": bonus,
            "bonusState": rng.choice(["locked", "unlocked"]) if bonus else "locked",
        }
        self.data["accounts"].append(account)
        return account

    def service(
        self,
        owner_id: int,
        *,
        term: str,
        status: str,
        days_left: float,
        auto_prolong: bool,
        price: int | None = None,
        failed_share: float = 0.1,
    ) -> dict:
        rng = self.rng
        expires_at = AS_OF + timedelta(days=days_left)
        age_days = rng.uniform(30, 540)
        created_at = min(AS_OF - timedelta(days=age_days), expires_at - timedelta(hours=1))
        service_id = self.next_service
        self.next_service += 1
        service = {
            "id": service_id,
            "name": f"demo-service-{service_id:05d}",
            "ownerId": owner_id,
            "paymentTerm": term,
            "autoProlong": auto_prolong,
            "createdAt": iso(created_at),
            "expiresAt": iso(expires_at),
            "status": status,
            "price": price if price is not None else self.price(term),
        }
        self.data["services"].append(service)
        self._transactions(service, created_at, failed_share)
        return service

    def _transactions(self, service: dict, created_at: datetime, failed_share: float) -> None:
        rng = self.rng
        latest = min(AS_OF, parse(service["expiresAt"])) - timedelta(minutes=5)
        count = rng.randint(1, 4)
        for index in range(count):
            span = max((latest - created_at).total_seconds(), 60)
            moment = created_at + timedelta(seconds=span * (index + rng.random()) / count)
            performed = rng.random() >= failed_share
            amount = min(service["price"], 1000) if service["price"] else 0
            self.data["transactions"].append(
                {
                    "id": self.next_transaction,
                    "amount": amount,
                    "status": "performed" if performed else "not_performed",
                    "performedAt": iso(moment + timedelta(minutes=rng.randint(1, 30)))
                    if performed
                    else None,
                    "createdAt": iso(moment),
                    "type": "order" if index == 0 else "prolong",
                    "serviceId": service["id"],
                }
            )
            self.next_transaction += 1

    def old_deleted(self, owner_id: int, *, status: str = "deleted") -> dict:

        rng = self.rng
        return self.service(
            owner_id,
            term=rng.choice(["week", "month", "month", "quarter_year"]),
            status=status,
            days_left=-rng.uniform(6, 130),
            auto_prolong=False,
            failed_share=0.4,
        )


def _segments(accounts: int, rng: random.Random) -> list[str]:
    roles: list[str] = []
    for name, share in SEGMENTS.items():
        roles.extend([name] * max(1, round(accounts * share)))
    roles = roles[:accounts]
    while len(roles) < accounts:
        roles.append("healthy")
    rng.shuffle(roles)
    return roles


def generate_demo(accounts: int = 200, seed: int = 42) -> dict[str, Any]:
    if accounts < 10:
        raise ValueError("accounts must be at least 10 to represent every customer state")
    rng = random.Random(seed)
    b = Builder(rng)

    for account_id, segment in enumerate(_segments(accounts, rng), start=1):
        if segment == "empty":
            b.account(account_id, rng.randint(0, 20000))
            continue

        if segment == "churned":
            b.account(account_id, rng.randint(0, 3000), replenished=rng.randint(350000, 900000))
            for index in range(rng.randint(1, 4)):
                b.old_deleted(account_id, status="blocked" if index == 1 else "deleted")
            continue

        if segment == "healthy":
            account = b.account(account_id, rng.randint(60000, 600000))
            for _ in range(rng.randint(1, 4)):
                term = rng.choice(["month", "month", "quarter_year", "half_year", "year", "week"])
                b.service(
                    account_id,
                    term=term,
                    status="active",
                    days_left=rng.uniform(8, min(300, PERIOD_DAYS[term] * 1.0 + 8)),
                    auto_prolong=rng.random() < 0.85,
                    failed_share=0.05,
                )
            if account_id % 9 == 0:

                b.service(
                    account_id,
                    term="month",
                    status="prolong_wait",
                    days_left=-rng.uniform(0.2, 3),
                    auto_prolong=True,
                    price=min(account["balance"] // 3, 25000),
                )
            if rng.random() < 0.3:
                b.old_deleted(account_id)
            continue

        if segment == "watch":
            b.account(account_id, rng.randint(3000, 40000))
            term = rng.choice(["month", "month", "week", "quarter_year"])
            b.service(
                account_id,
                term=term,
                status=rng.choice(["active", "active", "suspended"]),
                days_left=rng.uniform(1.5, 9),
                auto_prolong=rng.random() < 0.35,
                failed_share=0.25,
            )
            for _ in range(rng.randint(0, 2)):
                b.service(
                    account_id,
                    term=rng.choice(["month", "quarter_year"]),
                    status="active",
                    days_left=rng.uniform(10, 90),
                    auto_prolong=True,
                    failed_share=0.15,
                )
            if rng.random() < 0.4:
                b.old_deleted(account_id)
            continue


        b.account(account_id, rng.randint(0, 4000))
        pattern = rng.choice(["hourly", "prolong_wait", "expiring", "prolong_wait"])
        if pattern == "hourly":

            b.service(
                account_id,
                term="hour",
                status="active",
                days_left=rng.uniform(0.1, 2.5),
                auto_prolong=False,
                price=rng.randint(60, 400),
                failed_share=0.5,
            )
        elif pattern == "prolong_wait":
            b.service(
                account_id,
                term=rng.choice(["month", "quarter_year"]),
                status="prolong_wait",
                days_left=-rng.uniform(0.3, 4.8),
                auto_prolong=rng.random() < 0.5,
                price=rng.randint(6000, 40000),
                failed_share=0.6,
            )
        else:
            b.service(
                account_id,
                term="month",
                status="active",
                days_left=rng.uniform(0.2, 4),
                auto_prolong=False,
                price=rng.randint(8000, 30000),
                failed_share=0.5,
            )
        for _ in range(rng.randint(0, 2)):
            b.service(
                account_id,
                term="month",
                status=rng.choice(["active", "suspended"]),
                days_left=rng.uniform(3, 40),
                auto_prolong=rng.random() < 0.5,
                failed_share=0.4,
            )
        if rng.random() < 0.6:
            b.old_deleted(account_id)


    pending = [s for s in b.data["services"] if s["status"] == "prolong_wait" and not s["autoProlong"]]
    for service in pending[:2]:
        service["expiresAt"] = iso(AS_OF - timedelta(days=rng.uniform(6, 9)))  
    expired = [s for s in b.data["services"] if s["status"] == "active" and s["paymentTerm"] == "month"]
    for service in expired[3:5]:
        service["expiresAt"] = iso(AS_OF - timedelta(days=rng.uniform(0.5, 2)))  

    return b.data


def generate_step2(base: dict[str, Any], seed: int = 42) -> dict[str, Any]:

    rng = random.Random(seed + 1)
    data = copy.deepcopy(base)
    data["capturedAt"] = iso(STEP2_AS_OF)
    accounts = {account["id"]: account for account in data["accounts"]}
    next_transaction = max((tx["id"] for tx in data["transactions"]), default=0) + 1

    def available(account: dict) -> int:
        bonus = account["bonusBalance"] if account["bonusState"] == "unlocked" else 0
        return account["balance"] + bonus

    rescued_owners: set[int] = set()
    for service in data["services"]:
        account = accounts[service["ownerId"]]
        expires_at = parse(service["expiresAt"])
        if service["status"] == "prolong_wait" and available(account) < service["price"]:
            if rng.random() < 0.5 or service["ownerId"] in rescued_owners:

                rescued_owners.add(service["ownerId"])
                top_up = service["price"] * 3
                account["balance"] += top_up - service["price"]
                account["totalReplenished"] += top_up
                service["status"] = "active"
                service["autoProlong"] = True
                service["expiresAt"] = iso(
                    expires_at + timedelta(days=PERIOD_DAYS[service["paymentTerm"]])
                )
                data["transactions"].append(
                    {
                        "id": next_transaction,
                        "amount": min(service["price"], 1000),
                        "status": "performed",
                        "performedAt": iso(STEP2_AS_OF - timedelta(hours=2)),
                        "createdAt": iso(STEP2_AS_OF - timedelta(hours=2, minutes=5)),
                        "type": "prolong",
                        "serviceId": service["id"],
                    }
                )
                next_transaction += 1
            else:
                service["status"] = "deleted"
        elif (
            service["status"] == "active"
            and service["paymentTerm"] == "hour"
            and available(account) < service["price"] * 24
        ):
            service["status"] = "blocked"
        elif (
            service["status"] in {"active", "suspended"}
            and not service["autoProlong"]
            and expires_at <= STEP2_AS_OF
        ):
            service["status"] = "prolong_wait"


    for service in data["services"]:
        if service["ownerId"] in rescued_owners and service["status"] in {"active", "suspended"}:
            service["autoProlong"] = True
    for owner_id in rescued_owners:
        account = accounts[owner_id]
        account["withdrawBalance"] = min(account["withdrawBalance"], account["balance"])
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic churn demo data.")
    parser.add_argument("--accounts", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data/demo.json"))
    parser.add_argument("--step2-out", type=Path, default=Path("data/demo-step2.json"))
    args = parser.parse_args()

    base = generate_demo(args.accounts, args.seed)
    for path, payload in ((args.out, base), (args.step2_out, generate_step2(base, args.seed))):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
