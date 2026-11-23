package br.com.hive.app;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import br.com.hive.app.widget.CofreDoWidget;
import br.com.hive.app.widget.MargemWidgetProvider;
import br.com.hive.app.widget.MargemWorker;

/**
 * Ponte do app web para o widget nativo (src/native/hiveNativo.ts).
 *
 * configurarWidget: recebe o token de ESCOPO RESTRITO do widget (nunca o JWT
 * nem o refresh da sessão) e a base HTTPS da API; guarda cifrado no Keystore.
 * limparWidget: apaga tudo (logout) e o widget volta a pedir para abrir o app.
 */
@CapacitorPlugin(name = "HiveNativo")
public class HiveNativoPlugin extends Plugin {

    @PluginMethod
    public void configurarWidget(PluginCall call) {
        String apiBase = call.getString("apiBase", "");
        String token = call.getString("token", "");
        if (apiBase == null || !apiBase.startsWith("https://")) {
            call.reject("A API do widget precisa ser HTTPS.");
            return;
        }
        if (token == null || !token.startsWith("hwt_") || token.length() > 200) {
            call.reject("Token de widget inválido.");
            return;
        }
        CofreDoWidget.guardar(getContext(), CofreDoWidget.API_BASE, apiBase);
        CofreDoWidget.guardar(getContext(), CofreDoWidget.TOKEN, token);
        MargemWorker.agendar(getContext());
        MargemWorker.atualizarAgora(getContext());
        call.resolve();
    }

    @PluginMethod
    public void limparWidget(PluginCall call) {
        CofreDoWidget.limpar(getContext());
        MargemWorker.cancelar(getContext());
        MargemWidgetProvider.redesenhar(getContext(), null);
        call.resolve();
    }

    @PluginMethod
    public void widgetDisponivel(PluginCall call) {
        JSObject r = new JSObject();
        r.put("disponivel", true);
        call.resolve(r);
    }
}
