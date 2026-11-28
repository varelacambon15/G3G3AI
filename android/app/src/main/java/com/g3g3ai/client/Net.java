package com.g3g3ai.client;

import android.app.Activity;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Red para conectar con un PC: descubrimiento UDP en la red local y emparejamiento
 * (código de 6 dígitos o QR de la página /m del PC) que devuelve la contraseña.
 * Todo en hilos propios; los resultados llegan por callbacks al hilo de la interfaz.
 */
final class Net {
    /** Versión del protocolo de descubrimiento (la misma que anuncia el servidor). */
    static final int DISCOVERY_PROTO = 1;

    interface Cb {
        void done(String error, JSONObject data);
    }

    private static final ExecutorService POOL = Executors.newCachedThreadPool();

    private Net() {}

    /** Ejecuta algo en el hilo de la interfaz (los callbacks tocan vistas). */
    static void ui(Activity a, Runnable r) {
        a.runOnUiThread(r);
    }

    // --- Descubrimiento UDP -----------------------------------------------------------------

    /**
     * Pregunta «¿hay PCs de G3G3AI?» por UDP (broadcast al puerto del servidor) y devuelve
     * el primero que responda: nombre, IP, puerto y URLs. El servidor limita a una
     * respuesta por segundo e IP; con un tiempo de espera corto basta.
     */
    static void discover(Activity a, int port, int timeoutMs, Cb cb) {
        POOL.execute(() -> {
            DatagramSocket s = null;
            try {
                s = new DatagramSocket();
                s.setSoTimeout(timeoutMs);
                s.setBroadcast(true);
                byte[] q = new JSONObject()
                        .put("g3g3ai", DISCOVERY_PROTO).put("q", "discover").toString().getBytes(StandardCharsets.UTF_8);
                s.send(new DatagramPacket(q, q.length, InetAddress.getByName("255.255.255.255"), port));
                byte[] buf = new byte[4096];
                DatagramPacket p = new DatagramPacket(buf, buf.length);
                s.receive(p);
                JSONObject d = new JSONObject(new String(buf, 0, p.getLength(), StandardCharsets.UTF_8));
                if (d.optInt("g3g3ai") != DISCOVERY_PROTO) throw new Exception("respuesta de protocolo desconocido");
                if (!d.has("urls")) d.put("urls", new org.json.JSONArray());
                ui(a, () -> cb.done(null, d));
            } catch (Exception e) {
                String m = e.getMessage() == null ? "sin respuesta" : e.getMessage();
                ui(a, () -> cb.done(m, null));
            } finally {
                if (s != null) s.close();
            }
        });
    }

    // --- Emparejamiento -----------------------------------------------------------------------

    /** Cambia el código de 6 dígitos (o el del QR de /m) por la contraseña del PC. */
    static void exchange(Activity a, String baseUrl, String code, Cb cb) {
        POOL.execute(() -> {
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(baseUrl + "/api/pair/exchange").openConnection();
                conn.setRequestMethod("POST");
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(15000);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json");
                byte[] body = new JSONObject().put("code", code == null ? "" : code.trim()).toString().getBytes(StandardCharsets.UTF_8);
                conn.setFixedLengthStreamingMode(body.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(body);
                }
                int status = conn.getResponseCode();
                String text = read(conn, status);
                if (status >= 400) throw new Exception(status == 401 ? "Código incorrecto o caducado" : "HTTP " + status);
                JSONObject d = new JSONObject(text);
                if (d.optString("token", "").isEmpty()) throw new Exception("El PC no devolvió la contraseña");
                ui(a, () -> cb.done(null, d));
            } catch (Exception e) {
                String m = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
                ui(a, () -> cb.done(m, null));
            } finally {
                if (conn != null) conn.disconnect();
            }
        });
    }

    /** Comprueba /api/status con la contraseña: «en línea» o el motivo del fallo. */
    static void check(Activity a, String baseUrl, String token, Cb cb) {
        POOL.execute(() -> {
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(baseUrl + "/api/status").openConnection();
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(10000);
                conn.setRequestProperty("Authorization", "Bearer " + token);
                int status = conn.getResponseCode();
                String text = read(conn, status);
                if (status >= 400) throw new Exception(status == 401 ? "Contraseña incorrecta" : "HTTP " + status);
                JSONObject d = new JSONObject(text);
                d.put("url", baseUrl);
                ui(a, () -> cb.done(null, d));
            } catch (Exception e) {
                String m = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
                ui(a, () -> cb.done(m, null));
            } finally {
                if (conn != null) conn.disconnect();
            }
        });
    }

    private static String read(HttpURLConnection c, int status) throws Exception {
        try (BufferedReader r = new BufferedReader(new InputStreamReader(
                status >= 400 ? c.getErrorStream() : c.getInputStream(), StandardCharsets.UTF_8))) {
            StringBuilder b = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) b.append(line);
            return b.toString();
        }
    }
}
