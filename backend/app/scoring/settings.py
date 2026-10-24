from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..ingestion.schemas import UtcDatetime
from .registry import FEATURES, load_features

load_features()


class RiskThresholds(BaseModel):
    low: float = Field(default=35, ge=0, le=100)
    high: float = Field(default=65, ge=0, le=100)

    @model_validator(mode="after")
    def validate_order(self) -> "RiskThresholds":
        if self.low >= self.high:
            raise ValueError("thresholds.low must be less than thresholds.high")
        return self


class ChurnCurve(BaseModel):
    k: float = Field(default=0.08, gt=0, le=10)
    midpoint: float = Field(default=60, ge=0, le=100)


class ScoringSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: dict[str, float] = Field(
        default_factory=lambda: {
            key: feature.default_weight for key, feature in FEATURES.items()
        }
    )
    horizon_days: float = Field(default=7, gt=0, le=3650)
    horizon_money_days: float = Field(default=30, gt=0, le=3650)
    thresholds: RiskThresholds = Field(default_factory=RiskThresholds)
    alpha_max_mean: float = Field(default=0.7, ge=0, le=1)
    churn_curve: ChurnCurve = Field(default_factory=ChurnCurve)
    balance_shield: float = Field(default=0.5, ge=0, le=1)
    suspended_value: float = Field(default=0.4, ge=0, le=1)
    as_of_mode: Literal["snapshot", "now", "fixed"] = "snapshot"
    as_of_fixed: UtcDatetime | None = None

    @model_validator(mode="after")
    def validate_thresholds_and_weights(self) -> "ScoringSettings":
        unknown = self.weights.keys() - FEATURES.keys()
        if unknown:
            raise ValueError(f"Unknown feature weights: {sorted(unknown)}")
        if any(not 0 <= weight <= 100 for weight in self.weights.values()):
            raise ValueError("Feature weights must be between 0 and 100")
        if self.as_of_mode == "fixed" and self.as_of_fixed is None:
            raise ValueError("as_of_fixed is required when as_of_mode is fixed")
        return self


def feature_descriptions() -> list[dict[str, str | float]]:
    return [
        {
            "key": feature.key,
            "title": feature.title,
            "description": feature.description or feature.title,
            "scope": feature.scope,
            "default_weight": feature.default_weight,
        }
        for feature in FEATURES.values()
    ]