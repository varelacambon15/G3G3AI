#!/usr/bin/env python3
"""Imita llama-server para las pruebas: /health y /v1/chat/completions en streaming.
Si se envían herramientas y el último mensaje del usuario contiene 'lista', pide list_dir."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("-m"); ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int)
ap.add_argument("-c"); ap.add_argument("-t"); ap.add_argument("-ngl"); ap.add_argument("--jinja", action="store_true")
args, _ = ap.parse_known_args()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b'{"status":"ok"}' if self.path == "/health" else b'{"data":[{"id":"fake"}]}'
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def chunk(self, obj):
        self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode()); self.wfile.flush()

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        msgs = req["messages"]
        last = msgs[-1]
        names = [t["function"]["name"] for t in req.get("tools") or []]
        if "run_command" in names and last["role"] == "user" and "ejecuta" in last["content"]:
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c2", "function": {
                "name": "run_command", "arguments": json.dumps({"command": "echo hola-g3"})}}]}}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if req.get("tools") and last["role"] == "user" and "lista" in last["content"]:
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "list_dir", "arguments": ""}}]}}]})
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if last["role"] == "tool":
            text = "Veo: " + ("hola.txt" if "hola.txt" in last["content"] else "nada")
        else:
            text = f"Eco ({len(msgs)} msgs): {last['content'][-40:]}"
        self.chunk({"choices": [{"delta": {"reasoning_content": "pensando"}}]})
        for w in text.split(" "):
            self.chunk({"choices": [{"delta": {"content": w + " "}}]})
        self.chunk({"choices": [{"delta": {}, "finish_reason": "stop"}], "timings": {"predicted_per_second": 12.5, "predicted_n": 7, "prompt_n": 3}})
        self.wfile.write(b"data: [DONE]\n\n")


ThreadingHTTPServer((args.host, args.port), H).serve_forever()
