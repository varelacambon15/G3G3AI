package com.g3g3ai.client;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** Servidores G3G3AI guardados (Konkr, PC...): nombre, dirección y contraseña. */
final class Servers {
    static final class Server {
        String name;
        String url;
        String token;

        Server(String name, String url, String token) {
            this.name = name;
            this.url = url;
            this.token = token;
        }
    }

    private static final String PREFS = "g3g3ai";

    private Servers() {}

    static List<Server> load(Context c) {
        List<Server> out = new ArrayList<>();
        try {
            JSONArray arr = new JSONArray(prefs(c).getString("servers", "[]"));
            for (int i = 0; i < arr.length(); i++) {
                JSONObject o = arr.getJSONObject(i);
                out.add(new Server(o.optString("name"), o.optString("url"), o.optString("token")));
            }
        } catch (JSONException ignored) {
            // lista vacía si los datos están dañados
        }
        return out;
    }

    static void save(Context c, List<Server> list) {
        JSONArray arr = new JSONArray();
        try {
            for (Server s : list) {
                arr.put(new JSONObject().put("name", s.name).put("url", s.url).put("token", s.token));
            }
        } catch (JSONException ignored) {
            return;
        }
        prefs(c).edit().putString("servers", arr.toString()).apply();
    }

    static int lastIndex(Context c) {
        return prefs(c).getInt("last", -1);
    }

    static void setLast(Context c, int i) {
        prefs(c).edit().putInt("last", i).apply();
    }

    /** Acepta "192.168.1.50", "192.168.1.50:8800" o una URL completa. */
    static String normalize(String raw) {
        String u = raw.trim();
        if (u.isEmpty()) return u;
        if (!u.startsWith("http://") && !u.startsWith("https://")) u = "http://" + u;
        while (u.endsWith("/")) u = u.substring(0, u.length() - 1);
        String hostPart = u.replaceFirst("^https?://", "");
        if (!hostPart.contains(":") && !hostPart.contains("/")) u = u + ":8800";
        return u;
    }

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
