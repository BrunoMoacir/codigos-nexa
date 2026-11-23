import Foundation
import Security

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
