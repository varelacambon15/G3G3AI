package com.g3g3ai.client;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/** Muestra la interfaz web de G3G3AI con soporte de cámara, archivos y descargas. */
public class WebActivity extends Activity {
    private static final int REQ_FILES = 1;

    private WebView web;
    private View errorView;
    private TextView errorText;
    private String baseUrl;
    private ValueCallback<Uri[]> fileCallback;
    private Uri cameraUri;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        baseUrl = getIntent().getStringExtra("url");
        String token = getIntent().getStringExtra("token");

        FrameLayout root = new FrameLayout(this);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        errorView = buildErrorView();
        errorView.setVisibility(View.GONE);
        root.addView(errorView, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);

        WebSettings ws = web.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setDatabaseEnabled(true);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setAllowFileAccess(false);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        ws.setUserAgentString(ws.getUserAgentString() + " G3G3AI-Android/0.5");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                Uri base = Uri.parse(baseUrl);
                boolean sameServer = u.getHost() != null && u.getHost().equals(base.getHost()) && u.getPort() == base.getPort();
                if (sameServer || "blob".equals(u.getScheme()) || "data".equals(u.getScheme())) return false;
                // Enlaces externos (fuentes de la búsqueda web, etc.) en el navegador
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (ActivityNotFoundException ignored) {
                    // sin navegador: no hacemos nada
                }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) {
                    errorText.setText("No se puede conectar con " + baseUrl + "\n\n" + err.getDescription()
                            + "\n\nComprueba que el equipo está encendido, que G3G3AI está en marcha y que el móvil "
                            + "está en la misma red Wi-Fi (o en Tailscale).");
                    errorView.setVisibility(View.VISIBLE);
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                CookieManager.getInstance().flush();
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                openChooser(params);
                return true;
            }
        });

        web.setDownloadListener((url, userAgent, contentDisposition, mimeType, length) -> download(url, userAgent, contentDisposition, mimeType));

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            String first = baseUrl + "/";
            if (token != null && !token.isEmpty()) first += "?token=" + Uri.encode(token);
            web.loadUrl(first);
        }
    }

    // --- Selector de archivos / cámara ------------------------------------------------------
    private void openChooser(WebChromeClient.FileChooserParams params) {
        Intent pick = params.createIntent();
        pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE);
        String[] types = params.getAcceptTypes();
        boolean images = types == null || types.length == 0 || (types.length == 1 && types[0].isEmpty());
        for (String t : types == null ? new String[0] : types) if (t.startsWith("image")) images = true;

        List<Intent> extra = new ArrayList<>();
        cameraUri = null;
        if (images) {
            try {
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.Images.Media.DISPLAY_NAME, "G3G3AI_" + System.currentTimeMillis() + ".jpg");
                cv.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                if (Build.VERSION.SDK_INT >= 29) cv.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/G3G3AI");
                cameraUri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cv);
                Intent cam = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                cam.putExtra(MediaStore.EXTRA_OUTPUT, cameraUri);
                cam.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                extra.add(cam);
            } catch (Exception e) {
                cameraUri = null;  // sin cámara o sin almacenamiento: sólo selector de archivos
            }
        }
        Intent target;
        if (params.isCaptureEnabled() && !extra.isEmpty()) {
            target = extra.get(0);  // <input capture>: abrir la cámara directamente
        } else {
            target = Intent.createChooser(pick, "Elegir archivo");
            if (!extra.isEmpty()) target.putExtra(Intent.EXTRA_INITIAL_INTENTS, extra.toArray(new Intent[0]));
        }
        try {
            startActivityForResult(target, REQ_FILES);
        } catch (ActivityNotFoundException e) {
            fileCallback.onReceiveValue(null);
            fileCallback = null;
            Toast.makeText(this, "No hay ninguna app para elegir archivos", Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_FILES || fileCallback == null) return;
        Uri[] result = null;
        if (resultCode == RESULT_OK) {
            if (data != null && data.getClipData() != null) {
                int n = data.getClipData().getItemCount();
                result = new Uri[n];
                for (int i = 0; i < n; i++) result[i] = data.getClipData().getItemAt(i).getUri();
            } else if (data != null && data.getData() != null) {
                result = new Uri[]{data.getData()};
            } else if (cameraUri != null && hasContent(cameraUri)) {
                result = new Uri[]{cameraUri};
            }
        }
        if (result == null && cameraUri != null && !hasContent(cameraUri)) {
            getContentResolver().delete(cameraUri, null, null);  // foto cancelada
        }
        fileCallback.onReceiveValue(result);
        fileCallback = null;
    }

    private boolean hasContent(Uri uri) {
        try (InputStream in = getContentResolver().openInputStream(uri)) {
            return in != null && in.read() != -1;
        } catch (Exception e) {
            return false;
        }
    }

    // --- Descargas (con la cookie de sesión) ------------------------------------------------
    private void download(String url, String userAgent, String contentDisposition, String mimeType) {
        if (url.startsWith("blob:") || url.startsWith("data:")) {
            Toast.makeText(this, "Este contenido no se puede descargar desde la app", Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            String name = URLUtil.guessFileName(url, contentDisposition, mimeType);
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
            r.addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url));
            r.addRequestHeader("User-Agent", userAgent);
            r.setMimeType(mimeType);
            r.setTitle(name);
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(r);
            Toast.makeText(this, "Descargando " + name, Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            Toast.makeText(this, "No se pudo descargar: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    // --- Pantalla de error -----------------------------------------------------------------
    private View buildErrorView() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(Color.parseColor("#FAF9F5"));
        int p = Math.round(24 * getResources().getDisplayMetrics().density);
        box.setPadding(p, p, p, p);
        errorText = new TextView(this);
        errorText.setTextSize(15);
        errorText.setTextColor(Color.parseColor("#1F1E1D"));
        errorText.setGravity(Gravity.CENTER);
        box.addView(errorText);
        TextView retry = new TextView(this);
        retry.setText("Reintentar");
        retry.setTextColor(Color.WHITE);
        retry.setBackgroundColor(Color.parseColor("#C2603F"));
        retry.setPadding(p, p / 2, p, p / 2);
        retry.setOnClickListener(v -> { errorView.setVisibility(View.GONE); web.reload(); });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = p;
        box.addView(retry, lp);
        TextView change = new TextView(this);
        change.setText("Cambiar de equipo");
        change.setTextColor(Color.parseColor("#C2603F"));
        change.setPadding(p, p / 2, p, p / 2);
        change.setOnClickListener(v -> backToServers());
        box.addView(change);
        return box;
    }

    private void backToServers() {
        Intent i = new Intent(this, ServersActivity.class);
        i.putExtra("noauto", true);
        i.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(i);
        finish();
    }

    @Override
    public void onBackPressed() {
        if (errorView.getVisibility() == View.VISIBLE) { backToServers(); return; }
        if (web.canGoBack()) web.goBack();
        else backToServers();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onDestroy() {
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
