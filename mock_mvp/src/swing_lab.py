"""Mock-only Swing Lab trade proposal helpers.

This module creates explicit buy/sell/reduce/exit/no-trade proposal cards for
Guardian Swing Lab. It does not place orders, connect to brokers, fetch market
data, or read private portfolio data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


ALLOWED_ACTIONS = {
    "buy_proposal": "買い提案",
    "sell_proposal": "売り提案",
    "reduce_proposal": "縮小提案",
    "exit_proposal": "撤退提案",
    "no_trade": "見送り",
}

ALLOWED_RISK_CLASSES = {"middle_risk", "high_risk", "experimental"}
ALLOWED_INSTRUMENT_TYPES = {
    "cash_equity",
    "etf",
    "leveraged_etf",
    "margin_short",
    "option",
    "pair_trade",
}
ALLOWED_APPROVAL = {"not_requested", "pending", "approved", "rejected"}
HIGH_GATE_INSTRUMENTS = {"margin_short", "option", "pair_trade"}
SELL_SIDE_ACTIONS = {"sell_proposal", "reduce_proposal", "exit_proposal"}

REQUIRED_PROPOSAL_FIELDS = (
    "action",
    "risk_class",
    "instrument_type",
    "signal_basis",
    "regime",
    "counter_evidence",
    "stop_rule",
    "max_entry_amount",
    "max_loss_amount",
    "data_freshness",
    "backtest_status",
    "human_approval_status",
    "review_deadline",
)


@dataclass
class SafetyResult:
    """Validation result for one Swing Lab proposal."""

    errors: list[str]
    warnings: list[str]

    @property
    def status(self) -> str:
        if self.errors:
            return "stop_required"
        if self.warnings:
            return "review_needed"
        return "ok"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def classify_regime(signal_inputs: dict[str, Any]) -> dict[str, Any]:
    """Classify a lightweight market regime from mock signal inputs."""
    trend_strength = _number(signal_inputs.get("trend_strength"))
    range_score = _number(signal_inputs.get("range_score"))
    volatility_percentile = _number(signal_inputs.get("volatility_percentile"))
    correlation_stress = _number(signal_inputs.get("correlation_stress"))

    if volatility_percentile >= 0.85 or correlation_stress >= 0.80:
        label = "high_vol_stress"
        confidence = max(volatility_percentile, correlation_stress)
    elif trend_strength >= 0.60:
        label = "trend"
        confidence = trend_strength
    elif range_score >= 0.60:
        label = "range"
        confidence = range_score
    else:
        label = "neutral"
        confidence = max(trend_strength, range_score, 0.50)

    return {
        "label": label,
        "confidence": round(float(confidence), 3),
        "trend_strength": trend_strength,
        "range_score": range_score,
        "volatility_percentile": volatility_percentile,
        "correlation_stress": correlation_stress,
    }


def generate_signal(signal_inputs: dict[str, Any], regime: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate a mock Swing Lab action from transparent signal inputs."""
    regime = regime or classify_regime(signal_inputs)
    momentum_score = _number(signal_inputs.get("momentum_score"))
    mean_reversion_score = _number(signal_inputs.get("mean_reversion_score"))
    risk_score = _number(signal_inputs.get("risk_score"))
    stop_triggered = bool(signal_inputs.get("stop_triggered"))
    profit_protection_triggered = bool(signal_inputs.get("profit_protection_triggered"))
    overheat_score = _number(signal_inputs.get("overheat_score"))

    basis: list[str] = []
    action = "no_trade"

    if stop_triggered:
        action = "exit_proposal"
        basis.append("risk: stop_triggered")
    elif risk_score >= 0.80:
        action = "reduce_proposal"
        basis.append(f"risk: risk_score={risk_score:.2f}")
    elif profit_protection_triggered or overheat_score >= 0.75:
        action = "sell_proposal"
        basis.append("risk: profit_protection_or_overheat")
    elif regime["label"] == "trend" and momentum_score >= 0.65:
        action = "buy_proposal"
        basis.append(f"momentum: momentum_score={momentum_score:.2f}")
        basis.append("regime: trend")
    elif regime["label"] == "range" and mean_reversion_score >= 0.65:
        action = "buy_proposal"
        basis.append(f"mean_reversion: mean_reversion_score={mean_reversion_score:.2f}")
        basis.append("regime: range")
    else:
        basis.append("risk: no clear experimental edge")

    return {
        "action": action,
        "action_label": ALLOWED_ACTIONS[action],
        "signal_basis": basis,
    }


