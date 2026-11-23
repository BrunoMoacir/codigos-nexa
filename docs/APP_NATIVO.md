# App nativo (Android e iOS)

O app nativo é o **mesmo `frontend-react`**, embrulhado pelo Capacitor 8. O
design é o da web, sem nenhuma tela à parte. O que o nativo acrescenta:

| Recurso | Android | iOS |
|:---|:---|:---|
| App instalado pela loja, com o build web embutido | ✅ | ✅ |
| **Widget de tela inicial** com a margem do dia | ✅ `MargemWidgetProvider` + WorkManager (30 min) | ✅ WidgetKit (iOS 17+, 30 min) — alvo criado à mão no Xcode |
| **Push nativo** (FCM HTTP v1) com os alertas WARNING/CRITICAL | ✅ | ✅ com o Firebase iOS SDK |
| Links externos no navegador do sistema | ✅ | ✅ |
| Exportações (LGPD, dossiê) via folha de compartilhar | ✅ | ✅ |
| Botão voltar do Android | ✅ | — |

O código fica em:

- `frontend-react/capacitor.config.ts`, a configuração;
- `frontend-react/src/native/`, a ponte web ↔ nativo;
- `frontend-react/android/` e `frontend-react/ios/`, os projetos nativos.

O backend que o app usa fica em `backend/app/widget/` (token do widget) e
`backend/app/core/notifications/fcm_sender.py` (push).

---

## Modelo de segurança

**O JWT e o refresh da sessão nunca saem do WebView.** O widget roda fora do
app (processo do launcher no Android e extensão no iOS), então recebe uma
credencial própria:

| Credencial do widget | Detalhe |
|:---|:---|
| Formato | `hwt_` + 32 bytes aleatórios |
| No servidor | Só o SHA-256 (`widget_tokens`) |
| Escopo | Lê **apenas** `GET /api/v1/widget/margem` (header `X-Widget-Token`). Não abre nenhuma outra rota, e um JWT não abre a rota do widget |
| Validade | 90 dias. Um token por aparelho: emitir de novo revoga o anterior |
| Revogação | `DELETE /widget/token/{user_id}`, logout, `logout-all`, reset de senha e exclusão de conta (LGPD). Um token emitido antes do último corte de sessão é recusado mesmo sem revogação explícita |
| No aparelho | Android: Keystore (AES-GCM) + `SharedPreferences`, fora do backup. iOS: Keychain `AfterFirstUnlockThisDeviceOnly`, num grupo compartilhado só com a extensão |

Outras decisões:

- **Código remoto:** sem `server.url`. O app roda sempre o build embutido;
  carregar JS de um servidor permitiria trocar o app sem passar pela loja.
- **Navegação:** `allowNavigation` vazio, então o WebView não sai do app. Os
  links externos (Stripe, WhatsApp, sites oficiais) abrem no navegador do
  sistema.
- **Rede:** sem texto puro (`cleartext=false` e `network_security_config`), e o
  build mobile **recusa** um `VITE_API_URL` que não seja https.
- **Backup:** desligado no Android (`allowBackup=false` + regras de extração),
  para que o extrato em cache e as credenciais não saiam do aparelho.
- **Build:** o `gradle-wrapper.jar` confere com o checksum oficial do Gradle
  8.14.3, e a distribuição baixada pelo wrapper está fixada por SHA-256
  (`distributionSha256Sum`). Um download adulterado é recusado. Ao atualizar o
  Gradle, atualize os dois.
- **Notificações:** a visibilidade é PRIVADA na tela de bloqueio (o conteúdo só
  aparece desbloqueado). O toque numa notificação só navega para rota interna;
  URL externa ou `//host` cai no `/feed`.
- **Push:** o token FCM é registrado por conta. Se o aparelho troca de conta, o
  token é transferido, e um token que o FCM declara inválido é revogado sozinho.
  O reset de senha e o `logout-all` revogam todos os aparelhos da conta. No
  login seguinte, o app confirma de novo o aparelho que já tinha push ligado.
- **CORS:** o backend precisa liberar `https://localhost` (Android) e
  `capacitor://localhost` (iOS). Isso não abre credencial nenhuma: a API não usa
  cookie e o CORS roda com `allow_credentials=False`. A autenticação é sempre o
  Bearer que só o app tem.
- **Compra:** fica fora do app. Vender assinatura digital dentro do app sem a
  compra da loja viola as regras da App Store e do Google Play. No app, `/planos`
  mostra o plano e os limites, e a assinatura é feita pelo site
  (`vendaNoApp()` em `src/native/plataforma.ts`).

### Riscos residuais (decisões conscientes)

- O **refresh token** fica no `localStorage` do WebView, como na web. Ele fica
  no sandbox do app, mas não no Keychain/Keystore. Movê-lo exige um plugin de
  armazenamento seguro e mudar `api/session.ts`.
- **Certificate pinning** não foi feito. Fixar o certificado da API protege
  contra CA comprometida, mas uma rotação de certificado sem atualização do app
  derruba todo mundo. Reavaliar quando houver domínio e CDN definitivos.

---

## Pré-requisitos

| Para | Precisa |
|:---|:---|
| Android | JDK 21, Android SDK (API 36) com as **licenças aceitas por você** (`sdkmanager --licenses`), Android Studio opcional |
| iOS | macOS com a versão do Xcode exigida pelo Capacitor 8 (capacitorjs.com/docs/getting-started/environment-setup), conta Apple Developer (para assinar, para o widget e para push) |
| Push | Projeto no Firebase com app Android e app iOS (chave APNs enviada ao Firebase) |

---

## Passo a passo

### 1. Identidade do app (antes da primeira publicação)

