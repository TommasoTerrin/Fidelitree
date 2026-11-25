# Decisioni (ADR brevi)

Una scheda per ogni decisione architetturale o di business che vincola il codice. Sostituisce l'abitudine di
accumulare i vincoli in `AGENTS.md`: **dal 2026-11-11 le decisioni nuove si scrivono qui**, non nella sezione
«Vincoli e trade-off accettati» di AGENTS.md (le voci già lì verranno migrate un po' alla volta).

## Quando si scrive una scheda

- al **gate 1** (`/spec`): per ogni decisione del grilling che cambia un vincolo esistente o ne introduce uno nuovo;
- con **`/fix`**: quando una voce `F-NN` cambia una decisione presa;
- con **`/improve-architecture`**: quando il founder sceglie una delle opzioni proposte.

Una scheda non si cancella mai: se una decisione cambia, la vecchia diventa `sostituita da NNNN` e se ne scrive una
nuova. Così chi legge vede sia la regola di oggi sia il perché di quella di ieri.

## Formato (`NNNN-slug.md`, numero progressivo a 4 cifre)

```markdown
# NNNN — <titolo breve>

- **Stato**: accettata | sostituita da NNNN
- **Data**: AAAA-MM-GG
- **Versione**: vX.Y.Z (spec: `.agents/tickets/vX.Y.Z/README.md`, decisione Dn o voce F-NN)
- **Area**: <file di `.agents/specs/` toccato>

## Contesto
Il problema e i vincoli (Meta, Zernio, costi, privacy...), in 3-6 righe.

## Decisione
Cosa si fa, in modo verificabile.

## Alternative scartate
Una riga ciascuna, con il motivo.

## Conseguenze
Cosa diventa più facile, cosa più difficile, cosa resta da fare (roadmap).
```

## Indice

| # | Decisione | Stato | Area |
|---|---|---|---|
| — | Le decisioni fino a v0.3.0 sono in AGENTS.md, «Vincoli e trade-off accettati» | | |
| [0001](0001-campagne-pilota-coupon-dm.md) | Campagne pilota: il coupon è il DM | accettata | `campagne.md` |
| [0002](0002-commenti-risposta-privata-testo.md) | Commenti Instagram: risposta privata di solo testo | accettata | `carta-instagram.md` |
| [0003](0003-pausa-archivia-campagne.md) | La pausa del negozio archivia le campagne | accettata | `merchant-auth-stato.md`, `admin.md` |
| [0004](0004-applica-nello-scanner.md) | «Applica» nello scanner | accettata | `carta-e-scanner.md` |
| [0005](0005-migrazioni-sql-a-mano.md) | Migrazioni con script SQL a mano | accettata | `dati-e-segreti.md` |
