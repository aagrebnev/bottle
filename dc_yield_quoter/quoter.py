"""Yield calculation engine for dc_yield_quoter."""

import math


def simple_yield(principal, rate, years):
    """Calculate simple interest yield.

    Returns the future value and total interest earned.
    """
    interest = principal * rate * years
    future_value = principal + interest
    return {
        "type": "simple_yield",
        "principal": principal,
        "annual_rate": rate,
        "years": years,
        "interest_earned": round(interest, 6),
        "future_value": round(future_value, 6),
        "effective_yield_pct": round((interest / principal) * 100, 4),
    }


def compound_yield(principal, rate, years, compounding_periods=12):
    """Calculate compound interest yield.

    compounding_periods: number of times compounded per year (12=monthly, 4=quarterly, 1=annual).
    """
    n = compounding_periods
    future_value = principal * (1 + rate / n) ** (n * years)
    interest = future_value - principal
    apy = (1 + rate / n) ** n - 1
    return {
        "type": "compound_yield",
        "principal": principal,
        "annual_rate": rate,
        "years": years,
        "compounding_periods_per_year": n,
        "interest_earned": round(interest, 6),
        "future_value": round(future_value, 6),
        "apy_pct": round(apy * 100, 4),
    }


def apr_to_apy(apr, compounding_periods=12):
    """Convert APR (Annual Percentage Rate) to APY (Annual Percentage Yield)."""
    n = compounding_periods
    apy = (1 + apr / n) ** n - 1
    return {
        "type": "apr_to_apy",
        "apr_pct": round(apr * 100, 4),
        "apy_pct": round(apy * 100, 4),
        "compounding_periods_per_year": n,
    }


def apy_to_apr(apy, compounding_periods=12):
    """Convert APY to APR."""
    n = compounding_periods
    apr = n * ((1 + apy) ** (1 / n) - 1)
    return {
        "type": "apy_to_apr",
        "apy_pct": round(apy * 100, 4),
        "apr_pct": round(apr * 100, 4),
        "compounding_periods_per_year": n,
    }


def discount_yield(face_value, purchase_price, days_to_maturity):
    """Calculate bank discount yield (used for T-bills and similar instruments)."""
    discount = face_value - purchase_price
    discount_yield_val = (discount / face_value) * (360 / days_to_maturity)
    return {
        "type": "discount_yield",
        "face_value": face_value,
        "purchase_price": purchase_price,
        "days_to_maturity": days_to_maturity,
        "discount": round(discount, 6),
        "discount_yield_pct": round(discount_yield_val * 100, 4),
    }


def bond_equivalent_yield(face_value, purchase_price, days_to_maturity):
    """Calculate bond equivalent yield (BEY) from a discount instrument."""
    discount = face_value - purchase_price
    bey = (discount / purchase_price) * (365 / days_to_maturity)
    return {
        "type": "bond_equivalent_yield",
        "face_value": face_value,
        "purchase_price": purchase_price,
        "days_to_maturity": days_to_maturity,
        "bey_pct": round(bey * 100, 4),
    }


def current_yield(annual_coupon, market_price):
    """Calculate current yield for a bond."""
    cy = annual_coupon / market_price
    return {
        "type": "current_yield",
        "annual_coupon": annual_coupon,
        "market_price": market_price,
        "current_yield_pct": round(cy * 100, 4),
    }


def continuous_compound_yield(principal, rate, years):
    """Calculate yield with continuous compounding."""
    future_value = principal * math.exp(rate * years)
    interest = future_value - principal
    return {
        "type": "continuous_compound_yield",
        "principal": principal,
        "annual_rate": rate,
        "years": years,
        "interest_earned": round(interest, 6),
        "future_value": round(future_value, 6),
        "effective_annual_rate_pct": round((math.exp(rate) - 1) * 100, 4),
    }
