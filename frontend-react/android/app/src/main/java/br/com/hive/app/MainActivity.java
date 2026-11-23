package br.com.hive.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // plugin local (widget nativo) — registrado antes do bridge subir
        registerPlugin(HiveNativoPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
