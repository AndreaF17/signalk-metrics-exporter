#!/usr/bin/env python3
import requests
import sys
import argparse
import logging
import math

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

    # Add autopilot target heading magnetic (convert from radians to degrees)
    try:
        heading_mag_rad = data["steering"]["autopilot"]["target"]["headingMagnetic"]["value"]
        heading_mag_deg = heading_mag_rad * (180 / math.pi)
        metric_name = "signalk_steering_autopilot_target_heading_magnetic_degrees"
        labels = {}
        if "$source" in data["steering"]["autopilot"]["target"]["headingMagnetic"]:
            labels["source"] = data["steering"]["autopilot"]["target"]["headingMagnetic"]["$source"]
        if "pgn" in data["steering"]["autopilot"]["target"]["headingMagnetic"]:
            labels["pgn"] = str(data["steering"]["autopilot"]["target"]["headingMagnetic"]["pgn"])
        
        label_str = (
            "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
            if labels else ""
        )
        if add_comments:
            metrics.append(f"# HELP {metric_name} Autopilot target heading magnetic in degrees")
            metrics.append(f"# TYPE {metric_name} gauge")
        metrics.append(f"{metric_name}{label_str} {heading_mag_deg:.2f}")
    except Exception:
        pass

    # Add navigation log metric (total distance traveled)
    try:
        nav_log = data["navigation"]["log"]["value"]
        metric_name = "signalk_navigation_log_meters"
        labels = {}
        if "$source" in data["navigation"]["log"]:
            labels["source"] = data["navigation"]["log"]["$source"]
        if "pgn" in data["navigation"]["log"]:
            labels["pgn"] = str(data["navigation"]["log"]["pgn"])
        
        label_str = (
            "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
            if labels else ""
        )
        if add_comments:
            metrics.append(f"# HELP {metric_name} Total distance traveled in meters")
            metrics.append(f"# TYPE {metric_name} gauge")
        metrics.append(f"{metric_name}{label_str} {nav_log}")
    except Exception:
        pass

    # Add water temperature metric (convert from Kelvin to Celsius)
    try:
        water_temp_k = data["environment"]["water"]["temperature"]["value"]
        water_temp_c = water_temp_k - 273.15
        metric_name = "signalk_environment_water_temperature_celsius"
        labels = {}
        if "$source" in data["environment"]["water"]["temperature"]:
            labels["source"] = data["environment"]["water"]["temperature"]["$source"]
        if "pgn" in data["environment"]["water"]["temperature"]:
            labels["pgn"] = str(data["environment"]["water"]["temperature"]["pgn"])
        
        label_str = (
            "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
            if labels else ""
        )
        if add_comments:
            metrics.append(f"# HELP {metric_name} Water temperature in Celsius")
            metrics.append(f"# TYPE {metric_name} gauge")
        metrics.append(f"{metric_name}{label_str} {water_temp_c:.2f}")
    except Exception:
        pass

    # Add navigation nextPoint metrics
    try:
        next_point = data["navigation"]["courseGreatCircle"]["nextPoint"]
        labels = {}
        
        # Distance to next waypoint
        if "distance" in next_point:
            distance = next_point["distance"]["value"]
            metric_name = "signalk_navigation_nextpoint_distance_meters"
            if "$source" in next_point["distance"]:
                labels["source"] = next_point["distance"]["$source"]
            if "pgn" in next_point["distance"]:
                labels["pgn"] = str(next_point["distance"]["pgn"])
            
            label_str = (
                "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
                if labels else ""
            )
            if add_comments:
                metrics.append(f"# HELP {metric_name} Distance to next waypoint in meters")
                metrics.append(f"# TYPE {metric_name} gauge")
            metrics.append(f"{metric_name}{label_str} {distance}")

        # Bearing to next waypoint
        if "bearingTrue" in next_point:
            bearing = next_point["bearingTrue"]["value"]
            metric_name = "signalk_navigation_nextpoint_bearing_true_radians"
            labels_bearing = {}
            if "$source" in next_point["bearingTrue"]:
                labels_bearing["source"] = next_point["bearingTrue"]["$source"]
            if "pgn" in next_point["bearingTrue"]:
                labels_bearing["pgn"] = str(next_point["bearingTrue"]["pgn"])
            
            label_str = (
                "{" + ",".join(f'{k}="{v}"' for k, v in labels_bearing.items()) + "}"
                if labels_bearing else ""
            )
            if add_comments:
                metrics.append(f"# HELP {metric_name} True bearing to next waypoint in radians")
                metrics.append(f"# TYPE {metric_name} gauge")
            metrics.append(f"{metric_name}{label_str} {bearing}")

        # Velocity Made Good (convert from m/s to knots)
        if "velocityMadeGood" in next_point:
            vmg_ms = next_point["velocityMadeGood"]["value"]
            vmg_knots = vmg_ms * 1.94384  # Convert m/s to knots
            metric_name = "signalk_navigation_nextpoint_velocity_made_good_knots"
            labels_vmg = {}
            if "$source" in next_point["velocityMadeGood"]:
                labels_vmg["source"] = next_point["velocityMadeGood"]["$source"]
            if "pgn" in next_point["velocityMadeGood"]:
                labels_vmg["pgn"] = str(next_point["velocityMadeGood"]["pgn"])
            
            label_str = (
                "{" + ",".join(f'{k}="{v}"' for k, v in labels_vmg.items()) + "}"
                if labels_vmg else ""
            )
            if add_comments:
                metrics.append(f"# HELP {metric_name} Velocity Made Good towards next waypoint in knots")
                metrics.append(f"# TYPE {metric_name} gauge")
            metrics.append(f"{metric_name}{label_str} {vmg_knots:.2f}")

        # Time to Go
        if "timeToGo" in next_point:
            ttg = next_point["timeToGo"]["value"]
            metric_name = "signalk_navigation_nextpoint_time_to_go_seconds"
            labels_ttg = {}
            if "$source" in next_point["timeToGo"]:
                labels_ttg["source"] = next_point["timeToGo"]["$source"]
            if "pgn" in next_point["timeToGo"]:
                labels_ttg["pgn"] = str(next_point["timeToGo"]["pgn"])
            
            label_str = (
                "{" + ",".join(f'{k}="{v}"' for k, v in labels_ttg.items()) + "}"
                if labels_ttg else ""
            )
            if add_comments:
                metrics.append(f"# HELP {metric_name} Time to reach next waypoint in seconds")
                metrics.append(f"# TYPE {metric_name} gauge")
            metrics.append(f"{metric_name}{label_str} {ttg}")

        # Next waypoint position
        if "position" in next_point and "value" in next_point["position"]:
            position = next_point["position"]["value"]
            labels_pos = {}
            if "$source" in next_point["position"]:
                labels_pos["source"] = next_point["position"]["$source"]
            if "pgn" in next_point["position"]:
                labels_pos["pgn"] = str(next_point["position"]["pgn"])
            
            if "longitude" in position and position["longitude"] is not None:
                metric_name = "signalk_navigation_nextpoint_longitude_degrees"
                label_str = (
                    "{" + ",".join(f'{k}="{v}"' for k, v in labels_pos.items()) + "}"
                    if labels_pos else ""
                )
                if add_comments:
                    metrics.append(f"# HELP {metric_name} Longitude of next waypoint in degrees")
                    metrics.append(f"# TYPE {metric_name} gauge")
                metrics.append(f"{metric_name}{label_str} {position['longitude']}")
            
            if "latitude" in position and position["latitude"] is not None:
                metric_name = "signalk_navigation_nextpoint_latitude_degrees"
                label_str = (
                    "{" + ",".join(f'{k}="{v}"' for k, v in labels_pos.items()) + "}"
                    if labels_pos else ""
                )
                if add_comments:
                    metrics.append(f"# HELP {metric_name} Latitude of next waypoint in degrees")
                    metrics.append(f"# TYPE {metric_name} gauge")
                metrics.append(f"{metric_name}{label_str} {position['latitude']}")

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