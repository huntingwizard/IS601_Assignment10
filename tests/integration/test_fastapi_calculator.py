"""
Integration tests for the calculator HTTP API.

These exercise the real FastAPI app (routing, validation, error handlers)
through Starlette's TestClient, so no server process is needed.
"""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def api():
    with TestClient(app) as test_client:
        yield test_client


def call(api, op, a, b):
    return api.post(f"/{op}", json={"a": a, "b": b})


# Success tests

@pytest.mark.parametrize(
    "op, a, b, expected",
    [
        ("add", 10, 5, 15),
        ("add", -4, 1.5, -2.5),
        ("add", 0, 0, 0),
        ("subtract", 10, 5, 5),
        ("subtract", 3, 8, -5),
        ("subtract", 2.5, 0.5, 2.0),
        ("multiply", 10, 5, 50),
        ("multiply", -3, 4, -12),
        ("multiply", 7, 0, 0),
        ("divide", 10, 2, 5),
        ("divide", -9, 3, -3),
        ("divide", 0, 4, 0),
    ],
)
def test_operations_return_expected_result(api, op, a, b, expected):
    response = call(api, op, a, b)

    assert response.status_code == 200
    assert response.json() == {"result": pytest.approx(expected)}

def test_divide_returns_fractional_result(api):
    response = call(api, "divide", 1, 3)

    assert response.status_code == 200
    assert response.json()["result"] == pytest.approx(1 / 3)

def test_numeric_strings_are_coerced(api):
    response = call(api, "add", "5", "2")

    assert response.status_code == 200
    assert response.json()["result"] == 7




# Error handling

def test_divide_by_zero_is_a_client_error(api):
    response = call(api, "divide", 10, 0)

    assert response.status_code == 400
    assert response.json() == {"error": "Cannot divide by zero!"}


@pytest.mark.parametrize("op", ["add", "subtract", "multiply", "divide"])
def test_non_numeric_input_is_rejected(api, op):
    response = call(api, op, "abc", 1)

    assert response.status_code == 400
    assert "a" in response.json()["error"]


@pytest.mark.parametrize("op", ["add", "subtract", "multiply", "divide"])
def test_missing_field_is_rejected(api, op):
    response = api.post(f"/{op}", json={"a": 1})

    assert response.status_code == 400
    assert "b" in response.json()["error"]


def test_null_value_is_rejected(api):
    response = call(api, "add", None, 2)

    assert response.status_code == 400
    assert "error" in response.json()


def test_empty_body_reports_both_fields(api):
    response = api.post("/multiply", json={})

    assert response.status_code == 400
    message = response.json()["error"]
    assert "a" in message and "b" in message


def test_unknown_route_returns_404(api):
    response = api.post("/modulo", json={"a": 1, "b": 2})

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_wrong_http_method_is_not_allowed(api):
    response = api.get("/add")

    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}

# Front page

def test_home_page_serves_calculator_html(api):
    response = api.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Calculator" in response.text