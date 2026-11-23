import Foundation
import Capacitor
import Security
#if canImport(WidgetKit)
import WidgetKit
#endif

/// Ponte do app web para o widget nativo (src/native/hiveNativo.ts).
///
/// `configurarWidget` recebe o token de ESCOPO RESTRITO do widget (nunca o JWT
/// nem o refresh da sessão) e a base HTTPS da API, e guarda no Keychain num
/// grupo de acesso compartilhado com a extensão do widget
/// (kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly: não vai para backup nem
/// para outro aparelho). `limparWidget` apaga tudo no logout.
@objc(HiveNativoPlugin)
public class HiveNativoPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "HiveNativoPlugin"
    public let jsName = "HiveNativo"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "configurarWidget", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "limparWidget", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "widgetDisponivel", returnType: CAPPluginReturnPromise),
    ]

    @objc func configurarWidget(_ call: CAPPluginCall) {
        guard let apiBase = call.getString("apiBase"), apiBase.hasPrefix("https://") else {
            call.reject("A API do widget precisa ser HTTPS.")
            return
        }
        guard let token = call.getString("token"), token.hasPrefix("hwt_"), token.count <= 200 else {
            call.reject("Token de widget inválido.")
            return
        }
        guard CofreCompartilhado.guardar(apiBase, chave: CofreCompartilhado.apiBase),
              CofreCompartilhado.guardar(token, chave: CofreCompartilhado.token) else {
            call.reject("Não foi possível guardar a credencial do widget.")
            return
        }
        recarregarWidgets()
        call.resolve()
    }

    @objc func limparWidget(_ call: CAPPluginCall) {
        CofreCompartilhado.apagarTudo()
        recarregarWidgets()
        call.resolve()
    }

    @objc func widgetDisponivel(_ call: CAPPluginCall) {
        call.resolve(["disponivel": CofreCompartilhado.grupo() != nil])
    }

    private func recarregarWidgets() {
        #if canImport(WidgetKit)
        if #available(iOS 14.0, *) {
            WidgetCenter.shared.reloadAllTimelines()
        }
        #endif
    }
}

/// Keychain compartilhado entre o app e a extensão do widget.
/// O grupo vem do Info.plist (HiveKeychainGroup = $(AppIdentifierPrefix)br.com.hive.app.compartilhado),
/// que o Xcode expande com o Team ID na compilação.
/// O MESMO arquivo é usado pela extensão (ios/HiveWidget/CofreCompartilhado.swift).
enum CofreCompartilhado {
    static let servico = "br.com.hive.app.widget"
    static let apiBase = "api_base"
    static let token = "token"

    static func grupo() -> String? {
        guard let valor = Bundle.main.object(forInfoDictionaryKey: "HiveKeychainGroup") as? String,
              !valor.isEmpty, !valor.contains("$(") else { return nil }
        return valor
    }

    private static func consultaBase(_ chave: String) -> [String: Any] {
        var q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: servico,
            kSecAttrAccount as String: chave,
        ]
        if let g = grupo() { q[kSecAttrAccessGroup as String] = g }
        return q
    }

    @discardableResult
    static func guardar(_ valor: String, chave: String) -> Bool {
        SecItemDelete(consultaBase(chave) as CFDictionary)
        var item = consultaBase(chave)
        item[kSecValueData as String] = Data(valor.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(item as CFDictionary, nil) == errSecSuccess
    }

    static func ler(_ chave: String) -> String? {
        var q = consultaBase(chave)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var resultado: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &resultado) == errSecSuccess,
              let dados = resultado as? Data else { return nil }
        return String(data: dados, encoding: .utf8)
    }

    static func apagarTudo() {
        for chave in [apiBase, token] { SecItemDelete(consultaBase(chave) as CFDictionary) }
    }
}
