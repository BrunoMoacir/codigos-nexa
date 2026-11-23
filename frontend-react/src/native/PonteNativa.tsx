import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { onSessionChange, session } from '../api/session';
import { iniciarNavegacaoNativa } from './navegacao';
import { ehNativo } from './plataforma';
import { ouvirToquesNasNotificacoes, sincronizarPushNativo } from './pushNativo';
import { configurarWidgetNativo } from './widgetNativo';

/**
 * Liga o app web ao app nativo (não desenha nada). Quase tudo só roda dentro do
 * Capacitor. A exceção é a conciliação do Web Push no navegador, depois de um
 * login novo. Fica dentro do Router para poder navegar quando a pessoa toca
 * numa notificação.
 */
export function PonteNativa() {
  const navigate = useNavigate();

  useEffect(() => {
    if (!ehNativo()) return;
    const pararNavegacao = iniciarNavegacaoNativa();
    const pararToques = ouvirToquesNasNotificacoes((rota) => navigate(rota));

    // Sessão ativa → credencial nova para o widget (rotaciona a cada abertura do
    // app) e o aparelho de push confirmado (o reset de senha revoga os dois)
    const sincronizarWidget = () => {
      if (session.isActive && session.userId) {
        configurarWidgetNativo(session.userId).catch(() => {
          /* sem rede ou backend fora: o widget tenta de novo na próxima abertura */
        });
        sincronizarPushNativo(session.userId).catch(() => {
          /* idem: o push é confirmado de novo na próxima abertura */
        });
      }
    };
    sincronizarWidget();
    const pararSessao = onSessionChange(sincronizarWidget);

    return () => {
      pararNavegacao();
      pararToques();
      pararSessao();
    };
  }, [navigate]);

  // Navegador: o reset de senha e o "sair de todos os aparelhos" revogam as
  // inscrições de Web Push no servidor. Ao entrar de novo, o navegador que já
  // tinha push ligado reenvia a inscrição (getPushState concilia navegador ×
  // servidor). Sem permissão concedida, nada é feito.
  useEffect(() => {
    if (ehNativo()) return;
    // só na entrada de uma sessão (ou troca de conta), não a cada escrita no
    // localStorage de outra aba
    let ultimaConta: string | null = null;
    const conciliar = () => {
      const conta = session.isActive && session.userId ? session.userId : null;
      if (conta === ultimaConta) return;
      ultimaConta = conta;
      if (!conta) return;
      if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
      import('../pwa/push')
        .then(({ getPushState }) => getPushState())
        .catch(() => {
          /* sem rede ou backend fora: concilia de novo no próximo login ou no Perfil */
        });
    };
    conciliar();
    return onSessionChange(conciliar);
  }, []);

  return null;
}
