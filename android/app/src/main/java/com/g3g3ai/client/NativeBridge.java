package com.g3g3ai.client;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Puente para el «Chat directo»: hace las peticiones HTTP a las APIs desde la app (sin CORS),
 * devolviendo la respuesta línea a línea para el streaming, y guarda claves y ajustes en el
 * almacenamiento privado de la app. Sólo se expone a la página empaquetada en la APK, nunca a
 * páginas cargadas desde un servidor.
 */
final class NativeBridge {
    private final Activity activity;
    private final WebView web;
    private final Map<String, HttpURLConnection> active = new ConcurrentHashMap<>();
    private final Set<String> aborted = ConcurrentHashMap.newKeySet();
    private final ExecutorService pool = Executors.newCachedThreadPool();
    private final SharedPreferences prefs;

    NativeBridge(Activity activity, WebView web) {
        this.activity = activity;
        this.web = web;
        this.prefs = activity.getSharedPreferences("g3direct", Context.MODE_PRIVATE);
    }

    @JavascriptInterface
    public void request(String id, String method, String url, String headersJson, String body) {
        pool.execute(() -> run(id, method, url, headersJson, body));
    }

    @JavascriptInterface
    public void abort(String id) {
        aborted.add(id);
        HttpURLConnection c = active.get(id);
        if (c != null) pool.execute(c::disconnect);
    }

    @JavascriptInterface
    public String getStore(String key) {
        return prefs.getString(key, "");
    }

    @JavascriptInterface
    public void setStore(String key, String value) {
        prefs.edit().putString(key, value).apply();
    }

    /** Equipos guardados en la app (para importar sus APIs). */
    @JavascriptInterface
    public String getServers() {
        JSONArray arr = new JSONArray();
        try {
            for (Servers.Server s : Servers.load(activity)) {
                arr.put(new JSONObject().put("name", s.name).put("url", s.url).put("token", s.token));
            }
        } catch (JSONException ignored) {
            // lista vacía
        }
        return arr.toString();
    }

    private void run(String id, String method, String url, String headersJson, String body) {
        HttpURLConnection c = null;
        try {
            if (!url.startsWith("https://") && !url.startsWith("http://")) {
                emit(id, "error", "Sólo se permiten direcciones http(s)");
                return;
            }
            c = (HttpURLConnection) new URL(url).openConnection();
            active.put(id, c);
            c.setRequestMethod(method);
            c.setConnectTimeout(20000);
            c.setReadTimeout(600000);
            JSONObject headers = new JSONObject(headersJson == null || headersJson.isEmpty() ? "{}" : headersJson);
            for (Iterator<String> it = headers.keys(); it.hasNext(); ) {
                String k = it.next();
                c.setRequestProperty(k, headers.getString(k));
            }
            if (body != null && !body.isEmpty()) {
                c.setDoOutput(true);
                if (!headers.has("content-type") && !headers.has("Content-Type")) {
                    c.setRequestProperty("Content-Type", "application/json");
                }
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                c.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream out = c.getOutputStream()) {
                    out.write(bytes);
                }
            }
            int status = c.getResponseCode();
            emit(id, "status", String.valueOf(status));
            InputStream in = status >= 400 ? c.getErrorStream() : c.getInputStream();
            if (in != null) {
                try (BufferedReader r = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = r.readLine()) != null) emit(id, "line", line);
                }
            }
            emit(id, "end", "");
        } catch (Exception e) {
            if (aborted.contains(id)) emit(id, "end", "");  // detenido por el usuario: no es un error
            else emit(id, "error", e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally {
            active.remove(id);
            aborted.remove(id);
            if (c != null) c.disconnect();
        }
    }

    private void emit(String id, String kind, String data) {
        String js = "window.__g3net(" + JSONObject.quote(id) + "," + JSONObject.quote(kind) + ","
                + JSONObject.quote(data == null ? "" : data) + ")";
        activity.runOnUiThread(() -> web.evaluateJavascript(js, null));
    }

    void shutdown() {
        for (String id : active.keySet()) abort(id);
        pool.shutdownNow();
    }
}
