package br.com.hive.app.widget;

import android.content.Context;

import androidx.annotation.NonNull;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import javax.net.ssl.HttpsURLConnection;

/**
 * Busca a margem do dia em GET {api}/widget/margem com o token de escopo
 * restrito (header X-Widget-Token) e redesenha os widgets.
 *
 * - Só HTTPS: HttpsURLConnection com a validação de certificado do sistema;
 * - 401 = token revogado/vencido (logout, "sair de todos", conta apagada):
 *   a credencial é apagada e o widget pede para abrir o app;
 * - roda a cada 30 min quando há rede (o mínimo do WorkManager é 15).
 */
public class MargemWorker extends Worker {

    private static final String PERIODICO = "hive_margem_periodica";
    private static final String AGORA = "hive_margem_agora";

    public MargemWorker(@NonNull Context ctx, @NonNull WorkerParameters params) {
        super(ctx, params);
    }

    public static void agendar(Context ctx) {
        Constraints comRede = new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build();
        PeriodicWorkRequest periodico = new PeriodicWorkRequest.Builder(MargemWorker.class, 30, TimeUnit.MINUTES)
                .setConstraints(comRede).build();
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(PERIODICO, ExistingPeriodicWorkPolicy.UPDATE, periodico);
    }

    public static void atualizarAgora(Context ctx) {
        Constraints comRede = new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build();
        OneTimeWorkRequest agora = new OneTimeWorkRequest.Builder(MargemWorker.class).setConstraints(comRede).build();
        WorkManager.getInstance(ctx).enqueueUniqueWork(AGORA, ExistingWorkPolicy.REPLACE, agora);
    }

    public static void cancelar(Context ctx) {
        WorkManager.getInstance(ctx).cancelUniqueWork(PERIODICO);
        WorkManager.getInstance(ctx).cancelUniqueWork(AGORA);
    }

    @NonNull
    @Override
    public Result doWork() {
        Context ctx = getApplicationContext();
        String base = CofreDoWidget.ler(ctx, CofreDoWidget.API_BASE);
        String token = CofreDoWidget.ler(ctx, CofreDoWidget.TOKEN);
        if (base == null || token == null || !base.startsWith("https://")) {
            MargemWidgetProvider.redesenhar(ctx, null);
            return Result.success();
        }
        HttpsURLConnection conexao = null;
        try {
            URL url = new URL(base.replaceAll("/+$", "") + "/widget/margem");
            conexao = (HttpsURLConnection) url.openConnection();
            conexao.setConnectTimeout(10_000);
            conexao.setReadTimeout(15_000);
            conexao.setInstanceFollowRedirects(false); // o token não segue redirecionamento
            conexao.setRequestProperty("X-Widget-Token", token);
            conexao.setRequestProperty("Accept", "application/json");
            int status = conexao.getResponseCode();
            if (status == 401) {
                CofreDoWidget.limpar(ctx);
                MargemWidgetProvider.redesenhar(ctx, null);
                return Result.success();
            }
            if (status != 200) return Result.retry();
            StringBuilder corpo = new StringBuilder();
            try (BufferedReader leitor = new BufferedReader(new InputStreamReader(conexao.getInputStream(), StandardCharsets.UTF_8))) {
                String linha;
                while ((linha = leitor.readLine()) != null && corpo.length() < 16_384) corpo.append(linha);
            }
            JSONObject payload = new JSONObject(corpo.toString());
            CofreDoWidget.guardar(ctx, CofreDoWidget.ULTIMO_PAYLOAD, payload.toString());
            MargemWidgetProvider.redesenhar(ctx, payload);
            return Result.success();
        } catch (Exception e) {
            return Result.retry();
        } finally {
            if (conexao != null) conexao.disconnect();
        }
    }
}
