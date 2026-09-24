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


# --- staleness: tenders that state no deadline --------------------------------
# Without this branch, web-discovered rows with a NULL deadline lived outside
# every expiry check forever and could still fire alerts.

def test_undated_tender_past_the_staleness_window_does_not_alert():
    tender = _tender(
        deadline=None,
        created_at=datetime.now() - timedelta(days=AlertRulesEngine.STALE_DAYS + 10),
        value_inr=AlertRulesEngine.HIGH_VALUE_THRESHOLD,
        fit_classification=FitLabel.STRONG_FIT,
        product_categories=["Video Surveillance"],
    )

    assert AlertRulesEngine.is_stale(tender) is True
    assert AlertRulesEngine.evaluate(tender) == (False, None)


def test_undated_tender_inside_the_window_still_alerts():
    tender = _tender(
        deadline=None,
        created_at=datetime.now() - timedelta(days=2),
        value_inr=AlertRulesEngine.HIGH_VALUE_THRESHOLD,
        product_categories=["Video Surveillance"],
    )

    assert AlertRulesEngine.is_stale(tender) is False
    should_alert, _ = AlertRulesEngine.evaluate(tender)
    assert should_alert is True


def test_publication_date_anchors_staleness_when_created_at_is_recent():
    # The Bolangir shape: an old notice re-scraped recently. COALESCE order is
    # publication_date first — a fresh created_at must not launder it.
    tender = _tender(deadline=None, created_at=datetime.now())
    tender.publication_date = (datetime.now() - timedelta(days=60)).date()

    assert AlertRulesEngine.is_stale(tender) is True


def test_undated_tender_with_no_timestamps_at_all_counts_as_stale():
    # Nothing to age from: never alert on data we know nothing about.
    tender = _tender(deadline=None, created_at=None, scraped_at=None)

    assert AlertRulesEngine.is_stale(tender) is True


def test_expired_deadline_suppresses_even_with_a_fresh_created_at():
    tender = _tender(
        deadline=datetime.now() - timedelta(days=1),
        created_at=datetime.now(),
    )

    assert AlertRulesEngine.is_stale(tender) is True


def test_stale_window_mirrors_the_repository_constant():
    # The board filter and the alert engine must agree on "stale" or a tender
    # is hidden from the board while still being alerted on (or vice versa).
    from database.repository import STALE_DAYS

    assert AlertRulesEngine.STALE_DAYS == STALE_DAYS
