#!/usr/bin/env python3
"""Imita llama-server para las pruebas: /health y /v1/chat/completions en streaming.
Si se envían herramientas y el último mensaje del usuario contiene 'lista', pide list_dir."""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("-m"); ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int)
ap.add_argument("-c"); ap.add_argument("-t"); ap.add_argument("-ngl"); ap.add_argument("--jinja", action="store_true")
args, _ = ap.parse_known_args()
# PNG de 1x1 píxel
PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b'{"status":"ok"}' if self.path == "/health" else b'{"data":[{"id":"fake"}]}'
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def chunk(self, obj):
        self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode()); self.wfile.flush()

    def json_reply(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/images/generations"):
            return self.json_reply({"data": [{"b64_json": PNG_B64}]})
        if req.get("modalities"):
            return self.json_reply({"choices": [{"message": {"role": "assistant", "content": "",
                                    "images": [{"image_url": {"url": "data:image/png;base64," + PNG_B64}}]}}]})
        if "tope tokens" in str(req["messages"][-1].get("content")) and req.get("max_tokens", 0) > 4096:
            body = json.dumps({"error": {"message": "This request requires more credits, or fewer max_tokens. "
                                                    "You requested up to %d tokens, but can only afford 3000" % req["max_tokens"]}}).encode()
            self.send_response(402); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        msgs = req["messages"]
        last = msgs[-1]
        names = [t["function"]["name"] for t in req.get("tools") or []]
        if "run_command" in names and last["role"] == "user" and "ejecuta" in last["content"]:
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c2", "function": {
                "name": "run_command", "arguments": json.dumps({"command": "echo hola-g3"})}}]}}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "create_document" in names and last["role"] == "user" and "hazme un excel" in str(last["content"]):
            content = json.dumps({"sheets": [{"name": "Nómina", "rows": [["Nombre", "Total"], ["Ana", 100]]}]})
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "d1", "function": {
                "name": "create_document", "arguments": json.dumps({"path": "nomina.xlsx", "content": content})}}]}}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "generate_image" in names and last["role"] == "user" and "dibuja" in str(last["content"]):
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "g1", "function": {
                "name": "generate_image", "arguments": json.dumps({"prompt": "a cat on a desk"})}}]}}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "memory_save" in names and last["role"] == "user" and "recuerda que" in last["content"]:
            fact = last["content"].split("recuerda que", 1)[1].strip()
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "m1", "function": {
                "name": "memory_save", "arguments": json.dumps({"content": "Al usuario " + fact})}}]}}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if last["role"] == "user" and "qué hiciste" in str(last["content"]):  # repite lo que ve en el historial
            logs = [m["content"] for m in msgs if m["role"] == "assistant" and "<registro_de_herramientas>" in str(m["content"])]
            sysmsg = msgs[0]["content"] if msgs[0]["role"] == "system" else ""
            self.chunk({"choices": [{"delta": {"content": "REGISTRO:" + (logs[-1].split("<registro_de_herramientas>")[1][:200] if logs else "ninguno")
                                               + "|PLAN:" + ("sí" if "Plan actual de la tarea" in sysmsg else "no")
                                               + "|MODOPLAN:" + ("sí" if "MODO PLAN" in sysmsg else "no")}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        first_user = next((m["content"] for m in msgs if m["role"] == "user"), "")
        if "flujo_completo" in str(first_user) and req.get("tools"):
            import os
            n_tools = 0
            for m in reversed(msgs):
                if m["role"] == "user":
                    break
                n_tools += m["role"] == "tool"
            path = os.environ.get("FAKE_READ_PATH", "")
            steps = [("todo_write", {"todos": [{"content": "Leer el archivo", "status": "in_progress"},
                                                {"content": "Cambiar el valor", "status": "pending"},
                                                {"content": "Comprobar el resultado", "status": "pending"}]}),
                     ("read_file", {"path": path}),
                     ("edit_file", {"path": path, "old_text": "secreto", "new_text": "cambiado"})]
            if n_tools < len(steps):
                name, args = steps[n_tools]
                self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": f"f{n_tools}", "function": {
                    "name": name, "arguments": json.dumps(args)}}]}, "finish_reason": "tool_calls"}]})
            else:
                self.chunk({"choices": [{"delta": {"content": "Hecho: he cambiado el valor y lo he comprobado."}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "tool_call_en_texto" in str(first_user) and req.get("tools"):
            if last["role"] == "tool":  # ya se ejecutó: responde con lo leído
                self.chunk({"choices": [{"delta": {"content": "Leído: " + str(last["content"])[-40:]}, "finish_reason": "stop"}]})
            else:  # la llamada va como texto, no como tool_calls
                import os
                path = os.environ.get("FAKE_READ_PATH", "")
                call = json.dumps({"name": "read_file", "arguments": {"path": path}})
                self.chunk({"choices": [{"delta": {"content": f"Voy a leerlo.\n<tool_call>{call}</tool_call>"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        sysmsg0 = msgs[0]["content"] if msgs[0]["role"] == "system" else ""
        if "COPIA aislada" in sysmsg0:  # ayudante que escribe: crea un archivo en su copia y termina
            import re as _re
            name = _re.search(r"edita_sub:(\w+)", str(first_user)).group(1)
            if last["role"] == "tool":
                self.chunk({"choices": [{"delta": {"content": f"Informe: creé {name}.txt"}, "finish_reason": "stop"}]})
            else:
                root = _re.search(r"Sólo puedes modificar archivos en: ([^.\n]+?)\.(?:\s|$)", sysmsg0).group(1)
                self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "w1", "function": {
                    "name": "write_file", "arguments": json.dumps({"path": f"{root}/{name}.txt", "content": f"hecho por {name}\n"})}}]},
                    "finish_reason": "tool_calls"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "delegate_edit" in names and last["role"] == "user" and "reparte" in str(last["content"]):
            self.chunk({"choices": [{"delta": {"tool_calls": [
                {"index": i, "id": f"e{i}", "function": {"name": "delegate_edit", "arguments": json.dumps({"task": f"edita_sub:{n}"})}}
                for i, n in enumerate(["uno", "dos"])]}, "finish_reason": "tool_calls"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if last["role"] == "tool" and "Propuesta" in str(last["content"]):
            self.chunk({"choices": [{"delta": {"content": "Propuestas listas para revisar"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "informe_sub" in str(first_user) and last["role"] == "user" and msgs[0]["role"] == "system" \
                and "ayudante de investigación" in msgs[0]["content"]:  # el ayudante de «delegate»
            self.chunk({"choices": [{"delta": {"content": "INFORME: hallazgo-123 en src/x.py:7"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "delegate" in names and last["role"] == "user" and "delega" in str(last["content"]):
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "d1", "function": {
                "name": "delegate", "arguments": json.dumps({"task": "informe_sub: busca dónde se usa X"})}}]},
                "finish_reason": "tool_calls"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if last["role"] == "tool" and "hallazgo-123" in str(last["content"]):
            self.chunk({"choices": [{"delta": {"content": "El ayudante encontró: hallazgo-123"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "dime el sistema que te llega" in str(first_user):  # eco de lo que dice el prompt del sistema
            note = "Agente" if "Herramientas del equipo desactivadas" in (msgs[0]["content"] if msgs[0]["role"] == "system" else "") else "ninguna nota"
            self.chunk({"choices": [{"delta": {"content": "Nota: " + note}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "miembro del equipo de G3G3AI" in sysmsg0 and last["role"] == "user":   # un miembro del equipo
            self.chunk({"choices": [{"delta": {"content": "INFORME EQUIPO: dato-42"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "team_delegate" in names and last["role"] == "user" and "pregunta al equipo" in str(last["content"]):
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t1", "function": {
                "name": "team_delegate", "arguments": json.dumps({"member": "Investigador", "task": "busca el dato"})}}]},
                "finish_reason": "tool_calls"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if last["role"] == "tool" and "dato-42" in str(last["content"]):
            self.chunk({"choices": [{"delta": {"content": "El equipo dice: dato-42"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "vacio tras herramienta" in str(first_user) and req.get("tools"):  # termina sin texto tras usar una herramienta
            if last["role"] == "user" and "No has escrito ninguna respuesta" in str(last["content"]):
                self.chunk({"choices": [{"delta": {"content": "Ahora sí: he visto la carpeta."}, "finish_reason": "stop"}]})
            elif last["role"] == "tool":
                self.chunk({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]})
            else:
                self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "v1", "function": {
                    "name": "list_dir", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "siempre vacio" in str(first_user):
            self.chunk({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "ver ajustes locales" in str(first_user):  # devuelve cómo le llegó la petición
            kw = req.get("chat_template_kwargs") or {}
            info = (f"AJUSTES: temp={req.get('temperature')} think={kw.get('enable_thinking')} cache={req.get('cache_prompt')} "
                    f"max={req.get('max_tokens')} tools={len(req.get('tools') or [])} np{sys.argv[sys.argv.index('-np') + 1] if '-np' in sys.argv else '?'}")
            self.chunk({"choices": [{"delta": {"content": info}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "error a mitad" in str(first_user):  # el proveedor falla después de haber enviado texto
            self.chunk({"choices": [{"delta": {"content": "empiezo bien… "}}]})
            self.chunk({"error": {"message": "upstream exploded", "code": 502}})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "haz una pagina" in str(first_user):  # responde con una página HTML grande y un diagrama
            page = "\n".join(["<!doctype html>", "<html><head><title>Calculadora de horas</title></head><body>"]
                             + [f"<p>Fila {i}</p>" for i in range(18)] + ["</body></html>"])
            text = f"Aquí la tienes:\n\n```html\n{page}\n```\n\nY el flujo:\n\n```mermaid\nflowchart TD\n  A[Inicio] --> B[Fin]\n```\n"
            self.chunk({"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "piensa demasiado" in str(first_user):  # razona hasta agotar el límite salvo que se le dé mucho margen
            if req.get("max_tokens", 0) >= 16384:
                self.chunk({"choices": [{"delta": {"reasoning_content": "pienso…"}}]})
                self.chunk({"choices": [{"delta": {"content": "respuesta tras pensar"}, "finish_reason": "stop"}]})
            else:
                self.chunk({"choices": [{"delta": {"reasoning_content": "pienso y pienso…"}, "finish_reason": "length"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "manda al usuario" in str(first_user):  # nombra la herramienta en vez de llamarla
            if "No le pidas al usuario" in str(last["content"]):
                self.chunk({"choices": [{"delta": {"content": "Ya lo he buscado yo."}, "finish_reason": "stop"}]})
            else:
                self.chunk({"choices": [{"delta": {"content": "Dime qué quieres que busque usando `web_search`."}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "respuesta lenta" in str(first_user):  # escribe poco a poco durante ~3 s
            import time as _t
            for w in ["Esta ", "respuesta ", "llega ", "despacio ", "y ", "termina ", "bien."]:
                self.chunk({"choices": [{"delta": {"content": w}}]}); self.wfile.flush(); _t.sleep(0.45)
            self.chunk({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "desbocate" in str(first_user):  # se va al chino salvo que se le baje la temperatura
            if (req.get("temperature") or 1) <= 0.25:
                self.chunk({"choices": [{"delta": {"content": "Respuesta serena y correcta."}, "finish_reason": "stop"}]})
            else:
                self.chunk({"choices": [{"delta": {"content": "Empiezo bien, pero "}}]})
                for _ in range(12):
                    self.chunk({"choices": [{"delta": {"content": "我们的目标是确保每个人都能够获得公平的机会"}}]})
                self.chunk({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "imita el registro" in str(first_user):
            self.chunk({"choices": [{"delta": {"content": "Hecho.\n\n<registro_de_herramientas>\n- read_file(x)\n</registro_de_herramientas>"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "eco del usuario" in str(first_user):  # devuelve el último mensaje del usuario tal cual le llega
            self.chunk({"choices": [{"delta": {"content": "USUARIO<<" + str(last["content"]) + ">>"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "eco del sistema" in str(first_user):  # devuelve el mensaje del sistema tal cual
            self.chunk({"choices": [{"delta": {"content": "SISTEMA<<" + sysmsg0 + ">>"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "contexto enorme" in str(first_user):  # informa del progreso de lectura (llama.cpp con return_progress)
            if req.get("return_progress"):
                for done in (0, 2000, 4000, 6000, 8000):
                    self.chunk({"choices": [], "prompt_progress": {"total": 8100, "cache": 100, "processed": 100 + done, "time_ms": done}})
            self.chunk({"choices": [{"delta": {"content": "leído"}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "con filtro" in str(first_user):
            self.chunk({"choices": [{"delta": {"content": "no puedo"}, "finish_reason": "content_filter"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "tope tokens" in str(first_user):
            self.chunk({"choices": [{"delta": {"content": "respuesta con tope"}, "finish_reason": "stop"}]})
            self.chunk({"choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 7}})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "texto largo" in str(first_user):  # simula un corte por longitud y su continuación
            if "límite de longitud" in str(last["content"]):
                self.chunk({"choices": [{"delta": {"content": "segunda parte."}, "finish_reason": "stop"}]})
            else:
                self.chunk({"choices": [{"delta": {"content": "primera parte, "}, "finish_reason": "length"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if "anuncia" in str(first_user) and req.get("tools"):  # usa una herramienta, anuncia otra y se para
            if last["role"] == "user" and "acabas de anunciar" in str(last["content"]):
                self.chunk({"choices": [{"delta": {"content": "Listo, ya lo he revisado."}, "finish_reason": "stop"}]})
            elif last["role"] == "tool":
                self.chunk({"choices": [{"delta": {"content": "He visto la carpeta. Ahora leo el archivo principal."},
                                         "finish_reason": "stop"}]})
            else:
                self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "a1", "function": {
                    "name": "list_dir", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if last["role"] == "user" and "página html" in str(last["content"]):
            text = ("Aquí tienes una **página** sencilla:\n\n```html\n<!doctype html><html><body style=\"font-family:sans-serif\">"
                    "<h1 style=\"color:#c2603f\">Hola desde G3G3AI</h1><button onclick=\"this.textContent='¡Pulsado!'\">Púlsame</button>"
                    "</body></html>\n```\n\n| Parte | Qué hace |\n|---|---|\n| h1 | Título |\n| button | Botón |\n\n- Uno\n- Dos")
            for w in text.split(" "):
                self.chunk({"choices": [{"delta": {"content": w + " "}}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if last["role"] == "user" and "qué sabes" in last["content"]:
            system = msgs[0]["content"] if msgs[0]["role"] == "system" else ""
            mem = system.split("Memoria", 1)[1][:300] if "Memoria" in system else "nada"
            self.chunk({"choices": [{"delta": {"content": "MEM:" + mem}}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if req.get("tools") and last["role"] == "user" and "lista" in last["content"]:
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "list_dir", "arguments": ""}}]}}]})
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}}]})
            self.wfile.write(b"data: [DONE]\n\n"); return
        if isinstance(last.get("content"), list):  # mensaje con imágenes
            n = sum(1 for part in last["content"] if part.get("type") == "image_url")
            txt = " ".join(part.get("text", "") for part in last["content"] if part.get("type") == "text")
            self.chunk({"choices": [{"delta": {"content": f"VEO {n} IMAGEN(ES); texto: {txt[-60:]}"}}]})
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
