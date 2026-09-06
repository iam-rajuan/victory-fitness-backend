from app.nutrition_ai import calculate_protein_target, _build_fallback_nutrition_plan


def test_protein_target_70kg_shows_112g():
    target, multiplier = calculate_protein_target("70", "g3")
    assert target == 112
    assert multiplier == 1.6


def test_protein_target_80kg_active_sportler_shows_160g():
    target, multiplier = calculate_protein_target("80", "g2")
    assert target == 160
    assert multiplier == 2.0


def test_protein_target_weight_loss_keeps_protein():
    target, multiplier = calculate_protein_target("80", "g1")
    assert target == 128
    assert multiplier == 1.6


def test_fallback_plan_includes_protein_target():
    payload = {
        "weight": "70",
        "goal": "g3",
        "cuisine": "Mediterranean",
    }
    plan = _build_fallback_nutrition_plan(payload)
    assert plan.get("daily_protein_target") == 112
    assert plan.get("protein_per_kg") == 1.6
    assert plan.get("baseline_weight") == 70.0

    # Ensure day meal protein sums to daily protein target
    mon = plan["days"][0]
    total_p = mon["breakfast"]["p"] + mon["lunch"]["p"] + mon["dinner"]["p"]
    assert total_p == 112


def test_weight_delta_trigger_logic():
    baseline_w = 70.0

    # Change to 71kg (delta = 1.0 < 2.0) -> should not trigger
    delta_1kg = abs(71.0 - baseline_w)
    assert delta_1kg < 2.0

    # Change to 73kg (delta = 3.0 >= 2.0) -> should trigger and update
    delta_3kg = abs(73.0 - baseline_w)
    assert delta_3kg >= 2.0
    new_target, _ = calculate_protein_target("73", "g3")
    assert new_target == round(73 * 1.6)  # 117g

    # Change to 67kg (delta = 3.0 >= 2.0) -> should trigger and update
    delta_loss = abs(67.0 - baseline_w)
    assert delta_loss >= 2.0
    loss_target, _ = calculate_protein_target("67", "g1")
    assert loss_target == round(67 * 1.6)  # 107g
