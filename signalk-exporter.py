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




def flatten(prefix, data, metrics, base_labels, add_comments=True):
    if isinstance(data, dict):
        # If this is a leaf node with a numeric value
        if "value" in data and isinstance(data["value"], (int, float)):
            # Build metric name from full path
            metric_name = f"signalk_{prefix}" if prefix else "signalk"
            unit = None
            if "meta" in data and "units" in data["meta"]:
                unit = data["meta"]["units"].replace("/", "_per_").replace(" ", "_")
            if unit:
                metric_name += f"_{unit}"
            metric_name = metric_name.lower()

            # Skip metrics where $source is 'defaults'
            if "$source" in data and data["$source"] == "defaults":
                return
            labels = base_labels.copy()
            if "$source" in data:
                labels["source"] = data["$source"]
            if "pgn" in data:
                labels["pgn"] = str(data["pgn"])

            value = data["value"]
            # Convert speed units to knots if needed
            if unit:
                if ("speed" in metric_name or "speed" in prefix):
                    if unit in ["m_s", "m_per_s"]:
                        value = value * 1.94384
                        metric_name = metric_name.replace("m_s", "knots").replace("m_per_s", "knots")
                    elif unit in ["km_h", "km_per_h"]:
                        value = value * 0.539957
                        metric_name = metric_name.replace("km_h", "knots").replace("km_per_h", "knots")
                    elif unit in ["kn", "knots"]:
                        metric_name = metric_name.replace("kn", "knots")

            label_str = (
                "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
                if labels else ""
            )
            # Exclude metrics for id, name, value at leaf, and for frombow/fromcenter under sensors_ais
            last = prefix.split("_")[-1] if prefix else ""
            if last in ("id", "name", "value"):
                return
            # Exclude signalk_sensors_ais_frombow and signalk_sensors_ais_fromcenter robustly
            if metric_name in ("signalk_sensors_ais_frombow", "signalk_sensors_ais_fromcenter"):
                return
            if add_comments:
                metrics.append(f"# HELP {metric_name} SignalK metric {metric_name}")
                metrics.append(f"# TYPE {metric_name} gauge")
            metrics.append(f"{metric_name}{label_str} {value}")
        # If this is a leaf node with a value dict (e.g., { value: { maximum: 2.25 } })
        elif "value" in data and isinstance(data["value"], dict):
            # Skip metrics where $source is 'defaults'
            if "$source" in data and data["$source"] == "defaults":
                return
            for subk, subv in data["value"].items():
                # Only process numeric subkeys, skip id/name/value, and frombow/fromcenter under sensors_ais
                if subk in ("id", "name", "value") or not isinstance(subv, (int, float)):
                    continue
                # Exclude signalk_sensors_ais_frombow and signalk_sensors_ais_fromcenter robustly
                test_metric_name = f"signalk_{prefix}_{subk}" if prefix else f"signalk_{subk}"
                test_metric_name = test_metric_name.lower()
                if test_metric_name in ("signalk_sensors_ais_frombow", "signalk_sensors_ais_fromcenter"):
                    continue
                metric_name = f"signalk_{prefix}_{subk}" if prefix else f"signalk_{subk}"
                unit = None
                if "meta" in data and "properties" in data["meta"] and subk in data["meta"]["properties"]:
                    meta_prop = data["meta"]["properties"][subk]
                    if "units" in meta_prop:
                        unit = meta_prop["units"].replace("/", "_per_").replace(" ", "_")
                if unit:
                    metric_name += f"_{unit}"
                metric_name = metric_name.lower()
                labels = base_labels.copy()
                if "$source" in data:
                    labels["source"] = data["$source"]
                if "pgn" in data:
                    labels["pgn"] = str(data["pgn"])
                value = subv
                # Convert speed units to knots if needed
                if unit:
                    if ("speed" in metric_name or "speed" in prefix):
                        if unit in ["m_s", "m_per_s"]:
                            value = value * 1.94384
                            metric_name = metric_name.replace("m_s", "knots").replace("m_per_s", "knots")
                        elif unit in ["km_h", "km_per_h"]:
                            value = value * 0.539957
                            metric_name = metric_name.replace("km_h", "knots").replace("km_per_h", "knots")
                        elif unit in ["kn", "knots"]:
                            metric_name = metric_name.replace("kn", "knots")
                label_str = (
                    "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
                    if labels else ""
                )
                if add_comments:
                    metrics.append(f"# HELP {metric_name} SignalK metric {metric_name}")
                    metrics.append(f"# TYPE {metric_name} gauge")
                metrics.append(f"{metric_name}{label_str} {value}")
        else:
            for k, v in data.items():
                if k in ("meta", "$source", "timestamp", "pgn"):
                    continue
                new_prefix = f"{prefix}_{k}" if prefix else k
                flatten(new_prefix, v, metrics, base_labels, add_comments)
    elif isinstance(data, (int, float)):
        # Only process if not id, name, value
        last = prefix.split("_")[-1] if prefix else ""
        if last in ("id", "name", "value"):
            return
        metric_name = f"signalk_{prefix}" if prefix else "signalk"
        metric_name = metric_name.lower()
        labels = base_labels.copy()
        label_str = (
            "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
            if labels else ""
        )
        if add_comments:
            metrics.append(f"# HELP {metric_name} SignalK metric {metric_name}")
            metrics.append(f"# TYPE {metric_name} gauge")
        metrics.append(f"{metric_name}{label_str} {data}")

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

def convert_to_prometheus(data, add_comments=True):
    metrics = []
    base_labels = {}
    flatten("", data, metrics, base_labels, add_comments)

    # Add autopilot state metric if present
    try:
        autopilot_state = data["steering"]["autopilot"]["state"]["value"]
        autopilot_val = 0 if str(autopilot_state).lower() == "standby" else 1
        metric_name = "signalk_steering_autopilot_state"
        if add_comments:
            metrics.append(f"# HELP {metric_name} Autopilot state: 0=standby, 1=active")
            metrics.append(f"# TYPE {metric_name} gauge")
        metrics.append(f"{metric_name} {autopilot_val}")
    except Exception:
        pass
    return "\n".join(metrics)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export SignalK vessel data as Prometheus metrics.")
    parser.add_argument(
        "-u", "--signalk-url",
        type=str,
        required=True,
        help="SignalK API URL to fetch vessel data eg: http://127.0.0.1:3000/signalk/v1/api/vessels/self",
    )
    parser.add_argument(
        "-n", "--no-comments",
        action="store_true",
        help="Do not include HELP/TYPE comments in the Prometheus output."
    )
    args = parser.parse_args()
    try:
        data = fetch_signalk(args.signalk_url)
        prom_text = convert_to_prometheus(data, add_comments=not args.no_comments)
        print(prom_text)
    except Exception as e:
        logging.error(f"Error: {e}")
        sys.exit(1)