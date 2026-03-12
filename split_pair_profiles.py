import json
from pathlib import Path

SOURCE_DIR = Path("data")
SOURCE_FILES = sorted(SOURCE_DIR.glob("pair_profiles_part*.json"))
OUTPUT_DIR = SOURCE_DIR / "pair_profiles_parts"
CHUNK_SIZE = 750  # عدد الأزواج داخل كل ملف صغير

def load_all_profiles():
    merged = {}

    for file_path in SOURCE_FILES:
        print(f"Reading {file_path.name} ...")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "pair_profiles" in data:
            merged.update(data["pair_profiles"])
        elif isinstance(data, dict):
            merged.update(data)
        else:
            raise ValueError(f"Unexpected JSON structure in {file_path.name}")

    return merged

def write_chunks(profiles: dict):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    items = list(profiles.items())
    total = len(items)
    chunk_count = 0

    for i in range(0, total, CHUNK_SIZE):
        chunk = dict(items[i:i + CHUNK_SIZE])
        chunk_count += 1
        out_path = OUTPUT_DIR / f"part{chunk_count:03d}.json"

        payload = {
            "pair_profiles": chunk
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(f"Wrote {out_path} ({len(chunk)} pairs)")

    print(f"\nDone. Created {chunk_count} files in: {OUTPUT_DIR}")

def main():
    if not SOURCE_FILES:
        print("No source files found. Expected files like:")
        print("data/pair_profiles_part1.json")
        print("data/pair_profiles_part2.json")
        return

    profiles = load_all_profiles()
    print(f"Loaded {len(profiles)} total pair profiles.\n")
    write_chunks(profiles)

if __name__ == "__main__":
    main()
