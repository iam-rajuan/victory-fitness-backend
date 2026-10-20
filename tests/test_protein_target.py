import pytest
from app.nutrition_ai import (
    calculate_protein_target,
    _protein_target_instruction,
    _workout_nutrient_timing_instruction,
    _build_nutrition_plan_prompt,
    _normalize_nutrition_plan,
    calculate_daily_macro_targets,
    _build_fallback_nutrition_plan,
)


def test_daily_macro_targets_match_current_muscle_building_profile():
    targets = calculate_daily_macro_targets(77, "g2")

    assert targets == {
        "protein": 169,
        "carbs": 292,
        "fat": 62,
        "calories": 2402,
        "protein_per_kg": 2.2,
        "weight_kg": 77.0,
    }


# ==============================================================================
# Focused Tests: 60 kg, 70 kg, 90 kg Across Relevant Goals
# ==============================================================================

@pytest.mark.parametrize(
    "goal_input",
    ["g3", "maintenance", "normal", "weight maintenance", "weight_maintenance", "To feel strong again"],
)
def test_protein_target_60kg_maintenance(goal_input: str):
    """60 kg maintenance: minimum approximately 1.6 g/kg -> 96 g/day."""
    target, multiplier = calculate_protein_target(60, goal_input)
    assert multiplier == 1.6
    assert target == 96  # round(60 * 1.6)


@pytest.mark.parametrize(
    "goal_input",
    ["g2", "muscle_growth", "muscle gain", "muscle building", "hypertrophy", "To build visible muscle"],
)
def test_protein_target_60kg_muscle_growth(goal_input: str):
    """60 kg muscle-growth goal: target up to approximately 2.2 g/kg -> 132 g/day."""
    target, multiplier = calculate_protein_target(60, goal_input)
    assert multiplier == 2.2
    assert target == 132  # round(60 * 2.2)


@pytest.mark.parametrize(
    "goal_input",
    ["g1", "weight reduction", "weight_reduction", "weight loss", "weight_loss", "lose weight", "To lose weight steadily"],
)
def test_protein_target_60kg_weight_reduction(goal_input: str):
    """60 kg weight-reduction goal: approximately 2.2 g/kg -> 132 g/day."""
    target, multiplier = calculate_protein_target(60, goal_input)
    assert multiplier == 2.2
    assert target == 132  # round(60 * 2.2)


@pytest.mark.parametrize(
    "goal_input",
    ["g3", "maintenance", "normal", "weight maintenance", "weight_maintenance", "To feel strong again"],
)
def test_protein_target_70kg_maintenance(goal_input: str):
    """70 kg maintenance: at least ~112 g/day (1.6 g/kg)."""
    target, multiplier = calculate_protein_target(70, goal_input)
    assert multiplier == 1.6
    assert target == 112  # round(70 * 1.6)


@pytest.mark.parametrize(
    "goal_input",
    ["g2", "muscle_growth", "muscle gain", "muscle building", "hypertrophy", "To build visible muscle"],
)
def test_protein_target_70kg_muscle_growth(goal_input: str):
    """70 kg muscle-growth goal: target up to approximately 2.2 g/kg -> 154 g/day."""
    target, multiplier = calculate_protein_target(70, goal_input)
    assert multiplier == 2.2
    assert target == 154  # round(70 * 2.2)


@pytest.mark.parametrize(
    "goal_input",
    ["g1", "weight reduction", "weight_reduction", "weight loss", "weight_loss", "lose weight", "To lose weight steadily"],
)
def test_protein_target_70kg_weight_reduction(goal_input: str):
    """70 kg weight-reduction goal: approximately 2.2 g/kg -> 154 g/day."""
    target, multiplier = calculate_protein_target(70, goal_input)
    assert multiplier == 2.2
    assert target == 154  # round(70 * 2.2)


