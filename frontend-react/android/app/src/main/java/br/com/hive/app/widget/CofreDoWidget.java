package br.com.hive.app.widget;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Guarda a credencial do widget (token de escopo restrito + endereço da API) e
 * o último payload mostrado, cifrados com AES-GCM. A chave fica no Android
 * Keystore e nunca sai do hardware/TEE; o SharedPreferences só vê texto cifrado.
 *
 * (androidx.security-crypto foi descontinuado; o Keystore direto é o caminho
 * recomendado.) O backup do app está desligado no manifesto, então nem o
 * texto cifrado vai para a nuvem — e a chave não poderia ir junto de qualquer forma.
 */
public final class CofreDoWidget {

    private static final String ARQUIVO = "hive_widget";
    private static final String ALIAS = "hive_widget_chave";
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final int TAG_BITS = 128;

    public static final String API_BASE = "api_base";
    public static final String TOKEN = "token";
    public static final String ULTIMO_PAYLOAD = "ultimo_payload";

    private CofreDoWidget() {}

    private static SecretKey chave() throws Exception {
        KeyStore ks = KeyStore.getInstance(KEYSTORE);
        ks.load(null);
        if (ks.containsAlias(ALIAS)) {
            return ((KeyStore.SecretKeyEntry) ks.getEntry(ALIAS, null)).getSecretKey();
        }
        KeyGenerator gerador = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        gerador.init(new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return gerador.generateKey();
    }

    private static SharedPreferences prefs(Context ctx) {
        return ctx.getApplicationContext().getSharedPreferences(ARQUIVO, Context.MODE_PRIVATE);
    }

    public static synchronized void guardar(Context ctx, String nome, String valor) {
        try {
            Cipher cifra = Cipher.getInstance("AES/GCM/NoPadding");
            cifra.init(Cipher.ENCRYPT_MODE, chave());
            byte[] iv = cifra.getIV();
            byte[] dados = cifra.doFinal(valor.getBytes(StandardCharsets.UTF_8));
            String gravado = Base64.encodeToString(iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(dados, Base64.NO_WRAP);
            prefs(ctx).edit().putString(nome, gravado).apply();
        } catch (Exception e) {
            // sem cofre não guardamos nada em claro: o widget só pede para abrir o app
            prefs(ctx).edit().remove(nome).apply();
        }
    }

    public static synchronized String ler(Context ctx, String nome) {
        String gravado = prefs(ctx).getString(nome, null);
        if (gravado == null) return null;
        try {
            String[] partes = gravado.split(":", 2);
            Cipher cifra = Cipher.getInstance("AES/GCM/NoPadding");
            cifra.init(Cipher.DECRYPT_MODE, chave(),
                    new GCMParameterSpec(TAG_BITS, Base64.decode(partes[0], Base64.NO_WRAP)));
            return new String(cifra.doFinal(Base64.decode(partes[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
        } catch (Exception e) {
            prefs(ctx).edit().remove(nome).apply();
            return null;
        }
    }

    public static synchronized void limpar(Context ctx) {
        prefs(ctx).edit().clear().apply();
    }
}
