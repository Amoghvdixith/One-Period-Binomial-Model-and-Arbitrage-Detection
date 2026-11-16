"""Shared fixtures and independently specified expected values.

The baseline targets below are derived by hand (see docs/validation.md), not
by calling the package:

    S0 = 100, u = 1.12, d = 0.92, r = 0.02, K = 100
    R = 1.02, q = (1.02 - 0.92) / 0.20 = 0.5
    Su = 112, Sd = 92
    call payoffs (12, 0)  -> C = 0.5*12/1.02 = 6/1.02
    put payoffs  (0, 8)   -> P = 0.5*8/1.02  = 4/1.02
    call Delta = 12/20 = 0.6, call B = (1.12*0 - 0.92*12)/(0.20*1.02) = -11.04/0.204
    put  Delta = -8/20 = -0.4, put  B = (1.12*8 - 0)/(0.20*1.02)     =  8.96/0.204
    digital (payout 1) payoffs (1, 0) -> 0.5/1.02
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from binomial_arbitrage import MarketParams, classify_market

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Numerical tolerances used by the tests (currency units / dimensionless).
ABS_TOL = 1e-12
REL_TOL = 1e-12

BASELINE = {"S0": 100, "u": 1.12, "d": 0.92, "r": 0.02, "K": 100}

EXPECTED = {
    "R": Fraction(102, 100),
    "q": Fraction(1, 2),
    "call_price": Fraction(6) / Fraction(102, 100),
    "put_price": Fraction(4) / Fraction(102, 100),
    "digital_price": Fraction(1, 2) / Fraction(102, 100),
    "call_delta": Fraction(6, 10),
    "call_B": Fraction(-1104, 100) / Fraction(204, 1000),
    "put_delta": Fraction(-4, 10),
    "put_B": Fraction(896, 100) / Fraction(204, 1000),
}


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def baseline_params() -> MarketParams:
    return MarketParams.create(BASELINE["S0"], BASELINE["u"], BASELINE["d"], BASELINE["r"])


@pytest.fixture
def baseline_classification(baseline_params):
    return classify_market(baseline_params)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Redact the machine hostname that pytest writes into JUnit XML.

    The saved test results are meant to be shareable; the hostname is a
    personal identifier and carries no test information. Counts, names and
    outcomes are left untouched.
    """
    import re

    xmlpath = getattr(session.config.option, "xmlpath", None)
    if not xmlpath:
        return
    path = Path(xmlpath)
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        path.write_text(re.sub(r'hostname="[^"]*"', 'hostname="redacted"', text), encoding="utf-8")


def approx(value, rel: float = REL_TOL, abs_: float = ABS_TOL):
    """pytest.approx with the project's default tolerances; accepts Fractions."""
    return pytest.approx(float(value), rel=rel, abs=abs_)
