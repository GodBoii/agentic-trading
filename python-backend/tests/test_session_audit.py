from pipeline.research.session_audit import classify_protection, timestamp, weighted


def order(stop="CANCELLED", target="TRADED", filled=5):
    return {"filledQty": filled, "legDetails": [
        {"legName": "STOP_LOSS_LEG", "orderStatus": stop},
        {"legName": "TARGET_LEG", "orderStatus": target},
    ]}


def test_cancelled_stop_after_target_is_normal_exit():
    status, _ = classify_protection(order(), [{"orderStatus": "TRADED"}], 0)
    assert status == "target_exit"


def test_cancelled_stop_with_open_same_venue_position_is_not_closed():
    status, _ = classify_protection(order(target="CANCELLED"), [], -9)
    assert status == "unprotected_open"


def test_unfilled_cancelled_entry_is_not_unprotected_position():
    status, _ = classify_protection(order(target="CANCELLED", filled=0), [], 0)
    assert status == "unfilled"


def test_closed_position_with_pending_legs_needs_reconciliation():
    status, _ = classify_protection(order(stop="PENDING", target="PENDING"), [], 0)
    assert status == "orphan_pending"


def test_fill_price_uses_quantity_weights_and_broker_time_is_ist():
    quantity, price = weighted([{"tradedQuantity": 1, "tradedPrice": 100}, {"tradedQuantity": 3, "tradedPrice": 102}])
    assert quantity == 4
    assert price == 101.5
    assert timestamp("2026-09-09 09:15:00") == timestamp("2026-09-09T03:45:00Z")
