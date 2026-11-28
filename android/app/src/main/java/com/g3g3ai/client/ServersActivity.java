package com.g3g3ai.client;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
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

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Pantalla inicial: tus PCs con G3G3AI (con su estado), búsqueda en la red, emparejamiento por código o QR y chat directo. */
public class ServersActivity extends Activity {
    private static final int BG = Color.parseColor("#FAF9F5");
    private static final int DARK = Color.parseColor("#1F1E1D");
    private static final int MUTED = Color.parseColor("#75716A");
    private static final int ACCENT = Color.parseColor("#C2603F");
    private static final int GREEN = Color.parseColor("#3F8F5B");
    private static final int LINE = Color.parseColor("#E6E3DA");

    private LinearLayout listBox;
    private int renderGen = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setTitle("G3G3AI");
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(18);
        root.setPadding(pad, pad, pad, pad);
        scroll.addView(root);

        TextView title = text("G3G3AI", 26, DARK, true);
        root.addView(title);
        TextView intro = text("Maneja el chat de tu PC desde el móvil, o habla directamente con tus APIs.", 14, MUTED, false);
        intro.setPadding(0, dp(2), 0, dp(14));
        root.addView(intro);

        root.addView(heading("Mis equipos"));
        listBox = new LinearLayout(this);
        listBox.setOrientation(LinearLayout.VERTICAL);
        root.addView(listBox);

        TextView find = button("🔍  Buscar equipos en mi red", true);
        find.setOnClickListener(v -> findOnNetwork());
        root.addView(find, margins(dp(4), 0));
        TextView hintFind = text("En el PC: Ajustes → Acceso → «Conectar el móvil». También puedes escanear su QR con la cámara.", 12, MUTED, false);
        hintFind.setPadding(0, dp(4), 0, dp(10));
        root.addView(hintFind);
        TextView add = button("＋  Añadir equipo a mano", false);
        add.setOnClickListener(v -> edit(-1));
        root.addView(add, margins(0, 0));

        root.addView(heading("Sin PC"));
        TextView direct = button("💬  Chat directo con API", false);
        direct.setOnClickListener(v -> {
            Intent i = new Intent(this, WebActivity.class);
            i.putExtra("direct", true);
            startActivity(i);
        });
        root.addView(direct, margins(0, 0));
        TextView hint = text("Habla con OpenCode Go, DeepSeek, Claude, OpenAI… usando tus claves (puedes importarlas de un equipo). "
                + "Fija conversaciones, márcalas como favoritas y mira lo que te queda de plan.", 12, MUTED, false);
        hint.setPadding(0, dp(4), 0, 0);
        root.addView(hint);
        setContentView(scroll);

