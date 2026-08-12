from datetime import datetime, timedelta, timezone

from database.models import FitLabel, Tender
from notifier.alert_rules import AlertRulesEngine


def _tender(**overrides) -> Tender:
    values = {
        "title": "Test tender",
        "deadline": datetime.now() + timedelta(days=10),
        "value_inr": None,
        "fit_classification": FitLabel.LOW_FIT,
        "product_categories": [],
    }
    values.update(overrides)
    return Tender(**values)


def test_expired_high_value_tender_does_not_alert():
    tender = _tender(
        deadline=datetime.now() - timedelta(days=1),
        value_inr=AlertRulesEngine.HIGH_VALUE_THRESHOLD + 1,
        fit_classification=FitLabel.STRONG_FIT,
        product_categories=["Video Surveillance"],
    )

    assert AlertRulesEngine.evaluate(tender) == (False, None)


def test_future_high_value_core_category_alerts():
    tender = _tender(
        value_inr=AlertRulesEngine.HIGH_VALUE_THRESHOLD,
        product_categories=["Video Surveillance"],
    )

    should_alert, reason = AlertRulesEngine.evaluate(tender)

    assert should_alert is True
    assert "High Value" in reason


def test_high_value_low_fit_without_core_category_does_not_alert():
    tender = _tender(
        value_inr=AlertRulesEngine.HIGH_VALUE_THRESHOLD + 1,
        fit_classification=FitLabel.LOW_FIT,
        product_categories=["Office Supplies"],
    )

    assert AlertRulesEngine.evaluate(tender) == (False, None)


def test_expired_timezone_aware_deadline_does_not_alert():
    # Postgres columns are TIMESTAMP WITH TIME ZONE, so any Tender rebuilt from
    # a DB row carries an aware deadline — comparing it to a naive now() raises.
    tender = _tender(
        deadline=datetime.now(timezone.utc) - timedelta(days=1),
        value_inr=AlertRulesEngine.HIGH_VALUE_THRESHOLD + 1,
        fit_classification=FitLabel.STRONG_FIT,
        product_categories=["Video Surveillance"],
    )

    assert AlertRulesEngine.evaluate(tender) == (False, None)


def test_future_timezone_aware_deadline_still_alerts():
    tender = _tender(
        deadline=datetime.now(timezone.utc) + timedelta(days=10),
        value_inr=AlertRulesEngine.HIGH_VALUE_THRESHOLD,
        product_categories=["Video Surveillance"],
    )

    should_alert, _ = AlertRulesEngine.evaluate(tender)

    assert should_alert is True


def test_short_deadline_relevant_fit_still_alerts():
    tender = _tender(
        deadline=datetime.now() + timedelta(days=2),
        fit_classification=FitLabel.POTENTIAL_FIT,
    )

    should_alert, reason = AlertRulesEngine.evaluate(tender)

    assert should_alert is True
    assert "Short Deadline" in reason
