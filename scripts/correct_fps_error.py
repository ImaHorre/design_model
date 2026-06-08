"""
correct_fps_error.py
====================
One-off correction for the fps=25 analysis error.

All stage-timing CSVs produced before 2026-06-08 were analyzed at 25 fps,
but the videos were recorded at 50 fps.  This makes all Stage*_s values 2×
too long and all derived frequencies 2× too low.

Fix: multiply Stage1_s, Stage2_s, Stage3_s by 0.5.

Usage (correct all rows):
    python scripts/correct_fps_error.py path/to/stage_timings.csv

Usage (skip device 1B — genuinely 25fps in the mfg050526 consistency data):
    python scripts/correct_fps_error.py path/to/stage_timings_Mfg050526_combined.csv --skip-device V5-30-260413-1B

The script writes the corrected file in-place and prints a summary.
"""

import argparse
import pandas as pd
import sys

TIMING_COLS = ["Stage1_s", "Stage2_s", "Stage3_s"]


def main():
    parser = argparse.ArgumentParser(description="Correct fps=25→50 timing error in stage_timings CSV")
    parser.add_argument("csv", help="Path to stage_timings CSV")
    parser.add_argument("--skip-device", metavar="DEVICE_ID",
                        help="DeviceID to leave untouched (e.g. V5-30-260413-1B for the 25fps device)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print summary without writing changes")
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    print(f"Loaded {len(df)} rows from: {args.csv}")

    if args.skip_device:
        if "DeviceID" not in df.columns:
            print("ERROR: --skip-device requires a 'DeviceID' column in the CSV", file=sys.stderr)
            sys.exit(1)
        mask_to_correct = df["DeviceID"] != args.skip_device
        n_skipped = (~mask_to_correct).sum()
        print(f"Skipping {n_skipped} rows with DeviceID == '{args.skip_device}' (genuine 25fps)")
    else:
        mask_to_correct = pd.Series([True] * len(df), index=df.index)
        n_skipped = 0

    n_to_correct = mask_to_correct.sum()
    print(f"Correcting {n_to_correct} rows (×0.5 on Stage1_s, Stage2_s, Stage3_s)")

    # Show before/after sample
    sample_idx = df[mask_to_correct].index[:3]
    print("\nSample before correction:")
    print(df.loc[sample_idx, TIMING_COLS].to_string())

    for col in TIMING_COLS:
        df.loc[mask_to_correct, col] = pd.to_numeric(df.loc[mask_to_correct, col],
                                                       errors="coerce") * 0.5

    print("\nSample after correction:")
    print(df.loc[sample_idx, TIMING_COLS].to_string())

    if args.dry_run:
        print("\nDry run — no file written.")
        return

    df.to_csv(args.csv, index=False, float_format="%.4g")
    print(f"\nWrote corrected file: {args.csv}")
    if n_skipped:
        print(f"  {n_skipped} rows (device '{args.skip_device}') left at original 25fps values")
    print(f"  {n_to_correct} rows corrected (timing values halved)")


if __name__ == "__main__":
    main()