        boolean linked = handleLink(getIntent());
        // Abre directamente el último equipo usado (la flecha atrás vuelve aquí)
        if (!linked && savedInstanceState == null && !getIntent().getBooleanExtra("noauto", false)) {
            int last = Servers.lastIndex(this);
            if (last >= 0 && last < Servers.load(this).size()) {
                open(last);
            }
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleLink(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        render();
    }

    /** Enlace del QR: g3g3ai://pair?u=http://IP:8800,...&c=123456&n=Nombre → empareja y abre. */
    private boolean handleLink(Intent intent) {
        Uri d = intent == null ? null : intent.getData();
        if (d == null || !"g3g3ai".equals(d.getScheme())) return false;
        String code = d.getQueryParameter("c");
        String urls = d.getQueryParameter("u");
        String name = d.getQueryParameter("n");
        intent.setData(null);   // para no repetirlo al girar la pantalla
        if (code == null || urls == null || urls.isEmpty()) return false;
        pairAndAdd(new ArrayList<>(Arrays.asList(urls.split(","))), code, name == null ? "" : name);
        return true;
    }

    // --- Lista de equipos con su estado --------------------------------------------------------
    private void render() {
        listBox.removeAllViews();
        final int gen = ++renderGen;
        List<Servers.Server> servers = Servers.load(this);
        if (servers.isEmpty()) {
            TextView empty = text("Aún no hay equipos. Pulsa «Buscar equipos en mi red».", 14, MUTED, false);
            empty.setPadding(0, dp(6), 0, dp(10));
            listBox.addView(empty);
        }
        for (int i = 0; i < servers.size(); i++) {
            final int idx = i;
            final Servers.Server s = servers.get(i);
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(dp(16), dp(14), dp(16), dp(14));
            card.setBackground(rounded(Color.WHITE, 14, LINE));
            card.setLayoutParams(margins(0, dp(10)));
            TextView name = text(s.name.isEmpty() ? s.url : s.name, 17, DARK, true);
            final TextView status = text("○ Comprobando…", 13, MUTED, false);
            TextView url = text(s.url + "   ·   mantén pulsado para editar", 12, MUTED, false);
            card.addView(name);
            card.addView(status);
            card.addView(url);
            card.setOnClickListener(v -> open(idx));
            card.setOnLongClickListener(v -> { edit(idx); return true; });
            listBox.addView(card);
            new Thread(() -> {
                String msg;
                int color;
                try {
                    JSONObject o = Net.http("GET", s.url + "/api/discover", null, 2500);
                    int st = o.optInt("_status");
                    if (st == 200 && "g3g3ai".equals(o.optString("app"))) {
                        msg = "● En línea · versión " + o.optString("version");
                        color = GREEN;
                    } else if (st == 401 || st == 403) {
                        msg = "● En línea";
                        color = GREEN;
                    } else {
                        msg = "● Responde, pero no parece G3G3AI";
                        color = ACCENT;
                    }
                } catch (Exception e) {
                    msg = "○ Sin respuesta (¿PC apagado o en otra red?)";
                    color = MUTED;
                }
                final String m = msg;
                final int c = color;
                runOnUiThread(() -> {
                    if (gen == renderGen) {
                        status.setText(m);
                        status.setTextColor(c);
                    }
                });
            }).start();
        }
    }

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

    // --- Buscar equipos en la red y emparejar ---------------------------------------------------
    private void findOnNetwork() {
        Toast.makeText(this, "Buscando equipos en tu Wi-Fi…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            final List<Net.Found> found = Net.discover(2500);
            runOnUiThread(() -> showFound(found));
        }).start();
    }

    private void showFound(List<Net.Found> found) {
        if (isFinishing()) return;
        if (found.isEmpty()) {
            new AlertDialog.Builder(this)
                    .setTitle("No encontré ningún equipo")
                    .setMessage("Comprueba que G3G3AI está abierto en el PC y que el móvil está en la misma Wi-Fi. "
                            + "También puedes escanear con la cámara el QR de Ajustes → Acceso del PC, o añadir el equipo a mano.")
                    .setPositiveButton("Añadir a mano", (d, w) -> edit(-1))
                    .setNegativeButton("Cerrar", null)
                    .show();
            return;
        }
        String[] labels = new String[found.size()];
        for (int i = 0; i < found.size(); i++) {
            Net.Found f = found.get(i);
            labels[i] = f.name + "\n" + f.url + (f.version.isEmpty() ? "" : "  ·  v" + f.version);
        }
        new AlertDialog.Builder(this)
                .setTitle("Equipos encontrados")
                .setItems(labels, (d, which) -> askCode(found.get(which)))
                .setNegativeButton("Cancelar", null)
                .show();
    }

