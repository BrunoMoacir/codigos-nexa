import WidgetKit
import SwiftUI

/// Widget "Margem do dia" (iOS 17+: usa containerBackground). Busca GET {api}/widget/margem com o token
/// de escopo restrito guardado pelo app no Keychain compartilhado.
///  - só HTTPS e sem seguir redirecionamento com o token;
///  - 401 = token revogado (logout, "sair de todos", conta apagada): apaga a
///    credencial e passa a pedir para abrir o app;
///  - próxima atualização em 30 min (o iOS decide o momento exato).

struct Margem: Decodable {
    let headline: String
    let subline: String
    let color: String
    let status: String
}

struct EntradaMargem: TimelineEntry {
    let date: Date
    let margem: Margem?
}

final class SemRedirecionamento: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

struct ProvedorMargem: TimelineProvider {
    func placeholder(in context: Context) -> EntradaMargem {
        EntradaMargem(date: Date(), margem: Margem(headline: "R$ 120/dia", subline: "Pode gastar com tranquilidade",
                                                   color: "#D4A820", status: "OK"))
    }

    func getSnapshot(in context: Context, completion: @escaping (EntradaMargem) -> Void) {
        buscar { completion(EntradaMargem(date: Date(), margem: $0)) }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<EntradaMargem>) -> Void) {
        buscar { margem in
            let proxima = Calendar.current.date(byAdding: .minute, value: 30, to: Date()) ?? Date()
            completion(Timeline(entries: [EntradaMargem(date: Date(), margem: margem)], policy: .after(proxima)))
        }
    }

    private func buscar(_ fim: @escaping (Margem?) -> Void) {
        guard let base = CofreCompartilhado.ler(CofreCompartilhado.apiBase), base.hasPrefix("https://"),
              let token = CofreCompartilhado.ler(CofreCompartilhado.token),
              let url = URL(string: base.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/widget/margem") else {
            fim(nil)
            return
        }
        var pedido = URLRequest(url: url, timeoutInterval: 15)
        pedido.setValue(token, forHTTPHeaderField: "X-Widget-Token")
        pedido.setValue("application/json", forHTTPHeaderField: "Accept")
        let sessao = URLSession(configuration: .ephemeral, delegate: SemRedirecionamento(), delegateQueue: nil)
        sessao.dataTask(with: pedido) { dados, resposta, _ in
            let status = (resposta as? HTTPURLResponse)?.statusCode ?? 0
            if status == 401 {
                CofreCompartilhado.apagarTudo()
                fim(nil)
                return
            }
            guard status == 200, let dados = dados,
                  let margem = try? JSONDecoder().decode(Margem.self, from: dados) else {
                fim(nil)
                return
            }
            fim(margem)
        }.resume()
    }
}

extension Color {
    /// "#RRGGBB" do payload; qualquer outra coisa vira o ouro HIVE.
    init(hexHive: String) {
        let limpo = hexHive.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard limpo.count == 6, let v = UInt32(limpo, radix: 16) else {
            self = Color(red: 0.83, green: 0.66, blue: 0.13)
            return
        }
        self = Color(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255,
                     blue: Double(v & 0xFF) / 255)
    }
}

struct VistaMargem: View {
    let entrada: EntradaMargem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("MARGEM DO DIA")
                .font(.system(size: 11, weight: .bold))
                .tracking(1.3)
                .foregroundColor(Color(hexHive: "#D4A820"))
            if let m = entrada.margem {
                Text(m.headline)
                    .font(.system(size: 18, weight: .heavy))
                    .foregroundColor(Color(hexHive: m.color))
                    .lineLimit(2)
                Text(m.subline)
                    .font(.system(size: 12))
                    .foregroundColor(Color(hexHive: "#B5B1AD"))
                    .lineLimit(2)
            } else {
                Text("Entre no app HIVE")
                    .font(.system(size: 18, weight: .heavy))
                    .foregroundColor(Color(hexHive: "#F3EFEA"))
                Text("Toque para abrir e ativar o widget")
                    .font(.system(size: 12))
                    .foregroundColor(Color(hexHive: "#B5B1AD"))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .containerBackground(Color(hexHive: "#0C0A08"), for: .widget)
    }
}

@main
struct HiveWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "HiveMargem", provider: ProvedorMargem()) { entrada in
            VistaMargem(entrada: entrada)
        }
        .configurationDisplayName("Margem do dia")
        .description("Quanto você pode gastar hoje sem comprometer as contas.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