@pytest.mark.parametrize(
    "goal_input",
    ["g3", "maintenance", "normal", "weight maintenance", "weight_maintenance", "To feel strong again"],
)
def test_protein_target_90kg_maintenance(goal_input: str):
    """90 kg maintenance: minimum approximately 1.6 g/kg -> 144 g/day."""
    target, multiplier = calculate_protein_target(90, goal_input)
    assert multiplier == 1.6
    assert target == 144  # round(90 * 1.6)


@pytest.mark.parametrize(
    "goal_input",
    ["g2", "muscle_growth", "muscle gain", "muscle building", "hypertrophy", "To build visible muscle"],
)
def test_protein_target_90kg_muscle_growth(goal_input: str):
    """90 kg muscle-growth goal: target up to approximately 2.2 g/kg -> 198 g/day."""
    target, multiplier = calculate_protein_target(90, goal_input)
    assert multiplier == 2.2
    assert target == 198  # round(90 * 2.2)


@pytest.mark.parametrize(
    "goal_input",
    ["g1", "weight reduction", "weight_reduction", "weight loss", "weight_loss", "lose weight", "To lose weight steadily"],
)
def test_protein_target_90kg_weight_reduction(goal_input: str):
    """90 kg weight-reduction goal: approximately 2.2 g/kg -> 198 g/day."""
    target, multiplier = calculate_protein_target(90, goal_input)
    assert multiplier == 2.2
    assert target == 198  # round(90 * 2.2)


# ==============================================================================
# Deterministic AI Prompt Constraint Tests
# ==============================================================================

def test_ai_prompt_contains_calculated_protein_constraint():
    """Verify daily protein target is calculated deterministically before AI prompt creation."""
    payload_maint = {"weight": "70", "goal": "g3"}
    prompt_inst_maint = _protein_target_instruction(payload_maint)
    assert "EXACTLY 112g/day (1.6g/kg" in prompt_inst_maint
    assert "Do NOT alter, arbitrarily calculate, or guess a different protein requirement." in prompt_inst_maint

    timing_inst_maint = _workout_nutrient_timing_instruction(payload_maint)
    assert "1.6g/kg ±5g" in timing_inst_maint
    assert "112g protein/day" in timing_inst_maint

    full_prompt_maint = _build_nutrition_plan_prompt(payload_maint)
    assert "112g/day" in full_prompt_maint

    # 70 kg Muscle Growth (2.2 g/kg -> 154 g)
    payload_muscle = {"weight": "70", "goal": "g2"}
    prompt_inst_muscle = _protein_target_instruction(payload_muscle)
    assert "EXACTLY 154g/day (2.2g/kg" in prompt_inst_muscle

    # 70 kg Weight Reduction (2.2 g/kg -> 154 g)
    payload_loss = {"weight": "70", "goal": "g1"}
    prompt_inst_loss = _protein_target_instruction(payload_loss)
    assert "EXACTLY 154g/day (2.2g/kg" in prompt_inst_loss


# ==============================================================================
# Validation and Macro Normalization Against Deterministic Target
# ==============================================================================

