import { Fragment, type ReactNode } from 'react';

/**
 * Markdown mínimo para as respostas do agente.
 *
 * O agente responde com **negrito**, listas e títulos; a bolha mostrava os
 * asteriscos crus. Este renderizador monta elementos React (nunca HTML em
 * string), então o texto do modelo não tem como injetar marcação.
 *
 * Suporta: parágrafos, # títulos, listas "-"/"*"/"1.", **negrito**, *itálico*,
 * `código` e links [texto](https://…) — só http(s).
 */

function inline(texto: string, chave: string): ReactNode[] {
  const partes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|\*[^*\s][^*]*\*)/g;
  let ultimo = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(texto))) {
    if (m.index > ultimo) partes.push(texto.slice(ultimo, m.index));
    const t = m[0];
    const k = `${chave}-${i++}`;
    if (t.startsWith('**')) partes.push(<strong key={k}>{t.slice(2, -2)}</strong>);
    else if (t.startsWith('`')) partes.push(<code key={k}>{t.slice(1, -1)}</code>);
    else if (t.startsWith('[')) {
      const [, rotulo, url] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(t) || [];
      partes.push(<a key={k} href={url} target="_blank" rel="noopener noreferrer">{rotulo}</a>);
    } else partes.push(<em key={k}>{t.slice(1, -1)}</em>);
    ultimo = m.index + t.length;
  }
  if (ultimo < texto.length) partes.push(texto.slice(ultimo));
  return partes;
}

export function Markdown({ texto }: { texto: string }) {
  const linhas = (texto || '').replace(/\r\n/g, '\n').split('\n');
  const blocos: ReactNode[] = [];
  let lista: { ordenada: boolean; itens: string[] } | null = null;
  let paragrafo: string[] = [];

  const fecharParagrafo = () => {
    if (paragrafo.length) {
      const k = `p${blocos.length}`;
      blocos.push(
        <p key={k}>
          {paragrafo.map((l, i) => (
            <Fragment key={i}>{i > 0 && <br />}{inline(l, `${k}-${i}`)}</Fragment>
          ))}
        </p>,
      );
      paragrafo = [];
    }
  };
  const fecharLista = () => {
    if (lista) {
      const k = `l${blocos.length}`;
      const itens = lista.itens.map((it, i) => <li key={i}>{inline(it, `${k}-${i}`)}</li>);
      blocos.push(lista.ordenada ? <ol key={k}>{itens}</ol> : <ul key={k}>{itens}</ul>);
      lista = null;
    }
  };

  for (const bruta of linhas) {
    const linha = bruta.trimEnd();
    const titulo = /^(#{1,4})\s+(.*)$/.exec(linha);
    const item = /^\s*([-*•]|\d+[.)])\s+(.*)$/.exec(linha);
    if (!linha.trim()) {
      fecharParagrafo();
      fecharLista();
    } else if (titulo) {
      fecharParagrafo();
      fecharLista();
      blocos.push(<p key={`h${blocos.length}`} className="md-h"><strong>{inline(titulo[2], `h${blocos.length}`)}</strong></p>);
    } else if (/^\s*(---+|\*\*\*+)\s*$/.test(linha)) {
      fecharParagrafo();
      fecharLista();
      blocos.push(<hr key={`r${blocos.length}`} />);
    } else if (item) {
      fecharParagrafo();
      const ordenada = /\d/.test(item[1]);
      if (lista && lista.ordenada !== ordenada) fecharLista();
      if (!lista) lista = { ordenada, itens: [] };
      lista.itens.push(item[2]);
    } else {
      fecharLista();
      paragrafo.push(linha);
    }
  }
  fecharParagrafo();
  fecharLista();
  return <div className="md">{blocos}</div>;
}
