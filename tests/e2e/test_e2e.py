# tests/e2e/test_e2e.py

import pytest
from playwright.sync_api import expect

URL = 'http://localhost:8000'


def calc(page, a, b, op):
    """Open the calculator, fill both inputs, and click the operation button."""
    page.goto(URL)
    page.fill('#a', a)
    page.fill('#b', b)
    page.click(f'button:text("{op}")')


@pytest.mark.e2e
def test_hello_world(page, fastapi_server):
    page.goto(URL)
    expect(page.locator('h1')).to_have_text('Hello World')


@pytest.mark.e2e
@pytest.mark.parametrize("a, b, op, expected", [
    ("10", "5", "Add", "Result: 15"),
    ("10", "5", "Subtract", "Result: 5"),
    ("10", "5", "Multiply", "Result: 50"),
    ("10", "2", "Divide", "Result: 5"),
])
def test_calculator_operations(page, fastapi_server, a, b, op, expected):
    calc(page, a, b, op)
    expect(page.locator('#result')).to_have_text(expected)


@pytest.mark.e2e
def test_calculator_divide_by_zero(page, fastapi_server):
    calc(page, "10", "0", "Divide")
    expect(page.locator('#result')).to_have_text('Error: Cannot divide by zero!')


@pytest.mark.e2e
def test_empty_inputs_show_error(page, fastapi_server):
    page.goto(URL)
    page.click('button:text("Add")')
    expect(page.locator('#result')).to_contain_text('Error')