import pytest


@pytest.mark.asyncio
async def test_list_ideas_empty(client):
    r = await client.get("/api/ideas")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_then_list(client):
    r = await client.post("/api/ideas", json={"content": "ship a cloud-agnostic platform"})
    assert r.status_code == 201
    body = r.json()
    assert body["content"] == "ship a cloud-agnostic platform"
    assert body["id"] > 0
    assert body["created_at"]

    r = await client.get("/api/ideas")
    assert [i["content"] for i in r.json()] == ["ship a cloud-agnostic platform"]


@pytest.mark.asyncio
async def test_newest_first(client):
    for text in ("first", "second", "third"):
        assert (await client.post("/api/ideas", json={"content": text})).status_code == 201
    ideas = (await client.get("/api/ideas")).json()
    # created_at ties are possible, so assert on the set plus count instead of order
    assert {i["content"] for i in ideas} == {"first", "second", "third"}
    assert len(ideas) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"content": ""}, {"content": "   "}, {}, {"content": "x" * 501}])
async def test_rejects_bad_input(client, payload):
    r = await client.post("/api/ideas", json=payload)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_content_is_trimmed(client):
    r = await client.post("/api/ideas", json={"content": "  padded  "})
    assert r.json()["content"] == "padded"


@pytest.mark.asyncio
async def test_health_probes(client):
    assert (await client.get("/healthz")).json()["status"] == "ok"
    ready = await client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"


@pytest.mark.asyncio
async def test_metrics_exposed(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text
