# Ticket 10 — Test mancanti sui criteri AC-10, AC-11, AC-15 e AC-17

> v0.4.1. Nasce da **F-03**. Nessun criterio nuovo, nessun comportamento nuovo. Priorità: consigliata. Chi lo fa:
> agente. Dipende da: —. Rischio esterno: nessuno. Contract: invariato. Spec: [README.md](README.md).

## Obiettivo
Aggiungere i test che mancano ai criteri già in spec, perché oggi i criteri risultano coperti solo in apparenza.

## Da fare (un test per volta, TDD)
1. **AC-10** (follower): test con `isFollower: true` → la risposta è la card con la promo, come da spec.
2. **AC-11** (contatore delle richieste): test che distingue una lettura fresca da una stantia (il contatore è incrementato
   sul valore attuale, non sull'oggetto caricato prima della modifica).
3. **AC-15** (limite via commento): commento oltre il limite → risposta «offerte terminate», contatore invariato.
4. **AC-17** (commento dell'account del negozio): commento con `author.id` uguale all'account del negozio → nessuna
   risposta privata, come da spec.
5. Se un test diventa rosso, **non correggere qui**: il comportamento sbagliato va in un ticket di correzione con `/fix`.

## File coinvolti
- **Modifica**: `tests/test_webhook_campaigns.py`, `tests/test_webhook_comments.py`, `tests/unit/test_campaign_core.py`
  (docstring con `AC-10`, `AC-11`, `AC-15`, `AC-17`).

## Metodo
- Ogni test cita il suo `AC-NN` nella docstring, così la tracciabilità lo trova.
- Commit locale in italiano: «… (ticket 10)». Riepilogo di 3 righe, attesa dell'ok. Niente push.

## Stato
⛔ superato da F-03: test mancanti su AC-10, AC-11, AC-15, AC-17 accettati come rischi (2026-11-25).
