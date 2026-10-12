# claude-session-restorer

**Troque entre contas do Claude no Mac sem perder suas sessões do Claude Code.**

Quando você entra com outra conta no Claude Desktop, a aba **Code** aparece sem nenhuma sessão.
As conversas não sumiram: o app só guarda uma lista de sessões separada para cada conta. O
`claude-session-restorer` refaz essa lista para a conta que está logada, e você continua qualquer
sessão de onde parou. Ao voltar para a outra conta, basta rodar de novo. Dá para repetir quantas
vezes quiser.

🇺🇸 [Read in English](README.md)

> Port para macOS do
> [sahol3/claude-code-session-restorer](https://github.com/sahol3/claude-code-session-restorer)
> (Windows / PowerShell). Ferramenta não oficial da comunidade, sem vínculo com a Anthropic.

---

## Instalação

Requisitos: **macOS** e **Python 3.8+**. Quem usa Homebrew já tem Python, porque o Homebrew exige
as Command Line Tools da Apple, que incluem o `python3`. Confira com `python3 --version`; se não
tiver, rode `xcode-select --install`.

### Opção 1 — Homebrew (recomendado)

```bash
brew install guedesdiogo/tap/claude-session-restorer
```

Para atualizar depois: `brew upgrade claude-session-restorer`.

### Opção 2 — npm pelo GitHub Packages

O GitHub Packages exige um token do GitHub para instalar **qualquer** pacote npm, mesmo os
públicos. Configuração (só uma vez):

1. Crie um token **classic** em <https://github.com/settings/tokens/new> marcando só o escopo
   **`read:packages`**.
2. Configure o npm:

   ```bash
   echo "@guedesdiogo:registry=https://npm.pkg.github.com" >> ~/.npmrc
   echo "//npm.pkg.github.com/:_authToken=SEU_TOKEN_AQUI" >> ~/.npmrc
   ```

3. Instale:

   ```bash
   npm install -g @guedesdiogo/claude-session-restorer
   ```

O pacote npm só chama o mesmo script Python, então o Python 3 continua necessário.

### Opção 3 — só o script

```bash
curl -fsSLo /usr/local/bin/claude-session-restorer \
  https://raw.githubusercontent.com/guedesdiogo/claude-session-restorer/main/bin/claude-session-restorer
chmod +x /usr/local/bin/claude-session-restorer
```

Confira a instalação com `claude-session-restorer --version`.

---

## Uso rápido

1. No **Claude Desktop**, saia da conta atual, entre com a outra e abra a aba **Code** uma vez
   (ela vai aparecer vazia, e isso é esperado).
2. Rode:

   ```bash
   claude-session-restorer --quit --reopen
   ```

   O comando fecha o Claude Desktop, refaz a lista de sessões da conta logada e abre o app de novo.
3. Vá na aba **Code**, clique na sessão e continue.

Se preferir fazer à mão: feche o Claude com **Cmd+Q** (fechar a janela não basta), rode
`claude-session-restorer` e abra o Claude de novo.

---

## Alternando entre duas contas sempre que precisar

A rotina é a mesma nos dois sentidos:

| Passo | Conta A → Conta B | Conta B → Conta A |
| ----- | ----------------- | ----------------- |
| 1 | Sair da A, entrar com a B, abrir a aba Code | Sair da B, entrar com a A, abrir a aba Code |
| 2 | `claude-session-restorer --quit --reopen` | `claude-session-restorer --quit --reopen` |
| 3 | Continuar qualquer sessão na B | Continuar qualquer sessão na A, inclusive o que você fez na B |

Por que funciona nos dois sentidos:

- Cada sessão fica salva uma única vez no disco, num transcript que não pertence a nenhuma conta.
  Quando você continua a sessão na conta B, as mensagens novas vão para esse mesmo transcript.
- Ao voltar para a A, o card da sessão na A ainda aponta para esse transcript, então tudo o que
  você fez na B aparece.
- Sessões novas que você criou na B são copiadas para a A na próxima execução.
- Rodar de novo nunca cria duplicatas.

Evite:

- **Usar a mesma sessão nas duas contas ao mesmo tempo** (por exemplo, uma no app e outra no
  terminal). As duas escreveriam no mesmo transcript.
- **Trocar de conta no meio de uma resposta.** Espere o Claude terminar.

Atalho opcional (adicione ao `~/.zshrc`):

```bash
alias trocar-conta='claude-session-restorer --quit --reopen'
```

---

## Opções

| Opção | O que faz |
| ----- | --------- |
| `--list` | Mostra as pastas de conta, quantas sessões cada uma tem e qual está logada. Não altera nada. |
| `--dry-run` | Mostra o que seria copiado ou criado, sem gravar nada. |
| `--quit` | Fecha o Claude Desktop antes de restaurar e espera ele terminar de sair. |
| `--reopen` | Abre o Claude Desktop de novo no final. |
| `--existing-cards-only` | Move só as sessões criadas na aba Code do app e ignora as do terminal (`claude`) e do VS Code. |
| `--account UUID --org UUID` | Restaura nesta conta em vez da detectada em `~/.claude.json`. |
| `--cards-dir PATH` | Usa outra pasta de cards do Claude Desktop. |
| `--projects-dir PATH` | Usa outra pasta de transcripts do Claude Code. |
| `--dest-root PATH` | Grava os cards numa pasta de teste em vez da real. |
| `--ignore-running` | Não interrompe se o Claude Desktop parecer aberto. Não recomendado. |
| `--no-backup` | Pula o backup. Só para teste. |
| `--version` | Mostra a versão. |

---

## Como funciona

O Claude Code grava cada conversa num transcript:

```
~/.claude/projects/<pasta-do-projeto>/<sessionId>.jsonl
```

Os transcripts são organizados por pasta de projeto e **não guardam nenhuma informação de conta**.

A aba **Code** do Claude Desktop não lê os transcripts diretamente. Ela lê um "card" pequeno para
cada sessão, guardado **por conta**:

```
~/Library/Application Support/Claude/claude-code-sessions/<accountId>/<organizationId>/local_*.json
```

Cada card aponta para o seu transcript pelo campo `cliSessionId`. A cada execução, a ferramenta:

1. Lê a conta logada em `~/.claude.json`.
2. Faz backup da pasta `claude-code-sessions` inteira.
3. Copia para a conta atual os cards das outras contas cujo transcript ainda não está listado.
4. Cria um card para cada transcript que ainda não tem nenhum, usando o título gerado pelo Claude,
   um resumo ou a primeira mensagem, nessa ordem.

---

## Segurança, backup e como desfazer

- **Backup:** antes de gravar, a pasta de cards inteira é copiada para
  `~/Library/Application Support/Claude/claude-code-sessions_backup_<data>_<hora>`.
- **Só adiciona:** os transcripts nunca são alterados nem apagados.
- **Pode rodar quantas vezes quiser:** o que já existe é ignorado.
- **Para desfazer:** feche o Claude, apague `claude-code-sessions`, renomeie o backup desejado para
  `claude-code-sessions` e abra o Claude.

Os backups vão se acumulando. Apague os antigos quando não precisar mais:

```bash
ls -d ~/Library/Application\ Support/Claude/claude-code-sessions_backup_*
```

### Guardar os transcripts por mais tempo

O Claude Code apaga transcripts com mais de `cleanupPeriodDays` dias (30 por padrão). Para guardar
por mais tempo, coloque em `~/.claude/settings.json`:

```json
{ "cleanupPeriodDays": 3650 }
```

---

## Problemas comuns

**"Claude Desktop is still running"** — O app reescreve a pasta de cards ao fechar, então ele
precisa estar fechado. Use `--quit` ou feche com **Cmd+Q**.

**"Could not read the logged-in account"** — Entre no Claude Desktop e abra a aba Code uma vez.
Depois rode de novo. Também dá para passar `--account` e `--org`; os IDs aparecem em
`claude-session-restorer --list`.

**A conta detectada é a antiga** — Abra o Claude Desktop, entre na aba Code com a conta nova,
feche com Cmd+Q e rode de novo. Confira com `--list`.

**A pasta de cards "does not exist"** — Sua versão do Claude Desktop pode guardar os cards em outro
lugar. Procure com `ls ~/Library/Application\ Support/Claude/`, use `--cards-dir` e
[abra uma issue](https://github.com/guedesdiogo/claude-session-restorer/issues).

**Sessões na nuvem** — Sessões que rodaram na nuvem (Claude Code na web ou remoto) ficam presas à
conta que as criou e não são movidas por esta ferramenta.

---

## Retomar pelo terminal

Se você não se importa em continuar pelo terminal, não precisa desta ferramenta. Na pasta do
projeto:

```bash
claude --continue          # sessão mais recente desta pasta
claude --resume            # escolher numa lista
```

---

## Créditos e licença

- Ferramenta original para Windows e o estudo do formato dos cards:
  [sahol3/claude-code-session-restorer](https://github.com/sahol3/claude-code-session-restorer).
- Port para macOS, empacotamento e opções extras: [Diogo Guedes](https://github.com/guedesdiogo).

[MIT](LICENSE). O formato dos arquivos foi descoberto por observação e pode mudar em qualquer
atualização do Claude Desktop. Use por sua conta e risco.
