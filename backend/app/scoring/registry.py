from dataclasses import dataclass
from typing import ClassVar

from .context import ScoringContext


@dataclass(frozen=True)
class FeatureResult:
    applicable: bool
    value: float = 0.0
    explanation: str = ""


class Feature:
    key: ClassVar[str]
    title: ClassVar[str]
    scope: ClassVar[str]
    default_weight: ClassVar[float]

    def compute(self, ctx: ScoringContext) -> FeatureResult:
        raise NotImplementedError


FEATURES: dict[str, type[Feature]] = {}


def register_feature(feature: type[Feature]) -> type[Feature]:
    if feature.key in FEATURES:
        raise ValueError(f"Feature already registered: {feature.key}")
    FEATURES[feature.key] = feature
    return feature


def load_features() -> None:
    from .features import (  # noqa: F401
        autoprolong_off_near_expiry,
        billing_anomaly,
        bonus_dependency,
        expiry_proximity,
        funds_deficit,
        prolong_wait_state,
        suspended_paying,
        unperformed_tx_share,
        withdraw_leak,
    )