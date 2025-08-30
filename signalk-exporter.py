#!/usr/bin/env python3
import requests
import sys
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)




def flatten(prefix, data, metrics, base_labels):
    if isinstance(data, dict):
        if "value" in data and isinstance(data["value"], (int, float)):
            # Determine type and unit for metric name
            unit = None
            if "meta" in data and "units" in data["meta"]:
                unit = data["meta"]["units"].replace("/", "_per_").replace(" ", "_")
            # Try to infer type from prefix (last part)
            type_part = prefix.split("_")[-1] if prefix else "value"
            # Prometheus metric name: signalk_TYPE_UNIT
            metric_name = f"signalk_{type_part}"
            if unit:
                metric_name += f"_{unit}"
            metric_name = metric_name.lower()

            labels = base_labels.copy()
            if "$source" in data:
                labels["source"] = data["$source"]
            if "pgn" in data:
                labels["pgn"] = str(data["pgn"])
            # Remove 'units' label if present
            # Convert speed units to knots if needed
            value = data["value"]
            if unit:
                speed_units = ["m_s", "m_per_s", "km_h", "km_per_h", "kn", "knots"]
                if type_part.lower().startswith("speed") or "speed" in type_part.lower():
                    if unit in ["m_s", "m_per_s"]:
                        value = value * 1.94384  # m/s to knots
                        metric_name = metric_name.replace("m_s", "knots").replace("m_per_s", "knots")
                    elif unit in ["km_h", "km_per_h"]:
                        value = value * 0.539957  # km/h to knots
                        metric_name = metric_name.replace("km_h", "knots").replace("km_per_h", "knots")
                    elif unit in ["kn", "knots"]:
                        metric_name = metric_name.replace("kn", "knots")
            label_str = (
                "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
                if labels else ""
            )
            metrics.append(
                f"# HELP {metric_name} SignalK metric {metric_name}\n"
                f"# TYPE {metric_name} gauge\n"
                f"{metric_name}{label_str} {value}"
            )
        else:
            for k, v in data.items():
                if k in ("meta", "$source", "timestamp", "pgn"):
                    continue
                new_prefix = f"{prefix}_{k}" if prefix else k
                flatten(new_prefix, v, metrics, base_labels)
    elif isinstance(data, (int, float)):
        type_part = prefix.split("_")[-1] if prefix else "value"
        metric_name = f"signalk_{type_part}"
        metric_name = metric_name.lower()
        labels = base_labels.copy()
        label_str = (
            "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
            if labels else ""
        )
        metrics.append(
            f"# HELP {metric_name} SignalK metric {metric_name}\n"
            f"# TYPE {metric_name} gauge\n"
            f"{metric_name}{label_str} {data}"
        )

def fetch_signalk(signalk_url):
    try:
        resp = requests.get(signalk_url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as http_err:
        if resp.status_code == 404:
            logging.warning("Sensors not turned on")
            sys.exit(0)
        else:
            logging.error(f"HTTP error occurred: {http_err}")
            raise
    except requests.exceptions.RequestException as err:
        logging.error(f"Request failed: {err}")
        raise

def convert_to_prometheus(data):
    metrics = []
    base_labels = {}
    flatten("", data, metrics, base_labels)
    return "\n".join(metrics)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export SignalK vessel data as Prometheus metrics.")
    parser.add_argument(
        "--signalk-url",
        type=str,
        required=True,
        help="SignalK API URL to fetch vessel data eg: http://127.0.0.1:3000/signalk/v1/api/vessels/self",
    )
    args = parser.parse_args()
    try:
        data = fetch_signalk(args.signalk_url)
        prom_text = convert_to_prometheus(data)
        print(prom_text)
    except Exception as e:
        logging.error(f"Error: {e}")
        sys.exit(1)