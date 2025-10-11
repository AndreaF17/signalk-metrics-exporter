# signalk-metrics-exporter

A small CLI utility that fetches a Signal K vessel object and converts it into Prometheus text-format metrics.

This repository contains a single script, `signalk-exporter.py`, which queries a Signal K server (v1 API) for a vessel's data and prints a set of Prometheus-compatible metrics to stdout. The script attempts to make sensible unit conversions (for example: speeds to knots, water temperature from Kelvin to Celsius) and excludes a number of noisy / non-numeric fields.

## Features

- Fetches Signal K JSON from the v1 API endpoint for a vessel (for example: `/signalk/v1/api/vessels/self`).
- Flattens nested Signal K paths into metric names in the form `signalk_<path>[_<unit>]`.
- Adds labels for `$source` and `pgn` when present.
- Converts common units:
	- speeds (m/s, km/h) -> knots
	- water temperature (Kelvin) -> Celsius
- Adds a few handcrafted metrics for commonly useful values (autopilot state, autopilot target heading in degrees, navigation log, next waypoint metrics).
- Skips metrics where the Signal K `$source` is `defaults` and omits common non-numeric leaf keys like `id`/`name`/`value`.

## Requirements

- Python 3.7+
- Uses the `requests` library. Install it with pip if not already available.

Example:

```bash
python3 -m pip install -r requirements.txt
```

## Virtual environment (recommended)

It's recommended to run the exporter inside a virtual environment to avoid polluting your system Python.

Create and activate a venv, then install dependencies from `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

To deactivate the venv later:

```bash
deactivate
```

## Usage

Run the script with the Signal K vessel API URL:

```bash
./signalk-exporter.py -u http://127.0.0.1:3000/signalk/v1/api/vessels/self
```

Options

- `-u`, `--signalk-url` (required) — Signal K API URL for the vessel object.
- `-n`, `--no-comments` — Do not include Prometheus `# HELP` and `# TYPE` comment lines in the output.

Notes

- The script exits with code 0 if the Signal K endpoint returns HTTP 404 (this is treated as "Sensors not turned on").
- Numeric values found in nested objects are emitted as gauges.
- Some fields are explicitly excluded to avoid generating useless metrics (for example `id`, `name`, `value` leaf keys and AIS sensor angles `fromBow` / `fromCenter`).

## Example output

Metric names are lower-cased and use `signalk_` as a prefix. Labels are added when `$source`/`pgn` are present.

Example (truncated):

```
# HELP signalk_navigation_log_meters Total distance traveled in meters
# TYPE signalk_navigation_log_meters gauge
signalk_navigation_log_meters{source="nmea0183",pgn="123456"} 12345.67
# HELP signalk_environment_water_temperature_celsius Water temperature in Celsius
# TYPE signalk_environment_water_temperature_celsius gauge
signalk_environment_water_temperature_celsius{source="sensor1"} 12.34
# HELP signalk_steering_autopilot_state Autopilot state: 0=standby, 1=active
# TYPE signalk_steering_autopilot_state gauge
signalk_steering_autopilot_state 1
```

## Conversions and special cases

- Speed units: `m/s` and `m_per_s` are converted to `knots` using 1 m/s = 1.94384 knots. `km/h` is converted to `knots` using 1 km/h = 0.539957.
- Water temperature is converted from Kelvin to Celsius where the script detects Kelvin values in the expected `environment.water.temperature` path.
- The script adds a convenience metric `signalk_steering_autopilot_state` which is `0` for `standby` and `1` for other states.

## Running as a Prometheus target

This script prints metrics to stdout. To use it with Prometheus you can run it behind a lightweight HTTP server that serves the output, or wrap the logic into a long-running exporter that periodically fetches Signal K and exposes `/metrics`.

A simple approach for testing is to run the script periodically with cron and have a small HTTP endpoint return the last output, or use a process like `socat`/`inetd`/`ncat` to serve the script's output.

## Development notes

- The script intentionally avoids creating a long-running server; it's a simple conversion tool. If you want a production exporter, consider adding a small HTTP server (Flask, FastAPI) with caching and a scrape-ready `/metrics` endpoint.
- The code is kept minimal and only depends on `requests`.

## Contact

If you have improvements, file an issue or a PR with suggested changes.
