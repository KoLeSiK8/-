

import argparse
import os
import sys
import time
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("SEED_DATASET", "none")

from fastapi.testclient import TestClient  
from generate_demo import generate_demo  

from app.config import settings  
from app.db import engine  
from app.main import create_app  

READS = {
    "summary": "/api/v1/analytics/summary",
    "customers (score desc)": "/api/v1/customers?sort_by=score&order=desc&size=20",
    "search": "/api/v1/customers?q=demo-0042",
    "customer card": "/api/v1/customers/42",
    "timeline": "/api/v1/analytics/churn-timeline",
    "metrics": "/metrics",
}


def timed(call) -> float:
    start = time.perf_counter()
    response = call()
    assert response.status_code == 200, response.text[:300]
    return time.perf_counter() - start


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=int, nargs="+", default=[10000])
    args = parser.parse_args()

    with TestClient(create_app(engine)) as client:
        assert client.post(
            "/api/v1/auth/login",
            json={"login": settings.admin_login, "password": settings.admin_password},
        ).status_code == 200
        original = client.get("/api/v1/model/settings").json()["settings"]["weights"]
        for accounts in args.accounts:
            payload = generate_demo(accounts, 42)
            put = timed(lambda: client.put("/api/v1/source/snapshot", json=payload))
            patch = timed(
                lambda: client.patch(
                    "/api/v1/model/settings",
                    json={"weights": {"withdraw_leak": original["withdraw_leak"] + 1}},
                )
            )
            client.patch("/api/v1/model/settings", json={"weights": original})
            print(
                f"{accounts} клиентов, {len(payload['services'])} услуг: "
                f"PUT снимка {put:.1f} с, PATCH настроек {patch:.1f} с"
            )
            for name, url in READS.items():
                ms = median(timed(lambda: client.get(url)) for _ in range(5)) * 1000
                print(f"  {name}: {ms:.0f} мс")


if __name__ == "__main__":
    main()
