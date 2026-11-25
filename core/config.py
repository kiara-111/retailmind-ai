"""Reads settings from environment variables (scheduler) or Streamlit secrets (web app)."""
import os

TIMEZONE = "Europe/Berlin"
DEFAULT_MODEL = "claude-sonnet-5-5"
# USD per million tokens, list price of Claude Sonnet 5.5 (Nov 2026). Used to show the cost of each run.
PRICE_IN_PER_MTOK = 2.0
PRICE_OUT_PER_MTOK = 10.0


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens or 0) / 1e6 * PRICE_IN_PER_MTOK + (output_tokens or 0) / 1e6 * PRICE_OUT_PER_MTOK


def get(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value.strip()
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return default


def has(*names: str) -> bool:
    return all(bool(get(n)) for n in names)
