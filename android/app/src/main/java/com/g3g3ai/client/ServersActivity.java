package com.g3g3ai.client;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.Menu;
import android.view.MenuItem;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * Pantalla inicial: lista de equipos con G3G3AI a los que conectarse.
 * Además de añadirlos a mano, puede encontrarlos en la red (UDP), emparejarse con el
 * código de 6 dígitos que muestra el PC o con el QR de su página /m, y muestra si
 * cada equipo está en línea.
 */
public class ServersActivity extends Activity {
    /** Enlace de emparejamiento que deja WebActivity al volver del QR del PC (g3g3ai://paired). */
    static String pendingPair = null;

    private LinearLayout listBox;
    private TextView statusLine;
    private final List<TextView> onlineViews = new ArrayList<>();
    private JSONObject discovered = null;   // último PC encontrado en la red

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setTitle("G3G3AI · Equipos");
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(18);
        root.setPadding(pad, pad, pad, pad);
        scroll.addView(root);

        TextView intro = new TextView(this);
        intro.setText("Conéctate a G3G3AI en tu PC. Ambos deben estar en la misma Wi-Fi que el móvil "
                + "(o en Tailscale). Lo más fácil: abre G3G3AI en el PC y usa Ajustes → Acceso → Conectar el móvil.");
        intro.setTextColor(Color.parseColor("#75716A"));
        intro.setTextSize(14);
        root.addView(intro);

        statusLine = new TextView(this);
        statusLine.setTextColor(Color.parseColor("#75716A"));
        statusLine.setTextSize(13);
        statusLine.setPadding(0, dp(8), 0, 0);
        root.addView(statusLine);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams rl = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        rl.topMargin = dp(14);
        row.setLayoutParams(rl);
        TextView search = button("🔍 Buscar en la red", "#1F1E1D");
        TextView link = button("🔗 Enlazar con QR", "#1F1E1D");
        LinearLayout.LayoutParams half1 = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        half1.rightMargin = dp(6);
        search.setLayoutParams(half1);
        LinearLayout.LayoutParams half2 = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        half2.leftMargin = dp(6);
        link.setLayoutParams(half2);
        search.setOnClickListener(v -> discoverFlow());
        link.setOnClickListener(v -> qrLinkFlow());
        row.addView(search);
        row.addView(link);
        root.addView(row);

        TextView direct = button("💬 Chat directo con API (sin equipo)", "#1F1E1D");
        LinearLayout.LayoutParams dlp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        dlp.topMargin = dp(10);
        direct.setLayoutParams(dlp);
        direct.setOnClickListener(v -> {
            Intent i = new Intent(this, WebActivity.class);
            i.putExtra("direct", true);
            startActivity(i);
        });
        root.addView(direct);
        TextView hint = new TextView(this);
        hint.setText("Habla directamente con DeepSeek, Claude, OpenAI… con tus claves (puedes importarlas de un equipo).");
        hint.setTextColor(Color.parseColor("#75716A"));
        hint.setTextSize(12);
        hint.setPadding(0, dp(4), 0, 0);
        root.addView(hint);

        listBox = new LinearLayout(this);
        listBox.setOrientation(LinearLayout.VERTICAL);
        listBox.setPadding(0, dp(14), 0, dp(14));
        root.addView(listBox);

        TextView add = button("＋ Añadir equipo a mano", "#C2603F");
        add.setOnClickListener(v -> edit(-1));
        root.addView(add);
        setContentView(scroll);

        // Abre directamente el último equipo usado (la flecha atrás vuelve aquí)
        if (savedInstanceState == null && !getIntent().getBooleanExtra("noauto", false)) {
            int last = Servers.lastIndex(this);
            if (last >= 0 && last < Servers.load(this).size()) {
                open(last);
            }
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        render();
        checkOnline();
        if (pendingPair != null) {
            String json = pendingPair;
            pendingPair = null;
            savePaired(json);
        }
    }

    private void render() {
        listBox.removeAllViews();
        onlineViews.clear();
        List<Servers.Server> servers = Servers.load(this);
        if (servers.isEmpty()) {
            TextView empty = new TextView(this);
            empty.setText("Aún no hay equipos. Búscalos en la red, enlaza el QR del PC o añade uno a mano.");
            empty.setPadding(0, dp(12), 0, dp(12));
            listBox.addView(empty);
        }
        for (int i = 0; i < servers.size(); i++) {
            final int idx = i;
            Servers.Server s = servers.get(i);
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(dp(16), dp(14), dp(16), dp(14));
            card.setBackgroundColor(Color.WHITE);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            lp.bottomMargin = dp(10);
            card.setLayoutParams(lp);
            TextView name = new TextView(this);
            name.setText(s.name.isEmpty() ? s.url : s.name);
            name.setTextSize(17);
            name.setTypeface(Typeface.DEFAULT_BOLD);
            name.setTextColor(Color.parseColor("#1F1E1D"));
            TextView url = new TextView(this);
            url.setText(s.url + "   ·   mantén pulsado para editar");
            url.setTextSize(13);
            url.setTextColor(Color.parseColor("#75716A"));
            TextView online = new TextView(this);
            online.setTextSize(13);
            online.setText("●  comprobando…");
            online.setTextColor(Color.parseColor("#9a938a"));
            card.addView(name);
            card.addView(url);
            card.addView(online);
            card.setOnClickListener(v -> open(idx));
            card.setOnLongClickListener(v -> { edit(idx); return true; });
            listBox.addView(card);
            onlineViews.add(online);
        }
    }

