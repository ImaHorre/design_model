"""
extract_experiments.py — Raw Data → stepgen compare CSV

Extracts metadata from filenames, aggregates per-DFU diameter and frequency
measurements, and writes a standardised experiments CSV for `stepgen compare`.

Usage:
    python extract_experiments.py <data_dir> [--out experiments.csv]
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

FILENAME_RE = re.compile(
    r"^(\d{4})_(\d{4})_(W\d+)_(\d+)_(\d+)_([A-Za-z]+)"
    r"_(\d+(?:-\d+)?mlhr\d+(?:-\d+)?mbar)"
    r"_(DFU\w+?)(?:_(ROI\d+))?"
    r"_(droplet_annotations|frequency_analysis)"
    r".*\.(csv|txt)$"
)


def parse_filename(fname: str) -> dict | None:
    """Return parsed metadata dict, or None if filename does not match."""
    m = FILENAME_RE.match(fname)
    if not m:
        return None
    test_date, mfg_date, wafer, shim, replica, fluids, flow_params, \
        dfu_label, roi_label, file_type, _ = m.groups()
    Qw, Po = parse_flow_params(flow_params)
    return {
        "test_date": test_date,
        "mfg_date": mfg_date,
        "wafer": wafer,
        "shim": shim,
        "replica": replica,
        "fluids": fluids,
        "flow_params": flow_params,
        "dfu_label": dfu_label,
        "roi_label": roi_label,
        "file_type": file_type,
        "Qw_in_mlhr": Qw,
        "Po_in_mbar": Po,
        "device_id": f"{wafer}_{shim}_{replica}",
    }


# ---------------------------------------------------------------------------
# Flow params parsing
# ---------------------------------------------------------------------------

FLOW_RE = re.compile(r"^(\d+(?:-\d+)?)mlhr(\d+(?:-\d+)?)mbar$")


def parse_flow_params(token: str) -> tuple[float, float]:
    """Parse '1-5mlhr400mbar' → (1.5, 400.0)."""
    m = FLOW_RE.match(token)
    if not m:
        raise ValueError(f"Cannot parse flow params: {token!r}")
    Qw = float(m.group(1).replace("-", "."))
    Po = float(m.group(2).replace("-", "."))
    return Qw, Po


# ---------------------------------------------------------------------------
# DFU → fractional position
# ---------------------------------------------------------------------------

def dfu_to_position(label: str) -> float:
    """Map DFU label to fractional channel position (0–1)."""
    low = label.lower()
    if low in ("start", "dfu_start"):
        return 0.0
    if low in ("end", "dfu_end"):
        return 1.0
    m = re.match(r"^dfu(\d+)$", low)
    if m:
        return int(m.group(1)) / 7.0
    raise ValueError(f"Unrecognised DFU label: {label!r}")


# ---------------------------------------------------------------------------
# Per-file data extraction
# ---------------------------------------------------------------------------

def extract_diameter(csv_path: Path) -> float:
    """Return mean diameter_um from a droplet annotations CSV."""
    df = pd.read_csv(csv_path)
    return float(df["diameter_um"].mean())


FREQ_RE = re.compile(
    r"Frequency Method 2 \(freq from avg time\):\s*([\d.]+)\s*Hz"
)


def extract_frequency(txt_path: Path) -> float:
    """Return Method-2 frequency (Hz) from a frequency analysis TXT file."""
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    m = FREQ_RE.search(text)
    if not m:
        raise ValueError(f"Frequency not found in {txt_path.name}")
    return float(m.group(1))


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------

def build_experiments(data_dir: Path) -> pd.DataFrame:
    """
    Scan data_dir for matching files, aggregate per (device_id, Qw, Po, DFU),
    and return a DataFrame with columns:
        device_id, Po_in_mbar, Qw_in_mlhr, position,
        droplet_diameter_um, frequency_hz
    """
    # key → {"diameters": [...], "frequencies": [...], meta}
    records: dict[tuple, dict] = defaultdict(lambda: {
        "diameters": [], "frequencies": [], "meta": None
    })

    skipped = []
    for path in sorted(data_dir.iterdir()):
        if not path.is_file():
            continue
        info = parse_filename(path.name)
        if info is None:
            skipped.append(path.name)
            continue

        key = (info["device_id"], info["Qw_in_mlhr"], info["Po_in_mbar"], info["dfu_label"])
        rec = records[key]
        rec["meta"] = info

        if info["file_type"] == "droplet_annotations":
            try:
                d = extract_diameter(path)
                rec["diameters"].append(d)
            except Exception as e:
                print(f"  [warn] {path.name}: {e}", file=sys.stderr)

        elif info["file_type"] == "frequency_analysis":
            try:
                f = extract_frequency(path)
                rec["frequencies"].append(f)
            except Exception as e:
                print(f"  [warn] {path.name}: {e}", file=sys.stderr)

    if skipped:
        print(f"Skipped {len(skipped)} non-matching file(s).", file=sys.stderr)

    rows = []
    for (device_id, Qw, Po, dfu_label), rec in sorted(records.items()):
        try:
            position = dfu_to_position(dfu_label)
        except ValueError as e:
            print(f"  [warn] {e}", file=sys.stderr)
            position = float("nan")

        diameter = float(np.mean(rec["diameters"])) if rec["diameters"] else float("nan")
        frequency = float(np.mean(rec["frequencies"])) if rec["frequencies"] else float("nan")

        rows.append({
            "device_id": device_id,
            "Po_in_mbar": Po,
            "Qw_in_mlhr": Qw,
            "position": position,
            "droplet_diameter_um": diameter,
            "frequency_hz": frequency,
        })

    return pd.DataFrame(rows, columns=[
        "device_id", "Po_in_mbar", "Qw_in_mlhr", "position",
        "droplet_diameter_um", "frequency_hz",
    ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract experimental data from raw files into a stepgen compare CSV."
    )
    parser.add_argument("data_dir", type=Path, help="Directory containing raw data files.")
    parser.add_argument("--out", type=Path, default=Path("experiments.csv"),
                        help="Output CSV path (default: experiments.csv).")
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        print(f"Error: {args.data_dir} is not a directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {args.data_dir.resolve()} ...")
    df = build_experiments(args.data_dir)

    if df.empty:
        print("No matching files found. Check filenames match the expected pattern.")
        sys.exit(1)

    # Summary table
    summary = (
        df.groupby(["device_id", "Qw_in_mlhr", "Po_in_mbar"])
        .agg(
            n_positions=("position", "count"),
            n_diameter=("droplet_diameter_um", lambda x: x.notna().sum()),
            n_freq=("frequency_hz", lambda x: x.notna().sum()),
        )
        .reset_index()
    )
    print("\nSummary:")
    print(summary.to_string(index=False))

    df.to_csv(args.out, index=False)
    print(f"\nWrote {len(df)} row(s) to {args.out}")


if __name__ == "__main__":
    main()
