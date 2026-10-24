import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


AS_OF = datetime(2026, 10, 24, tzinfo=timezone.utc)
PAYMENT_TERMS = ("hour", "week", "month", "quarter_year", "half_year", "year")


def generate_demo(accounts: int = 200, seed: int = 42) -> dict[str, Any]:
    if accounts < 5:
        raise ValueError("accounts must be at least 5 to represent every customer state")

    rng = random.Random(seed)
    states = ["low", "medium", "high", "churned", "no_data"]
    roles = [states[index % len(states)] for index in range(accounts)]
    rng.shuffle(roles)
    data: dict[str, Any] = {
        "capturedAt": AS_OF.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "accounts": [],
        "services": [],
        "transactions": [],
    }
    service_id = 1
    transaction_id = 1

    for account_index, role in enumerate(roles, start=1):
        account_id = account_index
        if role == "high":
            balance, withdraw, bonus, bonus_state = 800, 100, 0, "locked"
        elif role == "medium":
            balance, withdraw, bonus, bonus_state = 5000, 1000, 25000, "locked"
        elif role == "low":
            balance, withdraw, bonus, bonus_state = 250000, 25000, 10000, "unlocked"
        else:
            balance = rng.randint(1000, 100000)
            withdraw = rng.randint(0, balance)
            bonus = rng.randint(0, 5000)
            bonus_state = rng.choice(("locked", "unlocked"))

        data["accounts"].append(
            {
                "id": account_id,
                "email": f"demo-{account_id:04d}@example.test",
                "balance": balance,
                "withdrawBalance": withdraw,
                "totalReplenished": (
                    rng.randint(350000, 500000)
                    if role == "churned"
                    else rng.randint(10000, 500000)
                ),
                "bonusBalance": bonus,
                "bonusState": bonus_state,
            }
        )

        if role == "no_data":
            continue

        for service_index in range(3):
            if role == "churned":
                service_status = "deleted" if service_index != 1 else "blocked"
                term = rng.choice(PAYMENT_TERMS)
                days_until_expiry = -rng.randint(10, 180)
                auto_prolong = bool(service_index % 2)
                price = rng.randint(500, 20000)
            elif service_index == 2:
                service_status = "deleted"
                term = "month"
                days_until_expiry = -30
                auto_prolong = False
                price = rng.randint(500, 20000)
            elif service_index == 1:
                term = "month"
                auto_prolong = True
                if role == "low" and account_id % 10 == 0:
                    service_status = "prolong_wait"
                    days_until_expiry = -1
                    price = 9000
                else:
                    service_status = "suspended"
                    days_until_expiry = 20 if role == "medium" else 120
                    price = 9000 if role == "medium" else 12000
            else:
                service_status = "active"
                if role == "high":
                    term = "hour"
                    days_until_expiry = 1
                    auto_prolong = False
                    price = 1200
                elif role == "medium":
                    term = "month"
                    days_until_expiry = 6
                    auto_prolong = False
                    price = 30000
                else:
                    term = "month"
                    days_until_expiry = 120
                    auto_prolong = True
                    price = 12000

            expires_at = AS_OF + timedelta(days=days_until_expiry)
            created_at = min(
                AS_OF - timedelta(days=120),
                expires_at - timedelta(days=1),
            )
            current_service_id = service_id
            data["services"].append(
                {
                    "id": current_service_id,
                    "name": f"demo-service-{current_service_id:05d}",
                    "ownerId": account_id,
                    "paymentTerm": term,
                    "autoProlong": auto_prolong,
                    "createdAt": created_at.isoformat(timespec="milliseconds").replace(
                        "+00:00", "Z"
                    ),
                    "expiresAt": expires_at.isoformat(timespec="milliseconds").replace(
                        "+00:00", "Z"
                    ),
                    "status": service_status,
                    "price": price,
                }
            )

            transaction_created = AS_OF - timedelta(minutes=30)
            data["transactions"].extend(
                [
                    {
                        "id": transaction_id,
                        "amount": min(price, 1000),
                        "status": "performed",
                        "performedAt": (transaction_created + timedelta(minutes=5))
                        .isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z"),
                        "createdAt": transaction_created.isoformat(timespec="milliseconds").replace(
                            "+00:00", "Z"
                        ),
                        "type": "order",
                        "serviceId": current_service_id,
                    },
                    {
                        "id": transaction_id + 1,
                        "amount": min(price, 1000),
                        "status": "not_performed",
                        "performedAt": None,
                        "createdAt": transaction_created.isoformat(timespec="milliseconds").replace(
                            "+00:00", "Z"
                        ),
                        "type": "prolong",
                        "serviceId": current_service_id,
                    },
                ]
            )
            service_id += 1
            transaction_id += 2

    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic churn demo data.")
    parser.add_argument("--accounts", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data/demo.json"))
    args = parser.parse_args()

    output = args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(generate_demo(args.accounts, args.seed), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote demo snapshot to {output}")


if __name__ == "__main__":
    main()