"""Write every stored brief to samples/<Company>_<Quarter>/{summary.json,summary.md,transcript.txt}."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import settings  # noqa: E402
import store  # noqa: E402

store.init()
for entry in store.list_briefs():
    row = store.get_brief(entry["id"])
    folder = f"samples/{re.sub(r'[^A-Za-z0-9]+', '_', row['company'])}_{row['quarter']}".replace(" ", "")
    os.makedirs(folder, exist_ok=True)

    with open(f"{folder}/summary.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(json.loads(row["payload"]), indent=2, ensure_ascii=False))
    with open(f"{folder}/summary.md", "w", encoding="utf-8") as f:
        f.write(row["markdown"])

    transcript = os.path.join(os.path.dirname(settings.DB_PATH) or ".", "transcripts", f"{entry['id']}.txt")
    if os.path.exists(transcript):
        with open(transcript, encoding="utf-8") as src, open(f"{folder}/transcript.txt", "w", encoding="utf-8") as dst:
            dst.write(src.read())
    print("wrote", folder)
