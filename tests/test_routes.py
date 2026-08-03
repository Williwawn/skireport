from markupsafe import escape

from skireport import mountains, weather


def test_index_lists_every_mountain(client):
    body = client.get("/").get_data(as_text=True)

    assert "Jackson Hole" in body
    assert "Whistler Blackcomb" in body
    for region in mountains.by_region():
        # Region names contain "&", which Jinja escapes on the way out.
        assert str(escape(region)) in body


def test_mountain_page_renders(client):
    response = client.get("/mountain/jackson-hole")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Jackson Hole" in body
    assert "Seven-day outlook" in body
    assert "Base" in body and "Summit" in body
    # Headline new snow from the fixture; the inch mark is escaped to &#34;.
    assert "24.0&#34;" in body
    assert "6,312 ft" in body  # base elevation, 1924 m converted


def test_unknown_mountain_is_404(client):
    response = client.get("/mountain/nope")
    assert response.status_code == 404
    assert "No mountain by that name" in response.get_data(as_text=True)


def test_picker_post_redirects(client):
    response = client.post("/", data={"mountain_id": "stowe"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/mountain/stowe")


def test_picker_post_rejects_unknown(client):
    assert client.post("/", data={"mountain_id": "nope"}).status_code == 404


def test_api_mountain(client):
    payload = client.get("/api/mountain/alta").get_json()

    assert payload["mountain"]["name"] == "Alta"
    assert payload["base"]["elevation_m"] == mountains.get("alta").base_elevation_m
    assert payload["summit"]["snow_depth_in"] == 60.0
    assert len(payload["forecast"]) == 7


def test_api_mountain_unknown(client):
    response = client.get("/api/mountain/nope")
    assert response.status_code == 404
    assert response.get_json()["error"] == "unknown mountain"


def test_api_mountains_index(client):
    payload = client.get("/api/mountains").get_json()
    assert len(payload) == len(mountains.all_mountains())
    assert {"id", "name", "region", "state", "country"} == set(payload[0])


def test_healthz(client):
    payload = client.get("/healthz").get_json()
    assert payload["ok"] is True
    assert payload["mountains"] >= 40


def test_page_degrades_when_upstream_is_down(client, monkeypatch):
    def boom(mountain):
        raise weather.WeatherUnavailable("upstream down")

    monkeypatch.setattr(weather, "get_report", boom)

    response = client.get("/mountain/vail")
    body = response.get_data(as_text=True)

    assert response.status_code == 503
    assert "Weather unavailable" in body
    assert "Traceback" not in body


def test_api_reports_upstream_failure(client, monkeypatch):
    def boom(mountain):
        raise weather.WeatherUnavailable("upstream down")

    monkeypatch.setattr(weather, "get_report", boom)
    assert client.get("/api/mountain/vail").status_code == 503
