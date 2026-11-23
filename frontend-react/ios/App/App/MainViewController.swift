import UIKit
import Capacitor

/// Bridge do Capacitor com o plugin local do widget registrado.
/// (Main.storyboard aponta para esta classe.)
class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(HiveNativoPlugin())
    }
}