    /** Comprueba cada equipo guardado y pinta «En línea» o el motivo en su tarjeta. */
    private void checkOnline() {
        List<Servers.Server> servers = Servers.load(this);
        for (int i = 0; i < servers.size() && i < onlineViews.size(); i++) {
            final int idx = i;
            Servers.Server s = servers.get(i);
            Net.check(this, s.url, s.token, (err, data) -> {
                TextView v = idx < onlineViews.size() ? onlineViews.get(idx) : null;
                if (v == null) return;
                if (err != null) {
                    v.setText("●  No responde: " + err);
                    v.setTextColor(Color.parseColor("#b3543e"));
                } else {
                    String host = data == null ? "" : data.optString("hostname", "");
                    v.setText("●  En línea" + (host.isEmpty() ? "" : " · " + host));
                    v.setTextColor(Color.parseColor("#3e7a3e"));
                }
            });
        }
    }

    // --- Buscar en la red (UDP) -----------------------------------------------------------

    private void discoverFlow() {
        discovered = null;
        statusLine.setText("Buscando PCs con G3G3AI en tu red…");
        Net.discover(this, 8800, 2500, (err, data) -> {
            if (err != null || data == null) {
                statusLine.setText("No se encontró ningún PC. Asegúrate de que G3G3AI está abierto en el "
                        + "ordenador y de que ambos comparten Wi-Fi; también puedes añadirlo a mano.");
                askAddress("No se encontró ningún PC", "Escribe la dirección del PC (p.ej. 192.168.1.50)");
                return;
            }
            discovered = data;
            String name = data.optString("name", "PC");
            String host = data.optString("host", "");
            int port = data.optInt("port", 8800);
            statusLine.setText("Encontrado: " + name + " (" + host + ":" + port + ")");
            new AlertDialog.Builder(this)
                    .setTitle("PC encontrado: " + name)
                    .setMessage(host + ":" + port + "\n\nPara conectarlo hay que emparejarlo: "
                            + "en el PC abre Ajustes → Acceso → Conectar el móvil y usa el código o el QR.")
                    .setPositiveButton("Emparejar con código", (d, w) -> pairCodeFlow(baseUrl(host, port), name))
                    .setNeutralButton("Guardar sin emparejar", (d, w) -> saveServer(name, baseUrl(host, port), ""))
                    .setNegativeButton("Cancelar", null)
                    .show();
        });
    }

    private static String baseUrl(String host, int port) {
        return "http://" + host + ":" + port;
    }

    // --- Emparejamiento con el código del PC ------------------------------------------------

