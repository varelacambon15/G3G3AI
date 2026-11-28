"""Cliente mínimo de la API de GitHub para el agente (issues, pull requests, CI y archivos).

Las acciones de lectura se ejecutan sin preguntar; las que escriben (crear issue/PR, comentar, cerrar) piden
siempre permiso al usuario (ver ToolContext.precheck). El token se guarda en Ajustes («github_token») o se toma
de la variable de entorno GITHUB_TOKEN / GH_TOKEN.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
from pathlib import Path

import httpx

API = "https://api.github.com"
READ_ACTIONS = {"repo", "issues", "issue", "prs", "pr", "checks", "file", "search_code", "runs", "run", "job_log", "release"}
WRITE_ACTIONS = {"create_issue", "comment", "create_pr", "close_issue", "dispatch"}
ACTIONS = sorted(READ_ACTIONS | WRITE_ACTIONS)


class GitHubError(Exception):
    pass


def token(cfg) -> str:
    return (cfg["github_token"] or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()


def repo_from_remote(workdir: Path) -> str | None:
    """owner/nombre a partir del remoto «origin» de la carpeta de trabajo."""
    try:
        r = subprocess.run(["git", "-C", str(workdir), "remote", "get-url", "origin"], capture_output=True,
                           text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git)?/?\s*$", r.stdout.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def describe_write(a: dict, repo: str) -> str:
    act = a.get("action")
    n = a.get("number")
    return {
        "create_issue": f"crea un issue en {repo}: «{a.get('title', '')}»",
        "comment": f"publica un comentario en {repo}#{n}",
        "create_pr": f"abre un pull request en {repo}: {a.get('head')} → {a.get('base') or 'rama principal'}",
        "close_issue": f"cierra {repo}#{n}",
        "dispatch": f"lanza el flujo «{a.get('workflow') or 'build.yml'}» en {repo} (rama {a.get('ref') or 'principal'}): compila y, si es el de publicar, saca la Release",
    }.get(act, f"{act} en {repo}")


def _short(s, n=600) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


async def call(cfg, a: dict, default_repo: str | None) -> str:
    tok = token(cfg)
    if not tok:
        return ("Error: no hay token de GitHub. Pídele al usuario que lo añada en Ajustes → «Token de GitHub» "
                "(permisos: repo / contents, issues y pull requests).")
    action = a.get("action")
    if action not in ACTIONS:
        return f"Error: acción desconocida «{action}». Acciones: {', '.join(ACTIONS)}."
    repo = (a.get("repo") or default_repo or "").strip()
    if action != "search_code" and not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return "Error: indica repo como «propietario/nombre» (o trabaja dentro de una carpeta con remoto de GitHub)."
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "G3G3AI"}
    async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as c:
        async def req(method: str, path: str, **kw):
            r = await c.request(method, API + path, **kw)
            if r.status_code == 401:
                raise GitHubError("el token de GitHub no es válido o ha caducado")
            if r.status_code == 403 and "rate limit" in r.text.lower():
                raise GitHubError("límite de peticiones de GitHub alcanzado; espera un rato")
            if r.status_code == 404:
                raise GitHubError(f"no encontrado (¿repo o número incorrecto, o el token no tiene acceso a {repo}?)")
            if r.status_code >= 400:
                try:
                    msg = r.json().get("message", r.text)
                    errs = r.json().get("errors")
                    if errs:
                        msg += f" {errs}"
                except ValueError:
                    msg = r.text
                raise GitHubError(f"HTTP {r.status_code}: {_short(msg, 400)}")
            if "json" not in r.headers.get("content-type", "") and r.content:
                return r.text                      # p. ej. el registro de un trabajo de CI
            return r.json() if r.content else {}
        try:
            return await _dispatch(req, action, repo, a)
        except GitHubError as e:
            return f"Error de GitHub: {e}"
        except httpx.HTTPError as e:
            return f"Error de red al hablar con GitHub: {e}"


async def _dispatch(req, action: str, repo: str, a: dict) -> str:
    num = a.get("number")
    if action in ("issue", "pr", "comment", "close_issue") and not num:
        raise GitHubError("falta «number»")
    if action == "repo":
        j = await req("GET", f"/repos/{repo}")
        return (f"{j['full_name']} — {j.get('description') or 'sin descripción'}\nRama principal: {j['default_branch']} · "
                f"⭐ {j['stargazers_count']} · issues abiertos: {j['open_issues_count']} · "
                f"{'privado' if j['private'] else 'público'} · lenguaje: {j.get('language')}\n{j['html_url']}")
    if action == "issues":
        j = await req("GET", f"/repos/{repo}/issues", params={"state": a.get("state") or "open", "per_page": 20})
        rows = [f"#{i['number']} [{i['state']}] {i['title']} — {i['user']['login']}" + (" (PR)" if "pull_request" in i else "")
                for i in j]
        return "\n".join(rows) or "No hay issues."
    if action == "issue":
        i = await req("GET", f"/repos/{repo}/issues/{num}")
        cs = await req("GET", f"/repos/{repo}/issues/{num}/comments", params={"per_page": 20})
        out = [f"#{i['number']} [{i['state']}] {i['title']} — {i['user']['login']}", _short(i.get("body"), 3000)]
        out += [f"\n💬 {c['user']['login']}: {_short(c['body'], 1200)}" for c in cs]
        return "\n".join(out)
    if action == "prs":
        j = await req("GET", f"/repos/{repo}/pulls", params={"state": a.get("state") or "open", "per_page": 20})
        return "\n".join(f"#{p['number']} [{p['state']}] {p['title']} — {p['head']['ref']} → {p['base']['ref']}"
                         for p in j) or "No hay pull requests."
    if action == "pr":
        p = await req("GET", f"/repos/{repo}/pulls/{num}")
        files = await req("GET", f"/repos/{repo}/pulls/{num}/files", params={"per_page": 50})
        out = [f"#{p['number']} [{p['state']}{', fusionado' if p.get('merged') else ''}] {p['title']}",
               f"{p['head']['ref']} → {p['base']['ref']} · +{p['additions']} −{p['deletions']} en {p['changed_files']} archivos",
               _short(p.get("body"), 2500), "", "Archivos:"]
        out += [f"  {f['status'][:1].upper()} {f['filename']} (+{f['additions']} −{f['deletions']})" for f in files]
        return "\n".join(out)
    if action == "checks":
        ref = a.get("ref")
        if not ref and num:
            ref = (await req("GET", f"/repos/{repo}/pulls/{num}"))["head"]["sha"]
        if not ref:
            raise GitHubError("indica «ref» (rama o commit) o «number» de un PR")
        j = await req("GET", f"/repos/{repo}/commits/{ref}/check-runs", params={"per_page": 50})
        runs = j.get("check_runs", [])
        return "\n".join(f"{'✔' if r['conclusion'] == 'success' else '✕' if r['conclusion'] in ('failure', 'timed_out', 'cancelled') else '…'} "
                         f"{r['name']}: {r['conclusion'] or r['status']}" for r in runs) or "No hay comprobaciones de CI."
    if action == "file":
        path = (a.get("path") or "").strip("/")
        j = await req("GET", f"/repos/{repo}/contents/{path}", params={"ref": a["ref"]} if a.get("ref") else None)
        if isinstance(j, list):
            return "\n".join(("[D] " if e["type"] == "dir" else "    ") + e["name"] for e in j)
        text = base64.b64decode(j.get("content", "")).decode("utf-8", errors="replace")
        return text[:30_000] + ("\n[… recortado …]" if len(text) > 30_000 else "")
    if action == "search_code":
        q = (a.get("query") or "").strip()
        if not q:
            raise GitHubError("falta «query»")
        j = await req("GET", "/search/code", params={"q": q + (f" repo:{repo}" if repo else ""), "per_page": 15})
        return "\n".join(f"{i['repository']['full_name']}: {i['path']}" for i in j.get("items", [])) or "Sin resultados."
    # --- CI y versiones: para que la IA pueda comprobar sus propios cambios y sacar versiones
    if action == "runs":
        params = {"per_page": min(int(a.get("limit") or 8), 20)}
        if a.get("ref"):
            params["branch"] = a["ref"]
        j = await req("GET", f"/repos/{repo}/actions/runs", params=params)
        rows = [f"{r['id']} · {r['head_sha'][:7]} · {r['head_branch']} · {r['event']} · "
                f"{'✔' if r['conclusion'] == 'success' else '✕' if r['conclusion'] in ('failure', 'timed_out', 'cancelled') else '…'} "
                f"{r['conclusion'] or r['status']} · {_short(r.get('display_title') or r.get('name'), 70)}"
                for r in j.get("workflow_runs", [])]
        return "Ejecuciones de CI (más recientes primero; usa «run» con el id para ver los trabajos):\n" + ("\n".join(rows) or "Ninguna.")
    if action == "run":
        rid = a.get("run_id")
        if not rid:
            raise GitHubError("falta «run_id» (míralo con la acción runs)")
        j = await req("GET", f"/repos/{repo}/actions/runs/{rid}/jobs", params={"per_page": 50})
        out = []
        for job in j.get("jobs", []):
            icon = "✔" if job["conclusion"] == "success" else "✕" if job["conclusion"] in ("failure", "timed_out", "cancelled") else "…"
            out.append(f"{icon} {job['name']} (id {job['id']}): {job['conclusion'] or job['status']}")
            for st in job.get("steps", []):
                if st.get("conclusion") in ("failure", "timed_out"):
                    out.append(f"    ✕ paso «{st['name']}» falló → mira el registro con job_log job_id={job['id']}")
        return "\n".join(out) or "Sin trabajos."
    if action == "job_log":
        jid = a.get("job_id")
        if not jid:
            raise GitHubError("falta «job_id» (míralo con la acción run)")
        raw = await req("GET", f"/repos/{repo}/actions/jobs/{jid}/logs")      # (un 403 aquí: el token necesita leer «Actions»)
        lines = [re.sub(r"^\S+Z ", "", ln) for ln in str(raw).splitlines()]
        keep = int(a.get("tail") or 80)
        errs = [i for i, ln in enumerate(lines) if re.search(r"error|Error|FAILED|Traceback|##\[error\]", ln)]
        head = f"[registro del trabajo {jid}: {len(lines)} líneas; se muestran las últimas {min(keep, len(lines))}"
        if errs:
            head += f"; primer error en la línea {errs[0] + 1}"
        return head + "]\n" + "\n".join(lines[-keep:])[-12_000:]
    if action == "release":
        j = await req("GET", f"/repos/{repo}/releases/tags/{a['ref']}" if a.get("ref") else f"/repos/{repo}/releases/latest")
        assets = ", ".join(f"{x['name']} ({x['size'] // 1_048_576} MB)" for x in j.get("assets", []))
        return f"{j['name']} ({j['tag_name']}) · publicada {j.get('published_at')}\n{j['html_url']}\nArchivos: {assets or 'ninguno'}\n\n{_short(j.get('body'), 1500)}"
    # --- escritura (siempre con permiso del usuario)
    if action == "dispatch":
        wf = a.get("workflow") or "build.yml"
        ref = a.get("ref") or (await req("GET", f"/repos/{repo}"))["default_branch"]
        await req("POST", f"/repos/{repo}/actions/workflows/{wf}/dispatches", json={"ref": ref})
        return f"Flujo «{wf}» lanzado en la rama {ref}. Mira cómo va con la acción runs (ref={ref})."
    if action == "create_issue":
        if not a.get("title"):
            raise GitHubError("falta «title»")
        j = await req("POST", f"/repos/{repo}/issues", json={"title": a["title"], "body": a.get("body") or ""})
        return f"Issue creado: #{j['number']} {j['html_url']}"
    if action == "comment":
        j = await req("POST", f"/repos/{repo}/issues/{num}/comments", json={"body": a.get("body") or ""})
        return f"Comentario publicado: {j['html_url']}"
    if action == "close_issue":
        await req("PATCH", f"/repos/{repo}/issues/{num}", json={"state": "closed"})
        return f"#{num} cerrado."
    if action == "create_pr":
        if not (a.get("title") and a.get("head")):
            raise GitHubError("faltan «title» y «head» (la rama con los cambios, ya subida con git push)")
        base = a.get("base") or (await req("GET", f"/repos/{repo}"))["default_branch"]
        j = await req("POST", f"/repos/{repo}/pulls", json={"title": a["title"], "head": a["head"], "base": base,
                                                           "body": a.get("body") or "", "draft": bool(a.get("draft"))})
        return f"Pull request creado: #{j['number']} {j['html_url']}"
    raise GitHubError("acción no implementada")