def calculate_position_size(
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    max_entry_pct: float | None = None,
) -> dict[str, Any]:
    """Calculate max units from risk amount and stop distance."""
    capital = _number(capital)
    risk_pct = _number(risk_pct)
    entry_price = _number(entry_price)
    stop_price = _number(stop_price)
    errors: list[str] = []

    if capital <= 0:
        errors.append("capital must be positive")
    if risk_pct <= 0:
        errors.append("risk_pct must be positive")
    if entry_price <= 0:
        errors.append("entry_price must be positive")
    per_unit_risk = abs(entry_price - stop_price)
    if per_unit_risk <= 0:
        errors.append("stop_price must differ from entry_price")

    if errors:
        return {
            "units": 0,
            "max_entry_amount": 0,
            "max_loss_amount": 0,
            "per_unit_risk": per_unit_risk,
            "errors": errors,
        }

    risk_amount = capital * risk_pct
    units_by_risk = int(risk_amount // per_unit_risk)
    if max_entry_pct is not None and max_entry_pct > 0:
        max_entry_amount = capital * max_entry_pct
        units_by_entry = int(max_entry_amount // entry_price)
        units = max(0, min(units_by_risk, units_by_entry))
    else:
        units = max(0, units_by_risk)
        max_entry_amount = units * entry_price

    return {
        "units": units,
        "max_entry_amount": round(units * entry_price, 2),
        "max_loss_amount": round(units * per_unit_risk, 2),
        "per_unit_risk": round(per_unit_risk, 4),
        "errors": [],
    }


def validate_backtest_safety(backtest_status: dict[str, Any]) -> SafetyResult:
    """Validate core backtest safety requirements."""
    errors: list[str] = []
    warnings: list[str] = []

    if int(_number(backtest_status.get("signal_lag_periods"), -1)) < 1:
        errors.append("signal lag must be at least 1 period")
    if backtest_status.get("transaction_cost_included") is not True:
        errors.append("transaction cost must be included")
    if backtest_status.get("slippage_included") is not True:
        errors.append("slippage must be included")
    if backtest_status.get("max_drawdown") in (None, ""):
        errors.append("max_drawdown is required")
    if backtest_status.get("oos_tested") is not True:
        warnings.append("OOS test is not confirmed")
    if backtest_status.get("walk_forward_tested") is not True:
        warnings.append("walk-forward test is not confirmed")
    if int(_number(backtest_status.get("parameter_search_count"), 0)) > 30:
        warnings.append("parameter search count is high; overfitting review required")
    sample_size = int(_number(backtest_status.get("sample_size"), 0))
    if sample_size and sample_size < 60:
        warnings.append("backtest sample size is small")
    if backtest_status.get("test_period_start") in (None, ""):
        warnings.append("backtest period start is not documented")
    if backtest_status.get("test_period_end") in (None, ""):
        warnings.append("backtest period end is not documented")
    if backtest_status.get("benchmark_or_baseline") in (None, ""):
        warnings.append("benchmark or baseline is not documented")
    if backtest_status.get("lookahead_bias_checked") is not True:
        warnings.append("lookahead bias check is not confirmed")
    if backtest_status.get("survivorship_bias_checked") is not True:
        warnings.append("survivorship bias check is not confirmed")
    if backtest_status.get("data_source") in (None, ""):
        warnings.append("backtest data source is not documented")

    return SafetyResult(errors=errors, warnings=warnings)


def _validate_gate_controls(proposal: dict[str, Any]) -> SafetyResult:
    errors: list[str] = []
    warnings: list[str] = []
    gate = int(_number(proposal.get("gate"), 0))
    instrument_type = str(proposal.get("instrument_type", ""))

    if gate >= 3 or instrument_type == "leveraged_etf":
        if proposal.get("gap_risk_reviewed") is not True:
            warnings.append("Gate 3+ requires high-volatility and gap-risk review")
    if gate >= 4 or instrument_type in HIGH_GATE_INSTRUMENTS:
        if proposal.get("broker_rule_confirmed") is not True:
            errors.append("Gate 4+ requires broker rule confirmation")
        if proposal.get("margin_confirmed") is not True:
            errors.append("Gate 4+ requires margin confirmation")
        if proposal.get("forced_liquidation_reviewed") is not True:
            errors.append("Gate 4+ requires forced liquidation risk review")
    if gate >= 5 and proposal.get("defined_max_loss_confirmed") is not True:
        errors.append("Gate 5 requires defined maximum loss confirmation")

    return SafetyResult(errors=errors, warnings=warnings)


def validate_position_ownership(card: dict[str, Any], proposal: dict[str, Any]) -> SafetyResult:
    """Validate local holding confirmation for sell-side proposals."""
    errors: list[str] = []
    warnings: list[str] = []
    action = str(card.get("action", ""))
    if action not in SELL_SIDE_ACTIONS:
        position = proposal.get("current_position")
        if isinstance(position, dict) and position.get("status") == "held":
            warnings.append("buy-side proposal may be an add-on; confirm current holding locally")
        return SafetyResult(errors=errors, warnings=warnings)

    if proposal.get("public_watch_only") is True:
        warnings.append("sell-side proposal requires local holding confirmation before execution")
        return SafetyResult(errors=errors, warnings=warnings)
    if proposal.get("enforce_position_ownership") is not True:
        warnings.append("sell-side ownership confirmation is not enforced in this run")
        return SafetyResult(errors=errors, warnings=warnings)

    position = proposal.get("current_position")
    if not isinstance(position, dict):
        errors.append("ownership confirmation required for sell-side proposal")
        return SafetyResult(errors=errors, warnings=warnings)
    quantity = _number(position.get("quantity"))
    if position.get("status") != "held" or quantity <= 0:
        errors.append("sell-side proposal requires a confirmed positive holding")
    if position.get("verified_at") in (None, ""):
        warnings.append("holding verification timestamp is not documented")
    return SafetyResult(errors=errors, warnings=warnings)


def validate_trade_proposal_card(card: dict[str, Any]) -> SafetyResult:
    """Validate a completed Swing Lab proposal card."""
    errors: list[str] = []
    warnings: list[str] = []

    for field in REQUIRED_PROPOSAL_FIELDS:
        if card.get(field) in (None, "", [], {}):
            errors.append(f"{field} is required")

    if card.get("action") not in ALLOWED_ACTIONS:
        errors.append("unsupported action")
    if card.get("risk_class") not in ALLOWED_RISK_CLASSES:
        errors.append("unsupported risk_class")
    if card.get("instrument_type") not in ALLOWED_INSTRUMENT_TYPES:
        errors.append("unsupported instrument_type")
    if card.get("human_approval_status") not in ALLOWED_APPROVAL:
        errors.append("unsupported human_approval_status")
    if _number(card.get("max_loss_amount")) <= 0 and card.get("action") != "no_trade":
        if card.get("action") in SELL_SIDE_ACTIONS and card.get("public_watch_only") is True:
            warnings.append("sell-side max loss requires local holding confirmation")
        else:
            errors.append("max_loss_amount must be positive for active proposals")
    if card.get("human_approval_status") != "approved":
        warnings.append("human approval is not approved yet")

    backtest_result = validate_backtest_safety(dict(card.get("backtest_status") or {}))
    errors.extend(backtest_result.errors)
    warnings.extend(backtest_result.warnings)

    return SafetyResult(errors=errors, warnings=warnings)


def build_trade_proposal_card(proposal: dict[str, Any]) -> dict[str, Any]:
    """Build and validate one mock Swing Lab proposal card."""
    regime = classify_regime(dict(proposal.get("signal_inputs") or {}))
    signal = generate_signal(dict(proposal.get("signal_inputs") or {}), regime)
    sizing = calculate_position_size(
        capital=_number(proposal.get("capital")),
        risk_pct=_number(proposal.get("risk_pct")),
        entry_price=_number(proposal.get("entry_price")),
        stop_price=_number(proposal.get("stop_price")),
        max_entry_pct=proposal.get("max_entry_pct"),
    )
    if signal["action"] == "no_trade":
        sizing = {
            **sizing,
            "units": 0,
            "max_entry_amount": 0,
            "max_loss_amount": 0,
            "errors": [],
        }

    review_deadline = proposal.get("review_deadline")
    if not review_deadline:
        review_deadline = (date.today() + timedelta(days=7)).isoformat()

    card = {
        "proposal_id": proposal.get("proposal_id", "SWING_MOCK_UNKNOWN"),
        "subject_label": proposal.get("subject_label", "MOCK_SWING_TARGET"),
        "ticker_or_code": proposal.get("ticker_or_code", ""),
        "universe_id": proposal.get("universe_id", ""),
        "rakuten_tradeable_status": proposal.get("rakuten_tradeable_status", ""),
        "market_as_of": proposal.get("market_as_of", ""),
        "price_source": proposal.get("price_source", ""),
        "public_watch_only": bool(proposal.get("public_watch_only", False)),
        "action": signal["action"],
        "action_label": signal["action_label"],
        "risk_class": proposal.get("risk_class", "experimental"),
        "instrument_type": proposal.get("instrument_type", "cash_equity"),
        "gate": int(_number(proposal.get("gate"), 0)),
        "currency": proposal.get("currency", "MOCK JPY"),
        "reference_price": proposal.get("reference_price"),
        "source_summary": proposal.get("source_summary", ""),
        "web_sources": proposal.get("web_sources", []),
        "signal_basis": signal["signal_basis"],
        "regime": regime,
        "counter_evidence": proposal.get("counter_evidence", ""),
        "stop_rule": proposal.get("stop_rule", ""),
        "max_entry_amount": sizing["max_entry_amount"],
        "max_loss_amount": sizing["max_loss_amount"],
        "position_units": sizing["units"],
        "data_freshness": proposal.get("data_freshness", ""),
        "backtest_status": proposal.get("backtest_status", {}),
        "human_approval_status": proposal.get("human_approval_status", "pending"),
        "review_deadline": review_deadline,
        "auto_order": False,
    }

    errors = list(sizing["errors"]) + [str(item) for item in proposal.get("additional_errors", [])]
    warnings: list[str] = [str(item) for item in proposal.get("additional_warnings", [])]
    gate_result = _validate_gate_controls(proposal)
    errors.extend(gate_result.errors)
    warnings.extend(gate_result.warnings)
    ownership_result = validate_position_ownership(card, proposal)
    errors.extend(ownership_result.errors)
    warnings.extend(ownership_result.warnings)
    card_result = validate_trade_proposal_card(card)
    errors.extend(card_result.errors)
    warnings.extend(card_result.warnings)

    card["errors"] = errors
    card["warnings"] = warnings
    card["status"] = SafetyResult(errors, warnings).status
    return card


def build_cards(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build cards for a list of mock proposals."""
    return [build_trade_proposal_card(proposal) for proposal in proposals]


if __name__ == "__main__":
    sample = {
        "proposal_id": "SWING_MOCK_DEMO",
        "capital": 1000000,
        "risk_pct": 0.005,
        "entry_price": 1000,
        "stop_price": 950,
        "max_entry_pct": 0.10,
        "counter_evidence": "momentum turns negative or volatility stress rises",
        "stop_rule": "exit if price closes below stop or after 4 weeks without progress",
        "data_freshness": "weekly close mock data as of 2026-05-21",
        "backtest_status": {
            "signal_lag_periods": 1,
            "transaction_cost_included": True,
            "slippage_included": True,
            "max_drawdown": -0.08,
            "oos_tested": True,
            "walk_forward_tested": True,
            "parameter_search_count": 8,
        },
        "signal_inputs": {"trend_strength": 0.72, "momentum_score": 0.81, "risk_score": 0.30},
    }
    print(build_trade_proposal_card(sample))
