# Git-hooks

## pre-commit — blokkeert documenten/data in de repo

Deze repo is **publiek**. Documenten en databestanden (`.docx`, `.doc`, `.pdf`,
`.xls(x)/.xlsm`, `.ppt(x)`, `.csv`, Word-tempbestanden `~$...`) mogen er nooit in
terechtkomen vanwege AVG/vertrouwelijkheid. Ze staan al in `.gitignore`; de
pre-commit hook is een extra harde rem (ook tegen `git add -f`).

### Installeren (eenmalig, per kloon)

```bash
git config core.hooksPath scripts/git-hooks
```

Daarna weigert `git commit` zodra er zo'n bestand in de staging staat.
Bewuste uitzondering: `git commit --no-verify`.
