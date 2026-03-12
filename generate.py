#!/usr/bin/env python3
import json
from pathlib import Path

# الملف الأصلي الكبير
SOURCE_FILE = Path("data/pair_profiles.json")

# المجلد الذي ستوضع فيه الأجزاء الصغيرة
OUTPUT_DIR = Path("data/pair_profiles_parts")

# عدد الأجزاء المستهدفة
TARGET_PARTS = 30

def main():
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"Missing source file: {SOURCE_FILE}")

    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "pair_profiles" in data:
        profiles = data["pair_profiles"]
    elif isinstance(data, dict):
        profiles = data
    else:
        raise ValueError("Unexpected JSON structure in pair_profiles.json")

    items = list(profiles.items())
    total = len(items)

    if total == 0:
        raise ValueError("No pair profiles found in source file.")

    chunk_size = (total // TARGET_PARTS) + (1 if total % TARGET_PARTS else 0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # حذف الأجزاء القديمة إن وجدت
    for old_file in OUTPUT_DIR.glob("part*.json"):
        old_file.unlink()

    part_num = 1
    for i in range(0, total, chunk_size):
        chunk = dict(items[i:i + chunk_size])

        output_payload = {
            "pair_profiles": chunk
        }

        output_file = OUTPUT_DIR / f"part{part_num:03d}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=2)

        print(f"Created {output_file} with {len(chunk)} pair profiles")
        part_num += 1

    print("\nDone.")
    print(f"Total pair profiles: {total}")
    print(f"Created parts in: {OUTPUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
