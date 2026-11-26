package com.g3g3ai.client;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.util.Base64;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * «Compartir con G3G3AI» desde cualquier app: texto, enlaces, fotos y documentos. Lee lo compartido,
 * lo deja preparado en {@link #pending} y abre el último equipo usado (o el chat directo si no hay equipos);
 * la página lo coloca en el cuadro de texto sin enviarlo.
 */
public class ShareActivity extends Activity {
    static final long MAX_FILE = 25L * 1024 * 1024;   // por archivo
    /** JSON {"text": "...", "files": [{"name","mime","data"(base64)}]} pendiente de entregar a la página. */
    static volatile String pending;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Intent in = getIntent();
        new Thread(() -> {
            String json;
            int skipped = 0;
            try {
                JSONObject out = new JSONObject();
                String text = in.getStringExtra(Intent.EXTRA_TEXT);
                String subject = in.getStringExtra(Intent.EXTRA_SUBJECT);
                StringBuilder t = new StringBuilder();
                if (subject != null && !subject.isEmpty() && (text == null || !text.contains(subject))) t.append(subject).append("\n\n");
                if (text != null) t.append(text);
                out.put("text", t.toString().trim());
                List<Uri> uris = new ArrayList<>();
                if (Intent.ACTION_SEND_MULTIPLE.equals(in.getAction())) {
                    ArrayList<Uri> list = in.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
                    if (list != null) uris.addAll(list);
                } else {
                    Uri u = in.getParcelableExtra(Intent.EXTRA_STREAM);
                    if (u != null) uris.add(u);
                }
                JSONArray files = new JSONArray();
                for (Uri u : uris) {
                    byte[] data = read(u);
                    if (data == null) { skipped++; continue; }
                    String mime = getContentResolver().getType(u);
                    files.put(new JSONObject().put("name", nameOf(u)).put("mime", mime == null ? "application/octet-stream" : mime)
                            .put("data", Base64.encodeToString(data, Base64.NO_WRAP)));
                }
                out.put("files", files);
                json = out.toString();
            } catch (Exception e) {
                json = null;
            }
            final String result = json;
            final int skippedFinal = skipped;
            runOnUiThread(() -> deliver(result, skippedFinal));
        }).start();
    }

    private void deliver(String json, int skipped) {
        if (json == null) {
            Toast.makeText(this, "No se pudo leer lo compartido", Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        if (skipped > 0) Toast.makeText(this, skipped + " archivo(s) omitidos: superan 25 MB o no se pudieron leer", Toast.LENGTH_LONG).show();
        pending = json;
        Intent web = new Intent(this, WebActivity.class);
        List<Servers.Server> servers = Servers.load(this);
        int last = Servers.lastIndex(this);
        if (last >= 0 && last < servers.size()) {
            Servers.Server s = servers.get(last);
            web.putExtra("url", s.url);
            web.putExtra("token", s.token);
        } else {
            web.putExtra("direct", true);
        }
        web.putExtra("share", true);
        web.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        startActivity(web);
        finish();
    }

    private byte[] read(Uri u) {
        try (InputStream is = getContentResolver().openInputStream(u)) {
            if (is == null) return null;
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[64 * 1024];
            int n;
            long total = 0;
            while ((n = is.read(buf)) > 0) {
                total += n;
                if (total > MAX_FILE) return null;
                bo.write(buf, 0, n);
            }
            return bo.toByteArray();
        } catch (Exception e) {
            return null;
        }
    }

    private String nameOf(Uri u) {
        try (Cursor c = getContentResolver().query(u, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                String n = c.getString(0);
                if (n != null && !n.isEmpty()) return n;
            }
        } catch (Exception ignored) {
            // sin nombre: se usa el final de la ruta
        }
        String p = u.getLastPathSegment();
        return p == null ? "archivo" : p;
    }
}