    private void askCode(Net.Found f) {
        List<Servers.Server> saved = Servers.load(this);
        for (int i = 0; i < saved.size(); i++) {
            if (saved.get(i).url.equalsIgnoreCase(f.url) && !saved.get(i).token.isEmpty()) {
                open(i);   // ya lo tienes guardado
                return;
            }
        }
        final EditText code = field("Código de 6 cifras", "", InputType.TYPE_CLASS_NUMBER);
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(20), dp(8), dp(20), 0);
        form.addView(code);
        new AlertDialog.Builder(this)
                .setTitle("Conectar con " + f.name)
                .setMessage("En el PC abre Ajustes → Acceso → «Conectar el móvil» y escribe el código que aparece.")
                .setView(form)
                .setPositiveButton("Conectar", (d, w) -> pairAndAdd(new ArrayList<>(Arrays.asList(f.url)),
                        code.getText().toString(), f.name))
                .setNegativeButton("Cancelar", null)
                .show();
    }

    /** Cambia el código por la contraseña del PC (la primera dirección que responda), lo guarda y lo abre. */
    private void pairAndAdd(final List<String> urls, final String rawCode, final String name) {
        final String code = rawCode.replaceAll("[^0-9]", "");
        if (code.length() != 6) {
            Toast.makeText(this, "El código tiene 6 cifras", Toast.LENGTH_LONG).show();
            return;
        }
        Toast.makeText(this, "Conectando…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            String error = "No se pudo contactar con el equipo";
            String okUrl = null;
            String token = null;
            String pcName = name;
            for (String u : urls) {
                String base = Servers.normalize(u);
                try {
                    JSONObject o = Net.http("POST", base + "/api/pair", "{\"code\":\"" + code + "\"}", 6000);
                    int st = o.optInt("_status");
                    if (st == 200 && o.has("token")) {
                        okUrl = base;
                        token = o.optString("token");
                        if (!o.optString("name").isEmpty()) pcName = o.optString("name");
                        break;
                    }
                    error = o.optString("detail", "El equipo respondió " + st);
                    if (st == 401) break;   // código mal: no sirve probar otra dirección
                } catch (Exception e) {
                    error = "No se pudo contactar con " + base + ". ¿Misma Wi-Fi?";
                }
            }
            final String fUrl = okUrl;
            final String fToken = token;
            final String fName = pcName;
            final String fError = error;
            runOnUiThread(() -> {
                if (isFinishing()) return;
                if (fUrl == null) {
                    new AlertDialog.Builder(this).setTitle("No se pudo conectar").setMessage(fError)
                            .setPositiveButton("OK", null).show();
                    return;
                }
                int idx = Servers.upsert(this, fName, fUrl, fToken);
                render();
                open(idx);
            });
        }).start();
    }

    // --- Añadir / editar a mano -------------------------------------------------------------------
    private void edit(int idx) {
        List<Servers.Server> servers = Servers.load(this);
        Servers.Server cur = idx >= 0 ? servers.get(idx) : null;
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(20), dp(8), dp(20), 0);
        EditText name = field("Nombre (p.ej. Portátil)", cur != null ? cur.name : "", InputType.TYPE_CLASS_TEXT);
        EditText url = field("Dirección (p.ej. 192.168.1.50)", cur != null ? cur.url : "", InputType.TYPE_TEXT_VARIATION_URI);
        EditText token = field("Contraseña o código de 6 cifras", cur != null ? cur.token : "",
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
                    String secret = token.getText().toString().trim();
                    if (secret.matches("\\d{6}")) {   // un código de emparejamiento: se cambia por la contraseña
                        pairAndAdd(new ArrayList<>(Arrays.asList(u)), secret, name.getText().toString().trim());
                        return;
                    }
                    Servers.Server s = new Servers.Server(name.getText().toString().trim(), u, secret);
                    if (cur == null) servers.add(s); else servers.set(idx, s);
                    Servers.save(this, servers);
                    render();
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

    // --- Utilidades de interfaz -------------------------------------------------------------------
    private EditText field(String hint, String value, int type) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setText(value);
        e.setInputType(type);
        e.setSingleLine(true);
        return e;
    }

    private TextView text(String t, int sp, int color, boolean bold) {
        TextView v = new TextView(this);
        v.setText(t);
        v.setTextSize(sp);
        v.setTextColor(color);
        if (bold) v.setTypeface(Typeface.DEFAULT_BOLD);
        return v;
    }

    private TextView heading(String t) {
        TextView v = text(t.toUpperCase(), 12, MUTED, true);
        v.setLetterSpacing(0.06f);
        v.setPadding(0, dp(18), 0, dp(6));
        return v;
    }

    private TextView button(String label, boolean primary) {
        TextView t = text(label, 16, primary ? Color.WHITE : DARK, false);
        t.setGravity(Gravity.CENTER);
        t.setBackground(primary ? rounded(ACCENT, 12, ACCENT) : rounded(Color.WHITE, 12, LINE));
        t.setPadding(dp(16), dp(14), dp(16), dp(14));
        return t;
    }

    private GradientDrawable rounded(int fill, int radiusDp, int stroke) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(fill);
        g.setCornerRadius(dp(radiusDp));
        g.setStroke(dp(1), stroke);
        return g;
    }

    private LinearLayout.LayoutParams margins(int top, int bottom) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.topMargin = top;
        lp.bottomMargin = bottom;
        return lp;
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
                    .setMessage("Cliente de G3G3AI. La IA se ejecuta en tu PC (o en el proveedor que elijas en el chat directo); "
                            + "esta app se conecta a ellos.")
                    .setPositiveButton("OK", null).show();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
