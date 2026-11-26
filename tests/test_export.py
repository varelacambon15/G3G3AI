from g3g3ai import office

CONV = {"title": "Nóminas / marzo", "messages": [
    {"role": "user", "content": "Compara las carpetas", "meta": {"attachments": [{"path": "/x/a.pdf"}]}},
    {"role": "tool", "content": "ignorado", "meta": None},
    {"role": "assistant", "content": "Faltan **3** archivos:\n\n- a\n- b", "meta": {"model": "org/Qwen3-8B.gguf", "tools": [{"name": "compare_dirs"}]}},
]}


def test_markdown_export():
    md = office.conversation_markdown(CONV, tools=True)
    assert md.startswith("# Nóminas / marzo")
    assert "## Tú" in md and "Adjuntos: a.pdf" in md and "## G3G3AI · Qwen3-8B" in md
    assert "ignorado" not in md and "compare_dirs" in md
    assert "compare_dirs" not in office.conversation_markdown(CONV)
    assert office.export_filename(CONV, "pdf") == "Nóminas marzo.pdf"


def test_docx_and_pdf_export():
    assert office.export_conversation(CONV, "docx")[:2] == b"PK"
    assert office.export_conversation(CONV, "pdf")[:4] == b"%PDF"
