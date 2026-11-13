# Handoff v0.4.1 — campagne pilota

> Documento di passaggio per una sessione nuova. Leggi prima `CLAUDE.md`, poi il blocco «Harness» di
> `.agents/planner/current.md`, poi il `README.md` di questa cartella. Il resto sta qui.

## Dove siamo

- Branch `feature/campagne-pilota`, da `develop` (2026-11-12), con il processo a skill.
- **Gate 1 (spec) APPROVATO il 2026-11-12**: 30 criteri AC-01..30, schede 0001-0005 in `.agents/decisions/`.
- **Gate 2 APPROVATO il 2026-11-12**: `domain-model.md` (7 scostamenti accettati) e `contracts.md` congelati,
  ticket `01-…06-*.md` scritti.
- **Ticket 01 FATTO il 2026-11-12** (1066 test verdi; attende l'ok del founder): versione 0.4.1, `app/core/text.py`,
  modello `Campaign`, `migrations/0001_campagne.sql`, core puro completo di `campaign_service` (nessuna shell). Spec
  vive `campagne.md` e `dati-e-segreti.md` create. Prossimo: `/implement 02` (dopo l'ok).
- **Ticket 02 FATTO il 2026-11-13** (1074 test verdi; attende l'ok del founder): API admin e sezione «Campagne» della
  dashboard, la pausa archivia le campagne nello stesso commit. Spec viva `specs/admin.md`, passi in `collaudo.md`
  («v0.4.1 — campagne»). Prossimo: `/implement 03` (dopo l'ok).
- **Ticket 03 FATTO il 2026-11-13** (1098 test verdi; attende l'ok del founder): le parole chiave delle campagne in DM
  e nelle risposte alle storie rispondono con la promo (`_reply_with_campaign`), contatore atomico, spec viva
  `specs/carta-instagram.md`, passi 5-9 in `collaudo.md`. Prossimo: `/implement 04` (commenti, risposta privata,
  `WEBHOOK_EVENTS`; riusa `_handle_send_error`/`_record_send` ma con mappatura errori propria, contract §6).
- **Ticket 04 FATTO il 2026-11-13** (1123 test verdi; attende l'ok del founder): commenti `comment.received` con risposta privata
  (`_process_comment`), `WEBHOOK_EVENTS` con i commenti, `zernio_check send-private-reply`; tutto «da spec», da provare nel
  ticket 06 (piano B pronto). Prossimo: `/implement 05` (scanner «Applica»; aggiungere anche `scanner_campaigns` e il controllo
  di AC-06).
- Nessun push, nessuna PR.

## Cosa fare alla ripartenza

1. Leggi il ticket successivo e `contracts.md` (congelato: si cambia solo con `/fix`).
2. Un ticket per sessione con `/implement NN` (TDD con `ft-test-writer` e `ft-implementer` separati, commit locale,
   riepilogo e attesa dell'ok). Ordine: 01 → 02 → 03 → 04 → 05 → 06.

## Decisioni prese al gate 2 (2026-11-12)

- Scostamento 3: campagne create o ripristinate con il negozio in pausa **ammesse** (restano «ferme», nessun 409).
- Ticket 04 (commenti) **bloccante**, con l'uscita del piano B se i commenti non funzionano con l'account gratuito.
- Strumenti di collaudo **approvati**: `zernio_check send-private-reply` (04) e `replay_webhook --comment` (06).
- Gli altri scostamenti (1, 2, 4-7) accettati come scritti.

## Decisioni prese durante il ticket 02 (2026-11-13)

- Header privati (`no-store`, `noindex`, `Referrer-Policy`) **solo sulle risposte di successo**, come nel resto della
  dashboard (il contract diceva «ogni risposta»). Test e `specs/admin.md` lo riportano.
- `Campaign` ha `sqlite_autoincrement` (solo SQLite, fuori dal contract §3): da rivedere in `/review`.
- `scanner_campaigns` non esiste ancora: il controllo «sparisce dallo scanner» di AC-06 va aggiunto nel ticket 05.

## Fatti verificati e da verificare su Zernio

Nessun collaudo anticipato (decisione 13): tutto ciò che riguarda i commenti è **da spec**, mai provato dal vivo.

- Risposta privata: `POST /v1/inbox/comments/{postId}/{commentId}/private-reply`, corpo `accountId` + `message`, una
  per commento, entro 7 giorni (lo controlla Meta). 502 con `details.privateReplyOutcome: "unknown"` = esito incerto;
  400 con `details.privateReplyConsumed: true` = già usata. Nessun `Idempotency-Key` documentato. Codice pronto
  nell'archivio: commit `621a278` di `feature/campagne`.
- `comment.received`: `account.accountId`, `comment.id`, `comment.platformPostId`, `comment.text` (spec Zernio; da
  verificare). Leggiamo solo questi.
- Risposta a una storia: `message.received` con `metadata.storyReply`, testo in `message.text` (da verificare).
- Neon `development`: le 4 tabelle della vecchia v0.4.0 sono già state eliminate (commit `9c3e081`).
- SQLite locale 3.49.1 (serve ≥ 3.35 per `UPDATE … RETURNING`); SQLAlchemy 2.0.55.

## Vincoli di sicurezza da tenere

- Nessun testo dei clienti, IGSID, id di commento o di post, chiave Zernio o token nei log, nelle risposte o nel DB
  (I6). Le campagne non salvano dati dei clienti.
- Dashboard admin: sessione o `X-Admin-Key`, `Origin` sui POST/PUT/DELETE con cookie, `no-store`, `noindex`, DOM solo
  con `textContent`. Nello scanner il nome della campagna entra nella finestra di conferma solo con `textContent`.
- Webhook: risposta entro 5 secondi, sempre 200 per gli esiti, nessun nuovo tentativo sugli invii.
- Produzione con dati veri: lo script SQL si applica solo dopo il branch Neon di backup (`deploy.md`, ticket 06).

## File di riferimento

- `README.md` (spec, gate 1), `domain-model.md`, `contracts.md`, ticket `01-…06-*.md` di questa cartella.
- `.agents/decisions/0001-…0005-*.md` — schede delle aree toccate.
- `.agents/planner/current.md` — blocco «Harness» e tabella dei ticket.
- Archivio `feature/campagne`: `git show feature/campagne:.agents/tickets/v0.4.0/<file>`; codice utile nei commit
  `5d8a4d9` (`app/core/text.py`) e `621a278` (risposta privata).
- `.agents/architecture/zernio-notes.md`, `.agents/workflows/collaudo.md`, `deploy.md`.
