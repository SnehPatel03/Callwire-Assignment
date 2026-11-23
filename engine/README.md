# Callwire engine

Python backend: watcher, PDF reader, LLM summariser, REST API and WebSocket feeds.
See the [root README](../README.md) for setup, configuration and design notes.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env        # set LLM_API_KEY; never commit .env
python main.py              # http://localhost:8000
```

| Package | Stage |
|---|---|
| `ingest/` | Watch NSE/BSE, filter transcripts, dedupe, download the PDF |
| `reader/` | PDF to clean text; quarter and call-date detection |
| `digest/` | Chunk, map, merge, verify; Markdown rendering |
| `gateway/` | FastAPI app: `/v1/*` REST, `/stream/*` WebSockets, built-in pages |

```bash
python -m pytest -q                       # offline tests
python tools/dump_samples.py              # write samples/<Company>_<Quarter>/
pip install websockets && python -m websockets ws://localhost:8000/stream/briefs
```
