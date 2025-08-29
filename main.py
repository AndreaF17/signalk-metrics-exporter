#!/usr/bin/env python3
import requests
import sys
import argparse



def extract_global_labels(data):
    labels = {}
    for key in ("mmsi", "uuid", "name"):
        if key in data and isinstance(data[key], str):
            labels[key] = data[key]
    return labels

def flatten(prefix, data, metrics, base_labels):
    if isinstance(data, dict):
        if "value" in data and isinstance(data["value"], (int, float)):
            metric_name = prefix.replace(".", "_").replace("-", "_")

            labels = base_labels.copy()
            if "$source" in data:
                labels["source"] = data["$source"]
            if "pgn" in data:
                labels["pgn"] = str(data["pgn"])
            if "meta" in data and "units" in data["meta"]:
                labels["units"] = data["meta"]["units"]

            label_str = (
                "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
                if labels else ""
            )

            metrics.append(
                f"# HELP {metric_name} SignalK metric {metric_name}\n"
                f"# TYPE {metric_name} gauge\n"
                f"{metric_name}{label_str} {data['value']}"
            )
        else:
            for k, v in data.items():
                if k in ("meta", "$source", "timestamp", "pgn"):
                    continue
                new_prefix = f"{prefix}_{k}" if prefix else k
                flatten(new_prefix, v, metrics, base_labels)
    elif isinstance(data, (int, float)):
        metric_name = prefix.replace(".", "_").replace("-", "_")
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
    resp = requests.get(signalk_url, timeout=5)
    resp.raise_for_status()
    return resp.json()

def convert_to_prometheus(data):
    metrics = []
    base_labels = extract_global_labels(data)
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
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)