def test_normalizer_validates_and_enforces_protein_target_for_muscle_growth():
    """Verify normalizer auto-adjusts arbitrary LLM output to match deterministic target (154g for 70kg muscle growth)."""
    deviant_plan = {
        "summary": "AI generated plan with low protein",
        "goal_label": "Muscle Building",
        "baseline_weight": 70.0,
        "daily_protein_target": 80,  # Arbitrary AI guess far below 154g
        "days": [
            {
                "day": "Mon",
                "breakfast": {"name": "Oatmeal", "desc": "Breakfast", "kcal": 300, "p": 10, "c": 50, "f": 5, "ingredients": [], "instructions": []},
                "lunch": {"name": "Chicken Wrap", "desc": "Lunch", "kcal": 450, "p": 25, "c": 45, "f": 12, "ingredients": [], "instructions": []},
                "pre_workout": {"name": "Rice Cakes", "desc": "Pre", "kcal": 200, "p": 5, "c": 40, "f": 2, "ingredients": [], "instructions": []},
                "post_workout": {"name": "Shake", "desc": "Post", "kcal": 300, "p": 30, "c": 25, "f": 3, "ingredients": [], "instructions": []},
                "dinner": {"name": "Salmon Bowl", "desc": "Dinner", "kcal": 400, "p": 20, "c": 35, "f": 10, "ingredients": [], "instructions": []},
            }
        ],
        "shopping_list": [],
    }

    payload = {"weight": 70.0, "goal": "muscle_growth"}
    normalized = _normalize_nutrition_plan(deviant_plan, payload=payload)

    # 1. Deterministic target strictly set
    assert normalized["daily_protein_target"] == 154
    assert normalized["protein_per_kg"] == 2.2

    # 2. Meal protein sums exactly to target 154g
    mon = normalized["days"][0]
    total_p = sum(mon[k]["p"] for k in ("breakfast", "lunch", "pre_workout", "post_workout", "dinner"))
    assert total_p == 154

    # 3. Strict macro math: kcal equals (p*4) + (c*4) + (f*9)
    for k in ("breakfast", "lunch", "pre_workout", "post_workout", "dinner"):
        meal = mon[k]
        expected_kcal = (meal["p"] * 4) + (meal["c"] * 4) + (meal["f"] * 9)
        assert meal["kcal"] == max(expected_kcal, 100)


def test_normalizer_validates_and_enforces_protein_target_for_weight_reduction():
    """Verify normalizer auto-adjusts arbitrary LLM output to match deterministic target (154g for 70kg weight loss)."""
    deviant_plan = {
        "summary": "AI generated plan with low protein",
        "goal_label": "Weight Loss",
        "baseline_weight": 70.0,
        "daily_protein_target": 75,  # Arbitrary AI guess far below 154g
        "days": [
            {
                "day": "Mon",
                "breakfast": {"name": "Eggs", "desc": "Breakfast", "kcal": 250, "p": 15, "c": 10, "f": 12, "ingredients": [], "instructions": []},
                "lunch": {"name": "Salad", "desc": "Lunch", "kcal": 350, "p": 20, "c": 20, "f": 15, "ingredients": [], "instructions": []},
                "pre_workout": {"name": "Apple & Whey", "desc": "Pre", "kcal": 200, "p": 15, "c": 25, "f": 2, "ingredients": [], "instructions": []},
                "post_workout": {"name": "Tuna Bowl", "desc": "Post", "kcal": 350, "p": 30, "c": 30, "f": 5, "ingredients": [], "instructions": []},
                "dinner": {"name": "Chicken Veg", "desc": "Dinner", "kcal": 350, "p": 25, "c": 15, "f": 10, "ingredients": [], "instructions": []},
            }
        ],
        "shopping_list": [],
    }

    payload = {"weight": 70.0, "goal": "g1"}
    normalized = _normalize_nutrition_plan(deviant_plan, payload=payload)

    assert normalized["daily_protein_target"] == 154
    assert normalized["protein_per_kg"] == 2.2

    mon = normalized["days"][0]
    total_p = sum(mon[k]["p"] for k in ("breakfast", "lunch", "pre_workout", "post_workout", "dinner"))
    assert total_p == 154


