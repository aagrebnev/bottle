"""dc_yield_quoter - Bottle web application for yield calculations."""

import os
import json
import sys

# Add parent directory to path so we can import bottle directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bottle
from bottle import Bottle, request, response, static_file

from dc_yield_quoter.quoter import (
    simple_yield,
    compound_yield,
    apr_to_apy,
    apy_to_apr,
    discount_yield,
    bond_equivalent_yield,
    current_yield,
    continuous_compound_yield,
)

app = Bottle()


def json_response(data, status=200):
    response.content_type = "application/json"
    response.status = status
    return json.dumps(data)


def get_float(name, default=None, required=True):
    """Extract a float query parameter."""
    val = request.params.get(name)
    if val is None:
        if required and default is None:
            raise ValueError(f"Missing required parameter: {name}")
        return default
    return float(val)


def get_int(name, default=None, required=True):
    """Extract an int query parameter."""
    val = request.params.get(name)
    if val is None:
        if required and default is None:
            raise ValueError(f"Missing required parameter: {name}")
        return default
    return int(val)


@app.route("/")
def index():
    """Serve the main page."""
    return static_file("index.html", root=os.path.join(os.path.dirname(__file__), "static"))


@app.route("/static/<filepath:path>")
def serve_static(filepath):
    return static_file(filepath, root=os.path.join(os.path.dirname(__file__), "static"))


@app.route("/api/health")
def health():
    return json_response({"status": "ok", "version": "1.0.0"})


@app.route("/api/simple-yield")
def api_simple_yield():
    """GET /api/simple-yield?principal=1000&rate=0.05&years=3"""
    try:
        result = simple_yield(
            principal=get_float("principal"),
            rate=get_float("rate"),
            years=get_float("years"),
        )
        return json_response(result)
    except (ValueError, ZeroDivisionError) as e:
        return json_response({"error": str(e)}, 400)


@app.route("/api/compound-yield")
def api_compound_yield():
    """GET /api/compound-yield?principal=1000&rate=0.05&years=3&periods=12"""
    try:
        result = compound_yield(
            principal=get_float("principal"),
            rate=get_float("rate"),
            years=get_float("years"),
            compounding_periods=get_int("periods", default=12, required=False),
        )
        return json_response(result)
    except (ValueError, ZeroDivisionError) as e:
        return json_response({"error": str(e)}, 400)


@app.route("/api/apr-to-apy")
def api_apr_to_apy():
    """GET /api/apr-to-apy?apr=0.05&periods=12"""
    try:
        result = apr_to_apy(
            apr=get_float("apr"),
            compounding_periods=get_int("periods", default=12, required=False),
        )
        return json_response(result)
    except (ValueError, ZeroDivisionError) as e:
        return json_response({"error": str(e)}, 400)


@app.route("/api/apy-to-apr")
def api_apy_to_apr():
    """GET /api/apy-to-apr?apy=0.05&periods=12"""
    try:
        result = apy_to_apr(
            apy=get_float("apy"),
            compounding_periods=get_int("periods", default=12, required=False),
        )
        return json_response(result)
    except (ValueError, ZeroDivisionError) as e:
        return json_response({"error": str(e)}, 400)


@app.route("/api/discount-yield")
def api_discount_yield():
    """GET /api/discount-yield?face_value=1000&purchase_price=980&days=90"""
    try:
        result = discount_yield(
            face_value=get_float("face_value"),
            purchase_price=get_float("purchase_price"),
            days_to_maturity=get_int("days"),
        )
        return json_response(result)
    except (ValueError, ZeroDivisionError) as e:
        return json_response({"error": str(e)}, 400)


@app.route("/api/bond-equivalent-yield")
def api_bond_equivalent_yield():
    """GET /api/bond-equivalent-yield?face_value=1000&purchase_price=980&days=90"""
    try:
        result = bond_equivalent_yield(
            face_value=get_float("face_value"),
            purchase_price=get_float("purchase_price"),
            days_to_maturity=get_int("days"),
        )
        return json_response(result)
    except (ValueError, ZeroDivisionError) as e:
        return json_response({"error": str(e)}, 400)


@app.route("/api/current-yield")
def api_current_yield():
    """GET /api/current-yield?coupon=50&price=980"""
    try:
        result = current_yield(
            annual_coupon=get_float("coupon"),
            market_price=get_float("price"),
        )
        return json_response(result)
    except (ValueError, ZeroDivisionError) as e:
        return json_response({"error": str(e)}, 400)


@app.route("/api/continuous-yield")
def api_continuous_yield():
    """GET /api/continuous-yield?principal=1000&rate=0.05&years=3"""
    try:
        result = continuous_compound_yield(
            principal=get_float("principal"),
            rate=get_float("rate"),
            years=get_float("years"),
        )
        return json_response(result)
    except (ValueError, ZeroDivisionError) as e:
        return json_response({"error": str(e)}, 400)


@app.route("/api/quote", method="POST")
def api_quote():
    """POST /api/quote - Calculate multiple yields at once.

    Body JSON: {"principal": 1000, "rate": 0.05, "years": 3, "compounding_periods": 12}
    """
    try:
        data = request.json
        if not data:
            return json_response({"error": "JSON body required"}, 400)

        principal = float(data.get("principal", 0))
        rate = float(data.get("rate", 0))
        years = float(data.get("years", 0))
        periods = int(data.get("compounding_periods", 12))

        if principal <= 0 or rate <= 0 or years <= 0:
            return json_response({"error": "principal, rate, and years must be positive"}, 400)

        results = {
            "simple": simple_yield(principal, rate, years),
            "compound": compound_yield(principal, rate, years, periods),
            "continuous": continuous_compound_yield(principal, rate, years),
            "apr_to_apy": apr_to_apy(rate, periods),
        }
        return json_response(results)
    except (ValueError, TypeError, ZeroDivisionError) as e:
        return json_response({"error": str(e)}, 400)


def main():
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug, reloader=debug)


if __name__ == "__main__":
    main()
