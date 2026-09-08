import asyncio
import sys
import os
sys.path.insert(0, os.getcwd())

from httpx import ASGITransport, AsyncClient
import uuid
from bson import ObjectId
from datetime import datetime, timezone
from app.main import app
from app.database import users_collection
from app.core.legacy import _issue_tokens

async def run_audit():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        print("==================================================")
        print("STARTING PROFILE HEADQUARTERS (SECTION J) AUDIT")
        print("==================================================")

        # 1. Setup Test User A
        user_a_id = ObjectId()
        email_a = f"audit_a_{user_a_id.binary.hex()[:8]}@example.com"
        user_a = {
            "_id": user_a_id,
            "email": email_a,
            "name": "Audit User Alpha",
            "is_verified": True,
            "is_admin": False,
            "points": 0,
            "subscription_tier": "SILVER",
            "subscription_status": "ACTIVE",
            "created_at": datetime.now(timezone.utc),
        }
        await users_collection.insert_one(user_a)
        token_resp_a = await _issue_tokens(user_a, None)
        token_a = token_resp_a.access_token or token_resp_a.session_token
        headers_a = {"Authorization": f"Bearer {token_a}"}
        print(f" PASS: User A created ({email_a}) & authenticated")

        # 2. Setup Test User B (for partner pairing)
        user_b_id = ObjectId()
        email_b = f"audit_b_{user_b_id.binary.hex()[:8]}@example.com"
        user_b = {
            "_id": user_b_id,
            "email": email_b,
            "name": "Audit User Beta",
            "is_verified": True,
            "is_admin": False,
            "points": 0,
            "subscription_tier": "SILVER",
            "subscription_status": "ACTIVE",
            "created_at": datetime.now(timezone.utc),
        }
        await users_collection.insert_one(user_b)
        token_resp_b = await _issue_tokens(user_b, None)
        token_b = token_resp_b.access_token or token_resp_b.session_token
        headers_b = {"Authorization": f"Bearer {token_b}"}
        print(f" PASS: User B created ({email_b}) & authenticated")

        # ==========================================================
        # FEATURE 1 — Identity Statement (Section 20.3)
        # ==========================================================
        identity_text = "I am someone who trains even when it is hard."
        resp = await client.patch("/me", json={
            "identity_statement": identity_text,
        }, headers=headers_a)
        assert resp.status_code == 200, f"Identity save failed: {resp.text}"
        data = resp.json()
        assert data.get("identity_statement") == identity_text, "Identity statement mismatch"

        # Verify clear capability
        resp = await client.patch("/me", json={
            "identity_statement": "",
        }, headers=headers_a)
        assert resp.status_code == 200
        # Re-set verbatim
        await client.patch("/me", json={"identity_statement": identity_text}, headers=headers_a)
        print(" PASS: Feature 1 (Identity Statement input, edit & clear) verified verbatim")

        # ==========================================================
        # FEATURE 2 — Workout Unlock field (Section 20.4)
        # ==========================================================
        unlock_label = "Favorite Podcast & Espresso"
        resp = await client.patch("/me", json={
            "workout_unlock_label": unlock_label,
        }, headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("workout_unlock_label") == unlock_label
        print(" PASS: Feature 2 (Workout Unlock field saved & retrieved) verified")

        # ==========================================================
        # FEATURE 3 — If-Then Trigger Builder (Section 20.5)
        # ==========================================================
        trigger_context = "Kids in bed"
        trigger_action = "open the app and start my workout"
        resp = await client.patch("/me", json={
            "training_trigger_context": trigger_context,
            "training_trigger_action": trigger_action,
        }, headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("training_trigger_context") == trigger_context
        assert data.get("training_trigger_action") == trigger_action
        print(" PASS: Feature 3 (If-Then Trigger Builder context + action) verified")

        # ==========================================================
        # FEATURE 4 — Accountability Partner pairing works (Section 20.1)
        # ==========================================================
        # Check initial partner state (none)
        resp = await client.get("/me/accountability-partner", headers=headers_a)
        assert resp.status_code == 200
        assert resp.json().get("status") == "none"

        # User A creates an invite
        resp = await client.post("/accountability-pairs/invite", json={"email": email_b}, headers=headers_a)
        assert resp.status_code in (200, 201), f"Invite failed: {resp.text}"
        invite_data = resp.json()
        invite_code = invite_data.get("invite_code")
        pair_id = invite_data.get("pair_id")
        assert invite_code and len(invite_code) == 6, f"Invalid invite code: {invite_code}"
        print(f" PASS: User A created invite code: {invite_code}")

        # User B accepts the invite code
        resp = await client.post("/accountability-pairs/accept", json={"invite_code": invite_code}, headers=headers_b)
        assert resp.status_code == 200, f"Accept failed: {resp.text}"
        assert resp.json().get("success") is True
        print(" PASS: User B accepted invite code (Mutual accept complete)")

        # Verify partner status on both sides
        resp_a = await client.get("/me/accountability-partner", headers=headers_a)
        assert resp_a.status_code == 200
        partner_data_a = resp_a.json()
        assert partner_data_a.get("status") == "active"
        assert partner_data_a.get("partner") is not None
        assert partner_data_a["partner"]["email"] == email_b
        # Has User B trained today? (False initially -> grey circle)
        assert partner_data_a["partner"]["trained_today"] is False
        assert partner_data_a.get("can_nudge") is True
        print(" PASS: Partner card displays grey circle (not trained today) & can_nudge is True")

        # Test 8pm Nudge from User A to User B
        resp_nudge = await client.post(f"/accountability-pairs/{pair_id}/nudge", headers=headers_a)
        assert resp_nudge.status_code == 200
        assert resp_nudge.json().get("success") is True
        print(" PASS: Nudge sent successfully to partner")

        # Verify in-app notification arrived for User B
        resp_notif = await client.get("/me/notifications", headers=headers_b)
        assert resp_notif.status_code == 200
        notifs = resp_notif.json().get("items", [])
        nudge_found = any("accountability" in str(n.get("type", "")).lower() or "partner" in str(n.get("title", "")).lower() for n in notifs)
        assert nudge_found, "Partner nudge notification not found in User B inbox"
        print(" PASS: User B received partner nudge in notifications")

        # Test automated 8pm nudges scanner
        resp_scan = await client.post("/accountability-pairs/run-8pm-nudges", headers=headers_a)
        assert resp_scan.status_code == 200
        print(f" PASS: Automated 8pm scanner executed: {resp_scan.json()}")

        # Now simulate User B completing a workout
        await client.post("/workout-logs", json={
            "workout_id": "test_wod_1",
            "workout_name": "Chest & Arms",
            "duration_seconds": 1800,
            "exercises_completed": 5,
        }, headers=headers_b)

        # Check User A view again -> trained_today should now be True (Green Tick!)
        resp_a_trained = await client.get("/me/accountability-partner", headers=headers_a)
        assert resp_a_trained.status_code == 200
        partner_data_a_trained = resp_a_trained.json()
        assert partner_data_a_trained["partner"]["trained_today"] is True
        print(" PASS: Partner card displays green tick (trained today confirmed in real-time)")

        # ==========================================================
        # FEATURE 5 — Points and Tier Progression (Section J)
        # ==========================================================
        # Log a few points for User A
        await client.post("/points-log", json={"points": 100, "reason": "strength_workout"}, headers=headers_a)
        await client.post("/points-log", json={"points": 50, "reason": "nutrition_logged"}, headers=headers_a)
        await client.post("/points-log", json={"points": 30, "reason": "daily_streak"}, headers=headers_a)

        resp_pts = await client.get("/me/points/breakdown", headers=headers_a)
        assert resp_pts.status_code == 200
        pts_data = resp_pts.json()
        assert "total_points" in pts_data
        assert "current_tier" in pts_data
        assert "next_tier" in pts_data
        assert "points_to_next_tier" in pts_data
        assert "seven_day_breakdown" in pts_data
        assert len(pts_data["seven_day_breakdown"]) == 7
        assert "category_totals_7d" in pts_data
        assert pts_data["category_totals_7d"]["workouts"] >= 100
        assert pts_data["category_totals_7d"]["nutrition"] >= 50
        assert pts_data["category_totals_7d"]["streaks"] >= 30
        print(f" PASS: Feature 5 (Points: {pts_data['total_points']}, Tier: {pts_data['current_tier']}, 7-day breakdown: {pts_data['category_totals_7d']}) verified")

        # ==========================================================
        # FEATURE 6 — Subscription Management (cancel, pause, change plan)
        # ==========================================================
        # Check initial subscription
        resp_sub = await client.get("/me/subscription", headers=headers_a)
        assert resp_sub.status_code == 200
        sub_info = resp_sub.json()["subscription"]
        print(f" Initial subscription: {sub_info['tier']} ({sub_info['status']})")

        # Change plan to Gold
        resp_change = await client.post("/me/subscription/change-plan", json={
            "plan_id": "gold",
            "billing_cycle": "yearly",
        }, headers=headers_a)
        assert resp_change.status_code == 200
        assert resp_change.json().get("tier") == "GOLD"
        print(" PASS: Changed subscription plan to GOLD")

        # Pause subscription for 30 days
        resp_pause = await client.post("/me/subscription/pause", json={"pause_days": 30}, headers=headers_a)
        assert resp_pause.status_code == 200
        pause_data = resp_pause.json()
        assert pause_data.get("status") == "PAUSED"
        assert pause_data.get("paused_until") is not None
        print(f" PASS: Subscription paused until {pause_data.get('paused_until')}")

        # Resume subscription
        resp_resume = await client.post("/me/subscription/resume", headers=headers_a)
        assert resp_resume.status_code == 200
        assert resp_resume.json().get("status") == "ACTIVE"
        print(" PASS: Subscription resumed to ACTIVE")

        # Cancel subscription (must stay active until period_end)
        resp_cancel = await client.post("/me/subscription/cancel", json={
            "reason": "Test cancellation",
        }, headers=headers_a)
        assert resp_cancel.status_code == 200
        cancel_data = resp_cancel.json()
        assert cancel_data.get("status") == "CANCELLED"
        period_end = cancel_data.get("current_period_end")
        assert period_end is not None

        # Verify that access remains active until period_end
        resp_sub_after = await client.get("/me/subscription", headers=headers_a)
        sub_after = resp_sub_after.json()["subscription"]
        assert sub_after["is_cancelled"] is True
        assert sub_after["has_active_access"] is True
        print(f" PASS: Cancelled subscription stays active until {period_end} (has_active_access: True)")

        # ==========================================================
        # UPGRADE — Post-workout upgrade offer (Section 17.1)
        # ==========================================================
        resp_offer = await client.get("/me/subscription/upgrade-offer", headers=headers_a)
        assert resp_offer.status_code == 200
        offer_data = resp_offer.json()
        assert offer_data.get("eligible") is True
        assert "keep this going" in offer_data.get("message", "").lower() or "unlock" in offer_data.get("message", "").lower()
        print(f" PASS: Section 17.1 upgrade offer available from Profile: \"{offer_data.get('message')}\"")

        print("==================================================")
        print("ALL 7 SECTION J FEATURES PASSED PERFECTLY!")
        print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_audit())
