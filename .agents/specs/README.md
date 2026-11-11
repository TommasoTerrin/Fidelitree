# Spec vive (come funziona il sistema oggi)

Le spec delle versioni (`.agents/tickets/vX.Y.Z/README.md`) raccontano **cosa cambia** in una versione. I file di
questa cartella raccontano **come funziona oggi** ogni area del sistema, già sommando tutte le versioni rilasciate.
Chi deve toccare un'area legge prima il suo file qui, non la storia dei ticket.

**Si parte da v0.5.0** (decisione del founder del 2026-11-11): v0.4.0 si chiude con il metodo di prima (regole in
AGENTS.md); i file di questa cartella li crea la prima versione dalla v0.5.0 in poi che tocca l'area.

## Regole

- **Un file per area**, `<area>.md`. Contiene: a cosa serve l'area, regole di business vigenti, criteri chiave (con
  il rimando all'`AC-NN` della versione che li ha introdotti), invarianti, errori, file di codice principali,
  rimandi alle schede di `.agents/decisions/`.
- **Si aggiorna man mano, non a fine progetto**:
  - al gate 1 (`/spec`) la spec della versione elenca, nella tabella «Aree toccate», quali file di qui cambieranno e come;
  - a fine ticket (`/implement`), se il ticket ha reso vera una regola nuova, si aggiorna il file dell'area con la
    nota «(da vX.Y.Z, non ancora in produzione)»;
  - al rilascio (`/release`) si tolgono le note «non ancora in produzione».
- **Mai descrivere qui lo storico**: solo la regola valida. Lo storico sta nelle spec delle versioni e nelle decisioni.
- Se un'area non ha ancora il suo file, lo crea il primo ticket che la tocca, partendo da ciò che dice AGENTS.md
  («Vincoli e trade-off accettati») e dal codice.

## Aree

| Area | File | Stato |
|---|---|---|
| Carta via DM Instagram (trigger, card, follower, 24 h, quota, standby) | `carta-instagram.md` | da creare (oggi in AGENTS.md) |
| Pagina carta, QR, scanner del merchant | `carta-e-scanner.md` | da creare |
| Pool del negozio, livelli, chiusura mensile, Ecologi | `pool-alberi.md` | da creare |
| Auth dei merchant e stato del servizio | `merchant-auth-stato.md` | da creare |
| Dashboard admin del founder | `admin.md` | da creare |
| Campagne promozionali | `campagne.md` | da creare (v0.4.0, in sviluppo) |
| Dati, segreti, privacy, log | `dati-e-segreti.md` | da creare |
