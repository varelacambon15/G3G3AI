"""Catálogo de conectores (servidores MCP conocidos) que se añaden con un clic desde «Conectores».

Cada uno genera una línea de «Servidores MCP» (ver mcp.parse_servers). Los de tipo «npx» necesitan Node.js.
"""
from __future__ import annotations

import re
import shutil

# id, nombre, icono, descripción, plantilla de la línea, campos que pide {clave: (etiqueta, tipo, ayuda)}
CATALOG = [
    {"id": "github", "name": "GitHub (oficial)", "icon": "git", "kind": "remote",
     "desc": "Repositorios, issues, pull requests, Actions y código de GitHub con el servidor oficial de GitHub.",
     "line": "github = TOKEN={token} https://api.githubcopilot.com/mcp/",
     "fields": {"token": ("Token de GitHub", "password", "Usa el mismo que en «GitHub» (arriba) o crea uno en github.com/settings/tokens.")},
     "uses_github_token": True},
    {"id": "playwright", "name": "Navegador web", "icon": "globe", "kind": "npx",
     "desc": "La IA abre páginas, hace clic, rellena formularios y saca capturas en un navegador real (Playwright).",
     "line": "navegador = npx -y @playwright/mcp@latest", "fields": {}},
    {"id": "context7", "name": "Documentación de librerías", "icon": "doc", "kind": "npx",
     "desc": "Documentación actualizada de librerías y frameworks (Context7) para programar sin inventar APIs.",
     "line": "documentacion = npx -y @upstash/context7-mcp", "fields": {}},
    {"id": "notion", "name": "Notion", "icon": "doc", "kind": "npx",
     "desc": "Buscar, leer y crear páginas y bases de datos de tu espacio de Notion.",
     "line": "notion = NOTION_TOKEN={token} npx -y @notionhq/notion-mcp-server",
     "fields": {"token": ("Token de integración de Notion", "password", "Créalo en notion.so/profile/integrations y comparte con la integración las páginas que quieras.")}},
    {"id": "filesystem", "name": "Carpeta del equipo", "icon": "folder", "kind": "npx",
     "desc": "Acceso de lectura y escritura a una carpeta concreta mediante el servidor oficial de archivos de MCP.",
     "line": "carpeta = npx -y @modelcontextprotocol/server-filesystem \"{path}\"",
     "fields": {"path": ("Carpeta", "text", "Ruta completa de la carpeta.")}},
    {"id": "postgres", "name": "Base de datos PostgreSQL", "icon": "cube", "kind": "npx",
     "desc": "Consultas de sólo lectura a una base de datos PostgreSQL (ver tablas, sacar datos).",
     "line": "postgres = npx -y @modelcontextprotocol/server-postgres \"{url}\"",
     "fields": {"url": ("Cadena de conexión", "password", "postgresql://usuario:clave@servidor:5432/base")}},
    {"id": "memory", "name": "Memoria en grafo", "icon": "brain", "kind": "npx",
     "desc": "Un grafo de conocimiento persistente (personas, proyectos, relaciones) que la IA consulta y amplía.",
     "line": "grafo = npx -y @modelcontextprotocol/server-memory", "fields": {}},
    {"id": "thinking", "name": "Pensamiento paso a paso", "icon": "spark", "kind": "npx",
     "desc": "Ayuda a los modelos a planificar problemas difíciles en pasos que pueden revisar y corregir.",
     "line": "pensar = npx -y @modelcontextprotocol/server-sequential-thinking", "fields": {}},
    {"id": "remote", "name": "Conector remoto (URL)", "icon": "share", "kind": "remote",
     "desc": "Cualquier servidor MCP por HTTP: pega su URL y, si la pide, la clave.",
     "line": "{name} = TOKEN={token} {url}",
     "fields": {"name": ("Nombre", "text", "Una palabra, p. ej. «crm»."), "url": ("URL del servidor MCP", "text", "https://…/mcp"),
                "token": ("Clave (opcional)", "password", "Se envía como «Authorization: Bearer …».")}},
]


def node_available() -> bool:
    return bool(shutil.which("npx"))


def build_line(item: dict, values: dict) -> str:
    vals = {k: str(values.get(k) or "").strip() for k in item["fields"]}
    for k, (label, _t, _h) in item["fields"].items():
        if not vals[k] and "opcional" not in label:
            raise ValueError(f"Falta «{label}».")
        if '"' in vals[k] or "\n" in vals[k]:
            raise ValueError(f"«{label}» no puede llevar comillas ni saltos de línea.")
    if "name" in vals:
        vals["name"] = re.sub(r"[^\w.-]", "", vals["name"])[:30] or "remoto"
    line = item["line"].format(**vals)
    return re.sub(r"TOKEN= ", "", line)     # sin clave: sin cabecera
