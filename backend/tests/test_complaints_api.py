"""The HTTP contract: status codes, validation bodies, filters, transitions."""

import uuid

from tests.conftest import VALID_COMPLAINT


async def submit(client, **overrides):
    payload = {**VALID_COMPLAINT, **overrides}
    return await client.post("/api/complaints", json=payload)


async def test_submit_returns_201_with_triage_applied(client) -> None:
    response = await submit(client)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["category"] in {"water", "electricity", "sanitation", "roads", "streetlights", "other"}
    assert body["priority"] in {"high", "normal", "low"}
    assert len(body["ai_summary"]) <= 140
    assert body["triaged_by"]
    assert body["triage_latency_ms"] >= 0
    assert response.headers["Location"] == f"/api/complaints/{body['id']}"


async def test_short_text_is_400_with_field_level_errors(client) -> None:
    response = await submit(client, text="too short")
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "validation_error"
    assert [field["field"] for field in body["fields"]] == ["text"]


async def test_multiple_invalid_fields_are_all_reported(client) -> None:
    response = await client.post("/api/complaints", json={"text": "x", "location": "y"})
    assert response.status_code == 400
    fields = {field["field"] for field in response.json()["fields"]}
    assert fields == {"text", "location"}


async def test_unknown_complaint_is_404(client) -> None:
    response = await client.get(f"/api/complaints/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


async def test_round_trip_submit_then_fetch(client) -> None:
    created = (await submit(client)).json()
    fetched = await client.get(f"/api/complaints/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["text"] == VALID_COMPLAINT["text"]


async def test_list_paginates_and_reports_total(client) -> None:
    for index in range(5):
        await submit(client, text=f"Streetlight number {index} is not working since last week at all.")
    page_one = (await client.get("/api/complaints?page=1&page_size=2")).json()
    assert page_one["total"] == 5
    assert len(page_one["items"]) == 2
    page_three = (await client.get("/api/complaints?page=3&page_size=2")).json()
    assert len(page_three["items"]) == 1


async def test_list_filters_by_status(client) -> None:
    created = (await submit(client)).json()
    await client.patch(f"/api/complaints/{created['id']}/status", json={"status": "in_progress"})
    await submit(client, text="Garbage container is overflowing near the market since three days.")

    open_only = (await client.get("/api/complaints?status=open")).json()
    assert open_only["total"] == 1
    in_progress = (await client.get("/api/complaints?status=in_progress")).json()
    assert in_progress["total"] == 1
    assert in_progress["items"][0]["id"] == created["id"]


async def test_page_size_above_the_cap_is_rejected(client) -> None:
    response = await client.get("/api/complaints?page_size=101")
    assert response.status_code == 400


async def test_valid_status_transition_is_applied(client) -> None:
    created = (await submit(client)).json()
    response = await client.patch(
        f"/api/complaints/{created['id']}/status", json={"status": "in_progress"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


async def test_invalid_transition_returns_409_naming_the_transition(client) -> None:
    created = (await submit(client)).json()
    await client.patch(f"/api/complaints/{created['id']}/status", json={"status": "rejected"})
    response = await client.patch(
        f"/api/complaints/{created['id']}/status", json={"status": "resolved"}
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "invalid_transition"
    assert body["message"] == "cannot transition from rejected to resolved"
    assert body["attempted"] == {"from": "rejected", "to": "resolved"}
    assert body["allowed"] == []
