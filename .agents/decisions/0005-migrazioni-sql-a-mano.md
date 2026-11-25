# 0005 — Migrazioni con script SQL a mano

- **Stato**: accettata
- **Data**: 2026-11-12
- **Versione**: v0.4.1 (spec: `.agents/tickets/v0.4.1/README.md`, decisione 1, AC-28)
- **Area**: `dati-e-segreti.md`

## Contesto
Dal 2026-10-29 ogni modifica allo schema richiede una migrazione preparata prima (in produzione ci sono dati veri).
Lo schema è creato da `create_all()` all'avvio, che crea le tabelle mancanti ma non altera quelle esistenti; Alembic
non c'è. v0.4.1 aggiunge una sola tabella (`campaign`).

## Decisione
- Cartella `migrations/` con script SQL numerati (`NNNN_<slug>.sql`). Il primo, `0001_campagne.sql`, contiene una sola
  `CREATE TABLE IF NOT EXISTS` con i suoi indici: nessun `ALTER` su tabelle o tipi esistenti.
- Lo script e il modello SQLModel devono coincidere (colonne, default lato DB, `NOT NULL`, lunghezze, `ON DELETE
  CASCADE`), perché all'avvio `create_all()` può creare la stessa tabella da solo; un test lo verifica.
- Procedura: branch di backup di Neon `production`, `development` rifatto da `production`, script applicato e app
  provata, poi produzione (in `deploy.md`).

## Alternative scartate
- Alembic subito: dipendenza e procedura in più per una sola `CREATE TABLE`; resta in roadmap.
- Affidarsi solo a `create_all()`: nessuna traccia versionata dello schema e nessuna prova prima della produzione.

## Conseguenze
- Rollback dello schema non necessario (la vecchia app ignora la tabella); in caso estremo `DROP TABLE campaign`.
- Su Neon `development` possono esserci le tabelle della vecchia v0.4.0: vanno controllate ed eliminate, con l'ok del
  founder, prima del collaudo (altrimenti `IF NOT EXISTS` lascerebbe colonne vecchie).