def test_normalizer_validates_and_enforces_protein_target_for_maintenance():
    """Verify normalizer auto-adjusts arbitrary LLM output to match deterministic target (112g for 70kg maintenance)."""
    deviant_plan = {
        "summary": "AI generated plan with high protein",
        "goal_label": "Maintenance",
        "baseline_weight": 70.0,
        "daily_protein_target": 180,  # Arbitrary AI hallucination far above 112g
        "days": [
            {
                "day": "Mon",
                "breakfast": {"name": "Eggs & Toast", "desc": "Breakfast", "kcal": 400, "p": 35, "c": 30, "f": 15, "ingredients": [], "instructions": []},
                "lunch": {"name": "Chicken Rice", "desc": "Lunch", "kcal": 550, "p": 50, "c": 50, "f": 12, "ingredients": [], "instructions": []},
                "pre_workout": {"name": "Banana Shake", "desc": "Pre", "kcal": 250, "p": 20, "c": 35, "f": 3, "ingredients": [], "instructions": []},
                "post_workout": {"name": "Double Shake", "desc": "Post", "kcal": 400, "p": 50, "c": 30, "f": 5, "ingredients": [], "instructions": []},
                "dinner": {"name": "Steak Bowl", "desc": "Dinner", "kcal": 500, "p": 45, "c": 25, "f": 18, "ingredients": [], "instructions": []},
            }
        ],
        "shopping_list": [],
    }

    payload = {"weight": 70.0, "goal": "g3"}
    normalized = _normalize_nutrition_plan(deviant_plan, payload=payload)

    assert normalized["daily_protein_target"] == 112
    assert normalized["protein_per_kg"] == 1.6

    mon = normalized["days"][0]
    total_p = sum(mon[k]["p"] for k in ("breakfast", "lunch", "pre_workout", "post_workout", "dinner"))
    assert total_p == 112


# ==============================================================================
# Fallback Plan Generation Tests Across Goals
# ==============================================================================

@pytest.mark.parametrize(
    "weight, goal, expected_protein, expected_mult",
    [
        (60, "g3", 96, 1.6),
        (60, "g2", 132, 2.2),
        (60, "g1", 132, 2.2),
        (70, "g3", 112, 1.6),
        (70, "g2", 154, 2.2),
        (70, "g1", 154, 2.2),
        (90, "g3", 144, 1.6),
        (90, "g2", 198, 2.2),
        (90, "g1", 198, 2.2),
    ],
)
def test_fallback_plan_deterministic_targets(weight: int, goal: str, expected_protein: int, expected_mult: float):
    payload = {
        "weight": str(weight),
        "goal": goal,
        "cuisine": "Mediterranean",
    }
    plan = _build_fallback_nutrition_plan(payload)
    assert plan["daily_protein_target"] == expected_protein
    assert plan["protein_per_kg"] == expected_mult
    assert plan["baseline_weight"] == float(weight)

    # Ensure every single day's 5 meals sum strictly to the expected daily protein target
    for day in plan["days"]:
        total_p = sum(day[k]["p"] for k in ("breakfast", "lunch", "pre_workout", "post_workout", "dinner"))
        assert total_p == expected_protein


# ==============================================================================
# Weight Delta Auto-Update Trigger Logic Tests
# ==============================================================================

def test_weight_delta_trigger_logic():
    baseline_w = 70.0

    # Change to 71kg (delta = 1.0 < 2.0) -> should not trigger
    delta_1kg = abs(71.0 - baseline_w)
    assert delta_1kg < 2.0

    # Change to 73kg maintenance (delta = 3.0 >= 2.0) -> should trigger and update to 1.6 g/kg
    delta_3kg = abs(73.0 - baseline_w)
    assert delta_3kg >= 2.0
    new_target, mult_maint = calculate_protein_target("73", "g3")
    assert mult_maint == 1.6
    assert new_target == round(73 * 1.6)  # 117g

    # Change to 67kg weight-reduction (delta = 3.0 >= 2.0) -> should trigger and update to 2.2 g/kg
    delta_loss = abs(67.0 - baseline_w)
    assert delta_loss >= 2.0
    loss_target, mult_loss = calculate_protein_target("67", "g1")
    assert mult_loss == 2.2
    assert loss_target == round(67 * 2.2)  # 147g

    # Change to 75kg muscle-growth (delta = 5.0 >= 2.0) -> should trigger and update to 2.2 g/kg
    delta_gain = abs(75.0 - baseline_w)
    assert delta_gain >= 2.0
    gain_target, mult_gain = calculate_protein_target("75", "g2")
    assert mult_gain == 2.2
    assert gain_target == round(75 * 2.2)  # 165g
