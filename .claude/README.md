# .claude/ — value-lab

Configuração do Claude Code. Onde cada coisa MORA (conforme o post oficial
"Steering Claude Code", jun/2026):

- **CLAUDE.md** (raiz do repo) — fatos sempre carregados: camadas, regra de ouro,
  versões. Mantido < 200 linhas.
- **rules/** — restrições path-scoped (carregam só quando o arquivo casa). Os
  invariantes "duros" da arquitetura.
- **agents/** — subagentes de revisão em contexto isolado (model: opus, alinhado
  ao seu fluxo Opus-revisa / Sonnet-implementa).
- **skills/** — procedimentos invocáveis + auto-descobríveis (/run-backtest, /add-league).
- **commands/** — LEGADO (fundido em skills). 2 atalhos finos de exemplo.
- **hooks/** + **settings.json** — guard-rails determinísticos (formatar, bloquear
  libs pesadas na API, rodar testes do domínio).

> ⚠ Hooks executam comandos com SUAS credenciais. Revise os scripts em hooks/
> antes de habilitar. O contrato de I/O dos hooks pode variar por versão do CLI —
> confira em code.claude.com/docs/en/hooks se algo não disparar.
