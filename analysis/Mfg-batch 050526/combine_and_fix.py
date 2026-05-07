import csv
import re

BASE = r"C:\Users\conor\Documents\Code Projects\PE\stepgen\design_model\analysis\Mfg-batch 050526"

INPUT_FILES = [
    f"{BASE}\\stage_timings_260413-3D.csv",
    f"{BASE}\\stage_timings-260413-1B.csv",
    f"{BASE}\\stage_timings_260413-4C.csv",
]
OUTPUT_FILE = f"{BASE}\\stage_timings_Mfg050526_combined.csv"

PROD_DATE = "050526"
TEST_DATE = "060526"
CONT_PHASE = "SDS"
DISP_PHASE = "SO"
CONT_FLOW = "5"
DISP_PRESSURE = "300"

all_rows = []
header = None

for filepath in INPUT_FILES:
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if header is None:
        header = rows[0]

    for row in rows[1:]:
        if not any(row):
            continue

        # Pad if short
        while len(row) < 18:
            row.append("")

        # Extract location from VideoFile name, preserving _B/_C suffix for sub-groups
        video = row[1].strip()
        loc_match = re.search(r'(DFU\d+(?:_[BC])?)\.mp4', video, re.IGNORECASE)
        location = loc_match.group(1) if loc_match else row[7].strip()

        # Fix DeviceID: strip -SDS suffix; normalise 20260413 -> 260413
        device_id = row[3].strip()
        device_id = re.sub(r"-SDS$", "", device_id)
        device_id = re.sub(r"20260413", "260413", device_id)

        row[3] = device_id
        row[4] = PROD_DATE
        row[5] = TEST_DATE
        row[6] = CONT_PHASE
        row[7] = DISP_PHASE
        row[8] = CONT_FLOW
        row[9] = DISP_PRESSURE
        row[10] = location

        all_rows.append(row)

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(all_rows)

print(f"Wrote {len(all_rows)} rows -> {OUTPUT_FILE}")

# Quick sanity check
unique_devices = sorted(set(r[3] for r in all_rows))
unique_locations = sorted(set(r[10] for r in all_rows), key=lambda x: int(re.search(r'\d+', x).group()))
print(f"Devices   : {unique_devices}")
print(f"Locations : {unique_locations}")
print(f"Sample row: {all_rows[0]}")
