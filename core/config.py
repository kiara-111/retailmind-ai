"""Reads settings from environment variables (scheduler) or Streamlit secrets (web app)."""
import os

TIMEZONE = "Europe/Berlin"
DEFAULT_MODEL = "claude-sonnet-5-5"


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
