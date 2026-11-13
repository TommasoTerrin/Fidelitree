# Ticket 04 — Commenti: `comment.received` → risposta privata

> v0.4.1. Dipende da: 03. Criteri: AC-14..20; I3, I6.
> Priorità: bloccante, con uscita di **piano B** (decisione 13: se i commenti non funzionano con l'account Zernio
> gratuito si spegne il ramo e `WEBHOOK_EVENTS` torna a solo `message.received`). Chi lo fa: agente.
> Rischio esterno: **Zernio/Meta non verificati** (`comment.received` sull'account gratuito, campi del payload,
> risposta privata a un non follower e nella quota): collaudo solo alla fine (ticket 07), per decisione del founder.
> Contract congelato: [contracts.md](contracts.md). Spec: [README.md](README.md).

## Obiettivo
Un commento uguale alla parola chiave di una campagna attiva riceve una risposta privata di solo testo con la promo
(o «offerte terminate»); un commento `CARTA` riceve l'invito a scrivere `CARTA` in chat, in ogni stato del negozio. I
negozi collegati da ora sottoscrivono anche `comment.received`.

## Da fare
- `zernio_service`: `build_private_reply_body`, `send_private_reply` con la sua classificazione degli errori,
  `WEBHOOK_EVENTS` con `comment.received` (§7). Riprendere dall'archivio: `git show 621a278 --
  app/services/zernio_service.py scripts/zernio_check.py tests/test_zernio_client.py` (comando
  `send-private-reply` di `zernio_check` compreso), citando il commit.
- `instagram_service` core: `InboundComment`, `parse_comment_received`, `build_comment_card_invite_text` (§6).
- `instagram_service` shell: smistamento per `event` e flusso dei commenti (§6) con la mappatura propria degli errori
  (AC-18); log con canale `commento`, mai testo, id del commento o del post.
- Aggiornare i due test che oggi verificano `events == ["message.received"]` (`tests/test_instagram_onboarding.py`,
  `tests/test_zernio_client.py`).
- Aggiornare `AGENTS.md` («Comandi»: `zernio_check ... send-private-reply`) e
  `.agents/architecture/zernio-notes.md` (righe «da spec» dell'archivio sui commenti).
- Spec vive: `.agents/specs/carta-instagram.md` con i commenti (scheda 0002).

## File coinvolti
- **Modifica**: `app/services/zernio_service.py`, `app/services/instagram_service.py`, `scripts/zernio_check.py`,
  `tests/test_zernio_client.py`, `tests/test_instagram_onboarding.py`, `tests/` (nuovi), `AGENTS.md`,
  `.agents/architecture/zernio-notes.md`, `.agents/specs/carta-instagram.md`.
- **Solo lettura** (contesto): `app/services/campaign_service.py`, `app/services/merchant_service.py`
  (`connect_instagram_account`), archivio `feature/campagne` (`621a278`).

## Collaudo
Passi in `collaudo.md` (sezione «v0.4.1 — campagne»), da fare con Instagram vero nel ticket 07:
1. «Scollega» e ricollega il profilo del negozio (sottoscrive `comment.received`).
2. Da un profilo cliente commenta `NATALE` sotto un post → arriva un DM con la promo; sotto il post nessuna risposta
   pubblica; in `/admin` richieste da commento = 1.
3. Commenta `CARTA` → DM «Per ricevere la tua carta scrivici CARTA qui in chat»; poi DM `CARTA` → card di oggi.
4. Commenta `NATALE` dallo stesso profilo una seconda volta → seconda risposta privata (un commento nuovo è una
   richiesta nuova).
5. Da un profilo che **non segue** il negozio: commento `NATALE` → DM consegnato? (esito in `zernio-notes.md`).

## Metodo
- TDD con `/implement 04`: `ft-test-writer` scrive UN test da UN criterio e il coordinatore osserva il rosso;
  `ft-implementer` scrive il minimo senza leggere il test; il contract è l'unico canale; `ft-referee` solo se test e
  codice sono entrambi difendibili.
- Commenti italiani precisi e completi (regola 4 di AGENTS.md), anche in test e script.
- `python -m pytest` verde prima del commit; commit in italiano «… (ticket 04)»; aggiorna `planner/current.md`.
- A fine ticket: riepilogo di 3 righe e attesa dell'ok. Niente push né PR.

## Stato
✅ fatto il 2026-11-13 (1123 test verdi, partenza 1098; attende l'ok).

**Fatto**: `zernio_service` (`build_private_reply_body`, `send_private_reply` con 502 incerto → `TIMEOUT`, `WEBHOOK_EVENTS` con
`comment.received`) e comando `zernio_check send-private-reply`, ripresi dall'archivio `621a278`; `instagram_service` core
(`InboundComment`, `parse_comment_received`, `build_comment_card_invite_text`) e shell (`_process_comment`, mappatura propria
degli errori). Spec viva `carta-instagram.md`, `zernio-notes.md` (righe «da verificare»), AGENTS.md, passi 10-14 di `collaudo.md`.

**Scelte**: i test e il codice di `zernio_service`/`zernio_check` sono quelli dell'archivio (autorizzato dal ticket), con il rosso
osservato prima di applicare il codice; aggiornato anche un terzo test non previsto dal ticket
(`tests/unit/test_zernio_core.py::test_build_webhook_body`, lista degli eventi). Nessun ramo per i «commenti dell'account del
negozio»: il contract non legge `author`, quindi seguono le stesse regole degli altri.
**Limiti**: tutto «da spec», mai provato su Zernio/Meta (collaudo nel ticket 07); il piano B resta disponibile.

### Registro TDD
- AC-20 → tests/test_zernio_client.py::test_register_webhook_corpo_e_id, tests/test_instagram_onboarding.py, tests/unit/test_zernio_core.py — rosso asserzione, verde al tentativo 1 (codice dall'archivio)
- zernio_service (risposta privata, §7) → tests/test_zernio_client.py::test_send_private_reply_* — rosso import/attributo, verde al tentativo 1 (da archivio)
- AC-16 → tests/test_webhook_comments.py::test_commento_carta_riceve_l_invito_in_risposta_privata_in_ogni_stato_senza_carta_ne_contatori — rosso asserzione, verde al tentativo 1
- AC-15 → tests/test_webhook_comments.py::test_commento_con_parola_di_campagna_riceve_la_promo_in_risposta_privata_e_conta_come_commento — rosso asserzione, verde al tentativo 1
- AC-17 → tests/test_webhook_comments.py::test_commento_che_non_attiva_nessuna_campagna_e_ignorato_senza_invio_ne_contatori — coperto (passa subito, 4 casi)
- AC-18 → tests/test_webhook_comments.py::test_errore_della_risposta_privata_un_solo_tentativo_esito_giusto_e_richiesta_contata — coperto (7 casi; mappatura scritta insieme ad AC-16)
- AC-19 → tests/test_webhook_comments.py::test_risposta_privata_riuscita_conta_nella_quota_come_un_dm_e_attiva_il_negozio_in_attesa_del_dm_di_prova — coperto
- AC-14 → tests/test_webhook_comments.py::test_commento_ripetuto_con_lo_stesso_evento_non_invia_ne_conta_due_volte_e_firma_errata_401, ::test_risposta_a_un_altro_commento_vale_come_un_commento_normale — coperto
