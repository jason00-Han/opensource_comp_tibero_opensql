from services.api import main


def test_dashboard_endpoint_requires_manager_and_returns_aggregated_status(api_client, monkeypatch):
    monkeypatch.setattr(main, "dashboard_overview", lambda context: {
        "status": "healthy", "generated_at": "2026-08-21T00:00:00Z",
        "opensql": {"documents": 2}, "workers": {"online": 1},
    })
    response = api_client.get("/v1/admin/dashboard/overview")
    assert response.status_code == 200
    assert response.json()["opensql"]["documents"] == 2


def test_root_redirects_to_web_dashboard(api_client):
    response = api_client.get("/", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/ui/"