O `appId` é **`br.com.hive.app`** (em `capacitor.config.ts`, `android/app/build.gradle`
e no bundle id do Xcode). Ele não muda depois da publicação. Se for usar
outro, troque nos três lugares **e** no grupo do Keychain
(`$(AppIdentifierPrefix)<appId>.compartilhado`), que aparece em:

- `ios/App/App/App.entitlements`;
- `ios/App/App/Info.plist`;
- `ios/HiveWidget/HiveWidget.entitlements`.

### 2. Backend

```bash
# CORS: origens do WebView (além do site)
ALLOWED_ORIGINS=https://app.seu-dominio.com.br,https://localhost,capacitor://localhost

# Push nativo: JSON da conta de serviço do Firebase, em base64 (SEGREDO)
#   Firebase → Configurações do projeto → Contas de serviço → Gerar nova chave privada
#   base64 -i conta-de-servico.json | tr -d '\n'
FCM_SERVICE_ACCOUNT_B64=...
```

Depois, rode a migração, que cria `widget_tokens` e `push_devices`:

```bash
cd backend && alembic upgrade head
```

Sem `FCM_SERVICE_ACCOUNT_B64`, o push nativo fica desligado e o resto
funciona.

### 3. Build web para o app

```bash
cd frontend-react
cp .env.mobile.example .env.mobile      # fora do git
# edite VITE_API_URL=https://api.seu-dominio.com.br/api/v1
npm run build:mobile                    # tsc + vite build --mode mobile + cap sync
```

### 4. Android

1. Baixe o `google-services.json` do Firebase (app Android `br.com.hive.app`)
   para `frontend-react/android/app/`. Ele está no `.gitignore`.
2. Abra o projeto com `npm run cap:android`, ou compile direto com
   `cd android && ./gradlew assembleDebug`.
3. Para assinar o release, use `keystore.properties` + `.jks` **fora do git**
   (já ignorados) e o Play App Signing.
4. Teste o widget: segure a tela inicial → Widgets → HIVE.

### 5. iOS

1. Rode `npm run cap:ios` (abre o Xcode).
2. **Firebase** (para push):
   - adicione o pacote `https://github.com/firebase/firebase-ios-sdk` via File →
     Add Package Dependencies, com os produtos `FirebaseCore` e
     `FirebaseMessaging` no alvo **App**;
   - arraste o `GoogleService-Info.plist` para `App/App`; ele está no `.gitignore`.

   O `AppDelegate` já usa `#if canImport(FirebaseMessaging)`: sem o pacote, o
   app compila, o push fica desligado, e o app não manda ao backend o token APNs
   cru (que o FCM não aceita).
3. **Capabilities do alvo App:** Push Notifications, Background Modes → Remote
   notifications, e Keychain Sharing (o grupo já está no `App.entitlements`).
4. **Alvo do widget**, criado à mão (o Capacitor não gera extensões):
   1. File → New → Target → **Widget Extension**, nome `HiveWidget`, sem Live
      Activity e sem Configuration Intent. Deployment target **iOS 17**.
   2. Apague os arquivos gerados pelo template e adicione ao alvo os que já
      estão no repo: `ios/HiveWidget/HiveWidget.swift` e
      `ios/HiveWidget/CofreCompartilhado.swift`.
   3. Em Signing & Capabilities do alvo, ative **Keychain Sharing** e aponte o
      entitlements para `ios/HiveWidget/HiveWidget.entitlements`.
   4. No `Info.plist` da extensão, adicione
      `HiveKeychainGroup = $(AppIdentifierPrefix)br.com.hive.app.compartilhado`
      (o mesmo valor do app).
   5. Use o mesmo time de assinatura do app. O bundle id deve ser
      `br.com.hive.app.HiveWidget`.
5. Para a App Store, troque `aps-environment` para `production` no
   `App.entitlements`, ou deixe o Xcode gerenciar.

### 6. Verificação de ponta a ponta

| Teste | Esperado |
|:---|:---|
| Entrar no app | O widget passa de "Abra o app para conectar" para a margem do dia (ou "Conecte seu banco") |
| Perfil → ativar notificações | `POST /push/devices/{id}` 200; um alerta CRITICAL de teste chega com o conteúdo oculto na tela bloqueada |
| Tocar na notificação | Abre a tela do alerta dentro do app |
| Link do WhatsApp / Stripe / gov.br | Abre no navegador do sistema, não no WebView |
| Sair (ou "sair de todos os aparelhos", ou redefinir a senha) | Widget volta para "Abra o app"; `GET /widget/margem` com o token antigo → 401; o celular para de receber os alertas até o próximo login |
| `/planos` no app | Mostra plano e limites, sem compra; o aviso aponta para o site |

---

## Testes automatizados

- **Backend** (`backend/tests/mobile/test_app_nativo.py`):
  - token do widget: emissão, rotação, escopo, IDOR, hash-only, revogação no
    logout-all e no reset de senha, corte de sessão;
  - aparelhos de push: transferência entre contas;
  - SSRF do Web Push, incluindo URL ambígua entre parsers e redirecionamento;
  - FCM com transporte simulado.
- **Frontend** (`frontend-react/src/tests/unit/native/nativo.test.ts`):
  - registro do token FCM; token APNs cru recusado; novo login confirma o
    aparelho sem ligar push sozinho;
  - toque só em rota interna;
  - o widget nunca recebe o JWT;
  - logout revoga;
  - links externos fora do WebView;
  - compra desligada no app.
- **Não automatizado** (exige SDK ou Xcode): compilação Android/iOS e o
  comportamento visual do widget. Valide pelo roteiro acima antes de cada
  envio às lojas.
