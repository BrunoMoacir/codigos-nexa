import { ehNativo } from './plataforma';

/**
 * Salva um arquivo gerado pelo app (export LGPD, dossiê ZIP, imagem do Wrapped).
 * No navegador: download normal. No app nativo o WebView ignora <a download>:
 * o arquivo vai para o cache do app e abre a folha de compartilhamento do
 * sistema (salvar em Arquivos, mandar por e-mail…).
 */
export async function salvarArquivo(blob: Blob, nome: string): Promise<void> {
  if (!ehNativo()) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return;
  }
  const [{ Filesystem, Directory }, { Share }] = await Promise.all([
    import('@capacitor/filesystem'),
    import('@capacitor/share'),
  ]);
  const base64 = await new Promise<string>((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(String(leitor.result).split(',')[1] || '');
    leitor.onerror = () => reject(leitor.error);
    leitor.readAsDataURL(blob);
  });
  const nomeSeguro = nome.replace(/[^A-Za-z0-9._-]/g, '_');
  const { uri } = await Filesystem.writeFile({ path: nomeSeguro, data: base64, directory: Directory.Cache });
  await Share.share({ title: nomeSeguro, url: uri });
}