    private void pairCodeFlow(String base, String nameHint) {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(20), dp(8), dp(20), 0);
        TextView tip = new TextView(this);
        tip.setText("Escribe el código de 6 dígitos que aparece en el PC\n(" + base + ")");
        tip.setTextSize(13);
        tip.setTextColor(Color.parseColor("#75716A"));
        EditText code = field("······", "", InputType.TYPE_CLASS_NUMBER);
        code.setTextAlignment(TextView.TEXT_ALIGNMENT_CENTER);
        form.addView(tip);
        form.addView(code);
        new AlertDialog.Builder(this)
                .setTitle("Emparejar con " + (nameHint == null || nameHint.isEmpty() ? "el PC" : nameHint))
                .setView(form)
                .setPositiveButton("Emparejar", (d, w) -> {
                    String c = code.getText().toString().trim();
                    if (c.length() != 6) { toast("Son 6 dígitos"); return; }
                    Net.exchange(this, base, c, (err, data) -> {
                        if (err != null || data == null) { toast("No se pudo emparejar: " + err); return; }
                        finishPairing(base, data.optString("token"));
                    });
                })
                .setNegativeButton("Cancelar", null)
                .show();
    }

    // --- Enlace del QR del PC (página /m) -----------------------------------------------------

    private void qrLinkFlow() {
        if (discovered == null) {
            askAddress("Enlazar con el QR del PC", "Dirección del PC (p.ej. 192.168.1.50)");
            return;
        }
        openPairPage(baseUrl(discovered.optString("host", ""), discovered.optInt("port", 8800)));
    }

    private void openPairPage(String base) {
        Intent i = new Intent(this, WebActivity.class);
        i.putExtra("url", base);
        i.putExtra("pair", true);
        startActivity(i);
    }

    /** Recibe {urls, token} del QR (g3g3ai://paired) y guarda el equipo. */
    private void savePaired(String json) {
        try {
            JSONObject o = new JSONObject(json);
            JSONArray urls = o.optJSONArray("urls");
            String token = o.optString("token", "");
            String base = urls != null && urls.length() > 0 ? urls.getString(0) : "";
            if (base.isEmpty() || token.isEmpty()) { toast("El QR no traía los datos completos"); return; }
            finishPairing(base, token);
        } catch (Exception e) {
            toast("No se pudo leer el emparejamiento");
        }
    }

    /** Con la contraseña ya en la mano: nombre (hostname del PC) + guardar + abrir. */
    private void finishPairing(String base, String token) {
        Net.check(this, base, token, (err, data) -> {
            String name = (err == null && data != null) ? data.optString("hostname", "") : "";
            saveServer(name.isEmpty() ? base : name, base, token);
            toast("Equipo guardado: " + (name.isEmpty() ? base : name));
            List<Servers.Server> all = Servers.load(this);
            open(all.size() - 1);
        });
    }

    private void saveServer(String name, String url, String token) {
        List<Servers.Server> servers = Servers.load(this);
        for (int i = 0; i < servers.size(); i++) {
            if (servers.get(i).url.equals(url)) {   // ya estaba: actualiza nombre y contraseña
                servers.set(i, new Servers.Server(name, url, token));
                Servers.save(this, servers);
                Servers.setLast(this, i);
                render();
                checkOnline();
                return;
            }
        }
        servers.add(new Servers.Server(name, url, token));
        Servers.save(this, servers);
        Servers.setLast(this, servers.size() - 1);
        render();
        checkOnline();
    }

    private void askAddress(String title, String hint) {
        EditText url = field(hint, "", InputType.TYPE_TEXT_VARIATION_URI);
        new AlertDialog.Builder(this)
                .setTitle(title)
                .setView(url)
                .setPositiveButton("Continuar", (d, w) -> {
                    String u = Servers.normalize(url.getText().toString());
                    if (u.isEmpty()) return;
                    if (title.startsWith("Enlazar")) openPairPage(u);
                    else pairCodeFlow(u, "");
                })
                .setNegativeButton("Cancelar", null)
                .show();
    }

    // --- Lista: abrir y editar ----------------------------------------------------------------

    private void open(int idx) {
        List<Servers.Server> servers = Servers.load(this);
        if (idx < 0 || idx >= servers.size()) return;
        Servers.setLast(this, idx);
        Servers.Server s = servers.get(idx);
        Intent i = new Intent(this, WebActivity.class);
        i.putExtra("url", s.url);
        i.putExtra("token", s.token);
        i.putExtra("name", s.name);
        startActivity(i);
    }

    private void edit(int idx) {
        List<Servers.Server> servers = Servers.load(this);
        Servers.Server cur = idx >= 0 ? servers.get(idx) : null;
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(20), dp(8), dp(20), 0);
        EditText name = field("Nombre (p.ej. Portátil)", cur != null ? cur.name : "", InputType.TYPE_CLASS_TEXT);
        EditText url = field("Dirección (p.ej. 192.168.1.50)", cur != null ? cur.url : "", InputType.TYPE_TEXT_VARIATION_URI);
        EditText token = field("Contraseña", cur != null ? cur.token : "",
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
        form.addView(name);
        form.addView(url);
        form.addView(token);
        AlertDialog.Builder b = new AlertDialog.Builder(this)
                .setTitle(cur == null ? "Añadir equipo" : "Editar equipo")
                .setView(form)
                .setPositiveButton("Guardar", (d, w) -> {
                    String u = Servers.normalize(url.getText().toString());
                    if (u.isEmpty()) return;
                    Servers.Server s = new Servers.Server(name.getText().toString().trim(), u, token.getText().toString().trim());
                    if (cur == null) servers.add(s); else servers.set(idx, s);
                    Servers.save(this, servers);
                    render();
                    checkOnline();
                })
                .setNegativeButton("Cancelar", null);
        if (cur != null) {
            b.setNeutralButton("Borrar", (d, w) -> {
                servers.remove(idx);
                Servers.save(this, servers);
                Servers.setLast(this, -1);
                render();
            });
        }
        b.show();
    }

    private EditText field(String hint, String value, int type) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setText(value);
        e.setInputType(type);
        e.setSingleLine(true);
        return e;
    }

    private TextView button(String text, String bg) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextSize(15);
        t.setGravity(Gravity.CENTER);
        t.setTextColor(Color.WHITE);
        t.setBackgroundColor(Color.parseColor(bg));
        t.setPadding(dp(16), dp(14), dp(16), dp(14));
        return t;
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show();
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, 1, 0, "Acerca de");
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == 1) {
            new AlertDialog.Builder(this).setTitle("G3G3AI")
                    .setMessage("Cliente de G3G3AI (versión de prueba). La IA se ejecuta en tu PC; "
                            + "esta app sólo se conecta a ellos.")
                    .setPositiveButton("OK", null).show();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
