package br.com.hive.app.widget;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.widget.RemoteViews;

import org.json.JSONObject;

import br.com.hive.app.MainActivity;
import br.com.hive.app.R;

/** Widget "Margem do dia" na tela inicial (mesmo conteúdo da tela /widget do app). */
public class MargemWidgetProvider extends AppWidgetProvider {

    @Override
    public void onUpdate(Context ctx, AppWidgetManager gerente, int[] ids) {
        String guardado = CofreDoWidget.ler(ctx, CofreDoWidget.ULTIMO_PAYLOAD);
        JSONObject payload = null;
        try {
            if (guardado != null) payload = new JSONObject(guardado);
        } catch (Exception ignorado) {
            payload = null;
        }
        redesenhar(ctx, payload);
        MargemWorker.agendar(ctx);
        MargemWorker.atualizarAgora(ctx);
    }

    @Override
    public void onDisabled(Context ctx) {
        MargemWorker.cancelar(ctx);
    }

    /** payload null = sem credencial: convida a abrir o app. */
    public static void redesenhar(Context ctx, JSONObject payload) {
        AppWidgetManager gerente = AppWidgetManager.getInstance(ctx);
        int[] ids = gerente.getAppWidgetIds(new ComponentName(ctx, MargemWidgetProvider.class));
        if (ids.length == 0) return;

        RemoteViews vistas = new RemoteViews(ctx.getPackageName(), R.layout.widget_margem);
        if (payload == null) {
            vistas.setTextViewText(R.id.widget_valor, ctx.getString(R.string.widget_sem_sessao));
            vistas.setTextViewText(R.id.widget_detalhe, ctx.getString(R.string.widget_abrir_app));
            vistas.setTextColor(R.id.widget_valor, Color.parseColor("#F3EFEA"));
        } else {
            vistas.setTextViewText(R.id.widget_valor, payload.optString("headline", ""));
            vistas.setTextViewText(R.id.widget_detalhe, payload.optString("subline", ""));
            vistas.setTextColor(R.id.widget_valor, corSegura(payload.optString("color", "#D4A820")));
        }

        Intent abrir = new Intent(ctx, MainActivity.class);
        abrir.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent toque = PendingIntent.getActivity(ctx, 0, abrir,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        vistas.setOnClickPendingIntent(R.id.widget_raiz, toque);

        for (int id : ids) gerente.updateAppWidget(id, vistas);
    }

    private static int corSegura(String hex) {
        try {
            return hex.matches("^#[0-9A-Fa-f]{6}$") ? Color.parseColor(hex) : Color.parseColor("#D4A820");
        } catch (Exception e) {
            return Color.parseColor("#D4A820");
        }
    }
}
