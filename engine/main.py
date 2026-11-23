"""Start the API, watcher and WebSocket feeds:  python main.py   ->  http://localhost:8000"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("gateway.app:app", host="0.0.0.0", port=8000)
