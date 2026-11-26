package com.g3g3ai.client;

import android.Manifest;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.webkit.JavascriptInterface;

/**
 * Avisos del sistema para la página («la respuesta está lista», «G3G3AI necesita tu permiso»). Sólo puede
 * mostrar notificaciones, así que es seguro exponerlo también a la interfaz servida por el PC.
 */
final class Notifier {
    private static final String CHANNEL = "respuestas";
    private final Activity activity;
    private int nextId = 100;

    Notifier(Activity activity) {
        this.activity = activity;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "Respuestas de G3G3AI", NotificationManager.IMPORTANCE_DEFAULT);
            ch.setDescription("Avisa cuando una respuesta termina o la IA necesita tu permiso mientras usas otra app");
            activity.getSystemService(NotificationManager.class).createNotificationChannel(ch);
        }
    }

    /** Pide el permiso de notificaciones (Android 13+) la primera vez que la página lo necesita. */
    @JavascriptInterface
    public void requestPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            activity.runOnUiThread(() -> activity.requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 7));
        }
    }

    @JavascriptInterface
    public void notify(String title, String body) {
        if (Build.VERSION.SDK_INT >= 33
                && activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        Intent open = activity.getPackageManager().getLaunchIntentForPackage(activity.getPackageName());
        if (open == null) open = new Intent(activity, ServersActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
        PendingIntent pi = PendingIntent.getActivity(activity, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(activity, CHANNEL) : new Notification.Builder(activity);
        b.setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle(clip(title, 80))
                .setContentText(clip(body, 200))
                .setStyle(new Notification.BigTextStyle().bigText(clip(body, 600)))
                .setAutoCancel(true)
                .setContentIntent(pi);
        NotificationManager nm = (NotificationManager) activity.getSystemService(Context.NOTIFICATION_SERVICE);
        nm.notify(nextId++, b.build());
    }

    private static String clip(String s, int n) {
        if (s == null) return "";
        return s.length() <= n ? s : s.substring(0, n - 1) + "…";
    }
}
