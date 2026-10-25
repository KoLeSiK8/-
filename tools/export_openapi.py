

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  


def render() -> str:
    schema = create_app().openapi()
    return yaml.safe_dump(schema, allow_unicode=True, sort_keys=False, width=100)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "openapi.yml")
    args = parser.parse_args()
    args.out.write_text(render(), encoding="utf-8")
    print(f"written {args.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
