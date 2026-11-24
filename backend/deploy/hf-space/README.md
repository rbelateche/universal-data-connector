---
title: UDC API (demo)
emoji: 🧩
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
short_description: Universal Data Connector API with a fictional retail demo
---

# Universal Data Connector: demo API

The REST API of the [Universal Data Connector](https://github.com/rbelateche/universal-data-connector),
running with a fictional retail scenario (*Maison Vellandre*: an ERP export, a PIM and an
e-commerce catalogue mapped to one Product model).

It is the backend of the UDC MCP App, which brings mapping review into Claude and ChatGPT.
Every route except `/health` requires an `X-Api-Key` header. All data is fictional and is
reset when the Space restarts.
