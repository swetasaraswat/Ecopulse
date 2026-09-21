import datetime as dt

TODAY = dt.date.today().isoformat()


def make_user(client, user_id="sweta", region="IN"):
    return client.put(f"/users/{user_id}", json={"region": region})


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["ai_enabled"] is False


def test_reference_data(client):
    factors = client.get("/factors").json()
    assert any(f["key"] == "electricity_home" for f in factors)
    regions = {r["code"]: r for r in client.get("/regions").json()}
    assert regions["IN"]["kg_co2e_per_kwh"] == 0.727
    assert "GLOBAL" in regions


def test_stateless_estimate_is_localised(client):
    body = {"activities": [{"activity_type": "electricity_home", "quantity": 100}]}
    india = client.post("/estimate", json={"region": "IN", **body}).json()
    uk = client.post("/estimate", json={"region": "GB", **body}).json()
    assert india["total_co2e_kg"] > uk["total_co2e_kg"]


def test_estimate_rejects_unknown_activity(client):
    response = client.post("/estimate", json={"region": "IN", "activities": [{"activity_type": "jetpack", "quantity": 1}]})
    assert response.status_code == 422
    assert "jetpack" in response.json()["detail"]


def test_estimate_rejects_bad_quantity_and_region(client):
    bad_qty = client.post("/estimate", json={"region": "IN", "activities": [{"activity_type": "bus", "quantity": -3}]})
    bad_region = client.post("/estimate", json={"region": "not a region!", "activities": [{"activity_type": "bus", "quantity": 3}]})
    assert bad_qty.status_code == 422 and bad_region.status_code == 422


def test_unknown_user_is_404(client):
    assert client.get("/users/ghost").status_code == 404
    assert client.get("/users/ghost/footprint").status_code == 404
    assert client.post("/users/ghost/activities", json={"activities": [{"activity_type": "bus", "quantity": 1}]}).status_code == 404


def test_full_flow_log_footprint_history(client):
    assert make_user(client).status_code == 200
    logged = client.post(
        "/users/sweta/activities",
        json={"date": TODAY, "activities": [
            {"activity_type": "car_petrol", "quantity": 12},
            {"activity_type": "electricity_home", "quantity": 8, "notes": "AC on"},
            {"activity_type": "meal_vegetarian", "quantity": 2},
        ]},
    )
    assert logged.status_code == 201
    total = logged.json()["total_co2e_kg"]
    assert total > 0 and len(logged.json()["logged"]) == 3

    footprint = client.get("/users/sweta/footprint", params={"date": TODAY}).json()
    assert footprint["total_co2e_kg"] == total
    assert set(footprint["by_category"]) == {"transport", "energy", "food"}
    assert footprint["activities"][1]["notes"] == "AC on"

    history = client.get("/users/sweta/history", params={"days": 7}).json()
    assert len(history["days"]) == 7
    assert history["days"][-1]["co2e_kg"] == total
    assert history["days"][0]["co2e_kg"] == 0
    assert history["total_co2e_kg"] == total


def test_changing_region_changes_later_estimates(client):
    make_user(client, region="IN")
    a = client.post("/users/sweta/activities", json={"activities": [{"activity_type": "electricity_home", "quantity": 10}]}).json()
    make_user(client, region="GB")
    b = client.post("/users/sweta/activities", json={"activities": [{"activity_type": "electricity_home", "quantity": 10}]}).json()
    assert a["total_co2e_kg"] > b["total_co2e_kg"]


def test_unknown_activity_logs_nothing(client):
    make_user(client)
    response = client.post("/users/sweta/activities", json={"activities": [
        {"activity_type": "bus", "quantity": 5}, {"activity_type": "nope", "quantity": 1}]})
    assert response.status_code == 422
    assert client.get("/users/sweta/footprint").json()["activities"] == []


def test_recommendations_end_to_end_without_ai(client):
    make_user(client)
    for offset in range(7):
        day = (dt.date.today() - dt.timedelta(days=offset)).isoformat()
        client.post("/users/sweta/activities", json={"date": day, "activities": [
            {"activity_type": "car_petrol", "quantity": 15}, {"activity_type": "meal_beef", "quantity": 1}]})
    body = client.get("/users/sweta/recommendations").json()
    assert body["source"] == "rules"
    assert body["suggestions"]
    assert body["suggestions"][0]["weekly_saving_kg_co2e"] > 0
    assert "kg CO2e a day" in body["summary"]
