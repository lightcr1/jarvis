# Branch-Workflow: dev → main

Seit 21.09.2026 laufen alle Änderungen über einen `dev`-Integrationsbranch,
bevor sie auf `main` landen.

```text
Feature-Branch → PR → dev  →  (dev→main PR)  →  main
```

## `dev` (Integrationsbranch)

- Jede Änderung kommt als Pull Request gegen `dev`.
- Erforderliche Checks müssen grün sein (CI).
- CODEOWNERS-geschützte Pfade brauchen zusätzlich ein Owner-Review.
- Unkritische, vollständig geprüfte PRs dürfen ohne allgemeine Review-Pflicht
  gemergt werden (Autonomie-Kanal für den Jarvis-Agenten).
- Dependabot öffnet seine Update-PRs standardmäßig gegen `dev`
  (`target-branch: dev` in `.github/dependabot.yml`).

## `main` (stabiler Produktionsbranch)

- Nur über Pull Requests aus `dev`.
- Erfordert 1 Review + CODEOWNERS-Review (geschützte Pfade) + grüne CI.
- Keine direkten Pushes, kein Force-Push, kein Löschen.

## Regeln beider Branches

- `deletion` blockiert Branch-Löschung
- `non_fast_forward` blockiert Force-Pushes
- `required_status_checks` erzwingt die CI-Checks

Die Regeln liegen als GitHub Rulesets:

| Repo | dev | main |
| --- | --- | --- |
| `lightcr1/jarvis` | Dev Branch Integration | Main Branch Protection |
| `lightcr1/runpod` | Dev Branch Integration | Main Branch Protection |

## Warum

Der Agent (OpenHands/Jarvis) arbeitet auf eigenen Branches und merged nach
erfolgreichen Checks selbstständig nach `dev`. `main` bleibt menschlich
kontrolliert: Der Weg zum Produktivstand führt immer über einen expliziten
`dev`→`main`-PR, den der Besitzer reviewt und merged.
