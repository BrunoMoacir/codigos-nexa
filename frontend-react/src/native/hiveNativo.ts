import { registerPlugin } from '@capacitor/core';

/** Plugin local do app (android/…/HiveNativoPlugin.java e ios/App/App/HiveNativoPlugin.swift). */
export interface HiveNativoPlugin {
  /** Guarda (cifrado no Keystore/Keychain) o token de ESCOPO RESTRITO do widget e a base HTTPS da API. */
  configurarWidget(opcoes: { apiBase: string; token: string }): Promise<void>;
  /** Apaga a credencial do widget (logout). */
  limparWidget(): Promise<void>;
  widgetDisponivel(): Promise<{ disponivel: boolean }>;
}

export const HiveNativo = registerPlugin<HiveNativoPlugin>('HiveNativo');
