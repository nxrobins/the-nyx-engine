"""The Consequence Calibration Harness — deterministic, offline measurement.

This package drives many scripted + adversarial lives through the REAL
NyxKernel in mock mode to death-or-cap and emits friction-metric
distributions as a checked-in regression artifact. It MEASURES the
consequence layer; it changes no game behaviour.

Hard boundary (CAL-E8): nothing under ``app/`` imports ``sim``. The
harness is a one-way consumer of the engine, never a dependency of it.

The optimization target is FRICTION (exploit precision/recall,
doom-escape rate, death-cause mix, keyword smuggle-through) — NEVER
retention or player satisfaction. See README.md.
"""
