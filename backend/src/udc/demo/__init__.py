"""Retail demo: three fictional sources for the Maison Vellandre product catalogue.

``data/sources/*.json`` holds each source's schema and sample rows;
``data/recorded/*.json`` holds the mapping proposals loaded at seed time, so the
demo runs without calling the Claude API and gives the same result every time.
Each recorded file says in ``_provenance`` whether it came from a real
inference run or was written by hand.
"""

from udc.demo.seed import load_demo_sources, load_recorded, record_demo, seed_demo

__all__ = ["load_demo_sources", "load_recorded", "record_demo", "seed_demo"]
