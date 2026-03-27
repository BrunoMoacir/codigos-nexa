# 🚀 Usuário Mock Criado no Railway

## ✅ Credenciais de Acesso

- **Email:** `teste@nexa.com`
- **Senha:** `teste123`
- **Nome:** Bruno Teste

## 📊 Como Popular com Transações

O usuário foi criado, mas para ter dados financeiros completos (transações, metas, etc), siga estes passos:

### Opção 1: Sandbox do Pluggy (RECOMENDADO)

1. Faça login em: https://codigos-nexa-production.up.railway.app
2. Vá para **Conexões**
3. Selecione o multiplicador: **Alto (500x)** ou **Stress (1000x)**
4. Clique em **Criar item Sandbox**
5. Aguarde a criação
6. Clique em **Sincronizar transações**

✨ Isso vai criar centenas/milhares de transações automaticamente!

### Opção 2: Conectar Banco Real

1. Faça login
2. Vá para **Conexões**
3. Clique em **Gerar Token Pluggy**
4. Use o widget para conectar seu banco real

## 🎨 Testando o Modo Escuro

- Clique no botão **☾ Modo escuro** no menu lateral
- Todas as páginas agora têm transições suaves
- O tema persiste entre navegação

## 📁 Scripts Disponíveis

### Script via API (Usado)
```bash
python3 backend/scripts/seed_railway_api.py
```

### Script Direto ao Banco (Requer configuração local)
```bash
# Configurar DATABASE_URL no .env
python3 backend/scripts/seed_railway_mock_user.py
```

## 🐛 Correções Aplicadas

✅ Nome do usuário aparece corretamente em todas as abas
✅ Modo escuro com transições suaves (0.3-0.4s cubic-bezier)
✅ Design minimalista e profissional
✅ Cores otimizadas para modo claro e escuro

## 🌐 URL do Frontend

https://codigos-nexa-production.up.railway.app
