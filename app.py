"""skiReport - a Flask site serving snow-focused weather for ski mountains."""

from __future__ import annotations

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

from skireport import mountains, weather


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            regions=mountains.by_region(),
            total=len(mountains.all_mountains()),
        )

    @app.post("/")
    def pick():
        """Non-JS fallback for the picker form."""
        mountain_id = (request.form.get("mountain_id") or "").strip()
        if mountains.get(mountain_id) is None:
            abort(404)
        return redirect(url_for("mountain_report", mountain_id=mountain_id))

    @app.get("/mountain/<mountain_id>")
    def mountain_report(mountain_id: str):
        mountain = mountains.get(mountain_id)
        if mountain is None:
            abort(404)

        try:
            report = weather.get_report(mountain)
        except weather.WeatherUnavailable:
            app.logger.exception("weather fetch failed for %s", mountain_id)
            return (
                render_template(
                    "mountain.html",
                    mountain=mountain,
                    report=None,
                    regions=mountains.by_region(),
                ),
                503,
            )

        return render_template(
            "mountain.html",
            mountain=mountain,
            report=report,
            regions=mountains.by_region(),
        )

    @app.get("/api/mountains")
    def api_mountains():
        return jsonify(
            [
                {
                    "id": m.id,
                    "name": m.name,
                    "region": m.region,
                    "state": m.state,
                    "country": m.country,
                }
                for m in mountains.all_mountains()
            ]
        )

    @app.get("/api/mountain/<mountain_id>")
    def api_mountain(mountain_id: str):
        mountain = mountains.get(mountain_id)
        if mountain is None:
            return jsonify({"error": "unknown mountain", "id": mountain_id}), 404

        try:
            report = weather.get_report(mountain)
        except weather.WeatherUnavailable as exc:
            return jsonify({"error": str(exc), "id": mountain_id}), 503

        return jsonify(weather.report_to_dict(report))

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "mountains": len(mountains.all_mountains())})

    @app.errorhandler(404)
    def not_found(_error):
        return (
            render_template(
                "error.html",
                code=404,
                title="Not found",
                message="No mountain by that name. Pick one from the list below.",
                regions=mountains.by_region(),
            ),
            404,
        )

    @app.errorhandler(500)
    def server_error(_error):
        return (
            render_template(
                "error.html",
                code=500,
                title="Something broke",
                message="An unexpected error occurred. Try again in a moment.",
                regions=mountains.by_region(),
            ),
            500,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
