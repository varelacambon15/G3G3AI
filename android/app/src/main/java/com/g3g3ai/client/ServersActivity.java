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

import java.util.List;

/** Pantalla inicial: lista de equipos con G3G3AI a los que conectarse. */
public class ServersActivity extends Activity {
    private LinearLayout listBox;

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
        intro.setText("Conéctate a G3G3AI en tu Konkr o tu PC. Ambos deben estar en la misma Wi-Fi que el móvil "
                + "(o en Tailscale). La dirección y la contraseña aparecen en Ajustes → Acceso remoto.");
        intro.setTextColor(Color.parseColor("#75716A"));
        intro.setTextSize(14);
        root.addView(intro);

        listBox = new LinearLayout(this);
        listBox.setOrientation(LinearLayout.VERTICAL);
        listBox.setPadding(0, dp(14), 0, dp(14));
        root.addView(listBox);

        TextView add = button("＋ Añadir equipo");
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
    }

    private void render() {
        listBox.removeAllViews();
        List<Servers.Server> servers = Servers.load(this);
        if (servers.isEmpty()) {
            TextView empty = new TextView(this);
            empty.setText("Aún no hay equipos. Añade el primero.");
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
            card.addView(name);
            card.addView(url);
            card.setOnClickListener(v -> open(idx));
            card.setOnLongClickListener(v -> { edit(idx); return true; });
            listBox.addView(card);
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

    private void edit(int idx) {
        List<Servers.Server> servers = Servers.load(this);
        Servers.Server cur = idx >= 0 ? servers.get(idx) : null;
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(20), dp(8), dp(20), 0);
        EditText name = field("Nombre (p.ej. Konkr)", cur != null ? cur.name : "", InputType.TYPE_CLASS_TEXT);
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

    private TextView button(String text) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextSize(16);
        t.setGravity(Gravity.CENTER);
        t.setTextColor(Color.WHITE);
        t.setBackgroundColor(Color.parseColor("#C2603F"));
        t.setPadding(dp(16), dp(14), dp(16), dp(14));
        return t;
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
                    .setMessage("Cliente de G3G3AI (versión de prueba). La IA se ejecuta en tu Konkr o tu PC; "
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
