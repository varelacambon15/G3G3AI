package com.g3g3ai.client;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/** Red sencilla para encontrar PCs con G3G3AI en la Wi-Fi y emparejarse con ellos (todo fuera del hilo de la interfaz). */
final class Net {
    static final int DISCOVERY_PORT = 8799;

    static final class Found {
        final String name;
        final String url;
        final String version;

        Found(String name, String url, String version) {
            this.name = name;
            this.url = url;
            this.version = version;
        }
    }

    private Net() {}

    /** Pregunta por difusión UDP quién tiene G3G3AI abierto en la red local y recoge las respuestas. */
    static List<Found> discover(int waitMs) {
        List<Found> out = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        DatagramSocket socket = null;
        try {
            socket = new DatagramSocket();
            socket.setBroadcast(true);
            Set<InetAddress> targets = new LinkedHashSet<>();
            targets.add(InetAddress.getByName("255.255.255.255"));
            List<NetworkInterface> nis = Collections.list(NetworkInterface.getNetworkInterfaces());
            for (NetworkInterface ni : nis) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InterfaceAddress ia : ni.getInterfaceAddresses()) {
                    if (ia.getBroadcast() != null) targets.add(ia.getBroadcast());
                }
            }
            byte[] query = "G3G3AI?".getBytes(StandardCharsets.UTF_8);
            long end = System.currentTimeMillis() + waitMs;
            long resendAt = System.currentTimeMillis() + waitMs / 2;
            boolean resent = false;
            sendAll(socket, targets, query);
            byte[] buf = new byte[1024];
            while (true) {
                long now = System.currentTimeMillis();
                if (now >= end) break;
                if (!resent && now >= resendAt) {
                    sendAll(socket, targets, query);   // una segunda vez, por si se perdió la primera
                    resent = true;
                }
                long next = resent ? end : resendAt;
                socket.setSoTimeout((int) Math.max(50, next - now));
                DatagramPacket p = new DatagramPacket(buf, buf.length);
                try {
                    socket.receive(p);
                } catch (SocketTimeoutException e) {
                    continue;
                }
                try {
                    JSONObject o = new JSONObject(new String(p.getData(), 0, p.getLength(), StandardCharsets.UTF_8));
                    if (!"g3g3ai".equals(o.optString("app"))) continue;
                    String url = "http://" + p.getAddress().getHostAddress() + ":" + o.optInt("port", 8800);
                    if (seen.add(url)) out.add(new Found(o.optString("name", url), url, o.optString("version")));
                } catch (JSONException ignored) {
                    // respuesta que no es de G3G3AI
                }
            }
        } catch (Exception ignored) {
            // sin red: lista vacía
        } finally {
            if (socket != null) socket.close();
        }
        return out;
    }

    private static void sendAll(DatagramSocket socket, Set<InetAddress> targets, byte[] data) {
        for (InetAddress t : targets) {
            try {
                socket.send(new DatagramPacket(data, data.length, t, DISCOVERY_PORT));
            } catch (Exception ignored) {
                // esa interfaz no admite difusión
            }
        }
    }

    /** Petición HTTP con JSON de respuesta; añade «_status» con el código HTTP. */
    static JSONObject http(String method, String url, String body, int timeoutMs) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        try {
            c.setRequestMethod(method);
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            if (body != null) {
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                c.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream out = c.getOutputStream()) {
                    out.write(bytes);
                }
            }
            int status = c.getResponseCode();
            InputStream in = status >= 400 ? c.getErrorStream() : c.getInputStream();
            String text = in == null ? "" : readAll(in);
            JSONObject o;
            try {
                o = new JSONObject(text);
            } catch (JSONException e) {
                o = new JSONObject();
            }
            o.put("_status", status);
            return o;
        } finally {
            c.disconnect();
        }
    }

    private static String readAll(InputStream in) throws Exception {
        try (InputStream is = in) {
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
            return new String(bos.toByteArray(), StandardCharsets.UTF_8);
        }
    }
}
