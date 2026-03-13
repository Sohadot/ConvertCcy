import json
from pathlib import Path

SOURCE_FILE = Path("data/pair_profiles.json")
OUTPUT_DIR = Path("data/pair_profiles_parts")
TARGET_PARTS = 30

def main():

    if not SOURCE_FILE.exists():
        print("ERROR: file not found:", SOURCE_FILE)
        return

    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "pair_profiles" in data:
        profiles = data["pair_profiles"]
    else:
        profiles = data

    items = list(profiles.items())
    total = len(items)

    chunk_size = total // TARGET_PARTS + 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    part = 1

    for i in range(0, total, chunk_size):

        chunk = dict(items[i:i+chunk_size])

        output = {
            "pair_profiles": chunk
        }

        filename = OUTPUT_DIR / f"part{part:03d}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print("created", filename)

        part += 1

    print("DONE")

if __name__ == "__main__":
    main()
