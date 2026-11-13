# Dati, segreti, privacy, log

> Creato dalla v0.4.1 (ticket 01) con le sole regole che questa versione tocca; il resto dell'area è ancora in
> AGENTS.md («Vincoli e trade-off accettati»). Le voci marcate «da v0.4.1» non sono ancora in produzione.

## Migrazioni dello schema (da v0.4.1, non ancora in produzione)

- Lo schema esistente non si altera mai con `create_all()`: ogni modifica passa da uno **script SQL scritto a mano**
  in `migrations/NNNN_nome.sql`, idempotente (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`), con un
  commento in testa che dice cosa crea e come si applica. Scheda:
  [0005](../decisions/0005-migrazioni-sql-a-mano.md).
- Si prova prima su Neon `development`, poi si applica a `production` dopo un branch di backup (procedura in
  [deploy.md](../workflows/deploy.md)).
- Un test (`tests/test_migrations.py`) controlla che ogni colonna e vincolo del modello compaia nello script e che lo
  script non contenga `ALTER`, `DROP` né `CREATE TYPE`. Non esegue lo script (su SQLite `SERIAL` non è un id
  automatico): la prova vera è su Neon.
- Primo script: `0001_campagne.sql` (tabella `campaign`).

## Dati dei clienti nelle campagne (da v0.4.1, non ancora in produzione)

Le campagne non salvano né testo dei messaggi, né IGSID, né username, né id dei commenti; i log riportano solo id del
negozio, id dell'evento, esito e (se c'è) id della campagna e canale.
