import { useEffect, useState } from 'react';
import { onSessionChange, session } from '../api/session';

export interface SessionSnapshot {
  isActive: boolean;
  userId: string;
  userName: string;
  userEmail: string;
  /** Nome para exibir: nome completo, senão a parte local do e-mail. */
  displayName: string;
}

function snapshot(): SessionSnapshot {
  const userName = session.userName;
  const userEmail = session.userEmail;
  return {
    isActive: session.isActive,
    userId: session.userId,
    userName,
    userEmail,
    displayName: userName || (userEmail ? userEmail.split('@')[0] : 'Usuário'),
  };
}

/** Sessão reativa: atualiza em login, logout e quando outra aba muda a sessão. */
export function useSession(): SessionSnapshot {
  const [estado, setEstado] = useState<SessionSnapshot>(snapshot);
  useEffect(() => onSessionChange(() => setEstado(snapshot())), []);
  return estado;
}
