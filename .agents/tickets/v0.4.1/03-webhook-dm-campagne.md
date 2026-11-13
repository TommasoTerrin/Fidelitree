# Ticket 03 — Webhook: parola chiave di campagna in DM e risposte alle storie

> v0.4.1. Dipende da: 01 (02 consigliato prima, per creare campagne a mano nel collaudo). Criteri: AC-09..13; I1, I3,
> I4, I6.
> Priorità: bloccante. Chi lo fa: agente. Rischio esterno: Zernio/Meta (testo della risposta a una storia: da
> verificare nel collaudo finale, ticket 07).
> Contract congelato: [contracts.md](contracts.md). Spec: [README.md](README.md).

## Obiettivo
Chi scrive in DM (o risponde a una storia con) la parola chiave di una campagna attiva riceve un DM di testo con la
promo, o «offerte terminate» oltre il limite; la richiesta si conta in modo atomico. `CARTA` e la voce di menu non
cambiano.

## Da fare
- Shell webhook di `campaign_service`: `CampaignReply`, `register_request` (`UPDATE … RETURNING`, un solo statement),
  `handle_campaign_request` (§5).
- In `instagram_service._process_message` il passo della campagna dopo `CARTA`/menu (§6, «flusso dei DM»): conteggio
  prima della finestra, `send_text` con chiave `f"{event_id}:promo"`, `_record_send`, `_handle_send_error`; nessuna
  carta toccata, `isFollower` ignorato.
- Log con id della campagna e canale `dm`, mai testo né IGSID.
- Test con il payload della risposta a una storia (`metadata.storyReply`) e test di atomicità di AC-11 con un oggetto
  `Campaign` caricato prima di un incremento fatto da un'altra sessione (§11).
- Aggiornare il docstring di modulo di `instagram_service` (trigger delle campagne).
- Spec vive: crea `.agents/specs/carta-instagram.md` (regole di oggi da AGENTS.md più le parole chiave delle campagne
  in DM, scheda 0002) con la nota «da v0.4.1, non ancora in produzione».

## File coinvolti
- **Modifica**: `app/services/campaign_service.py`, `app/services/db_crud/campaign_crud.py`,
  `app/services/instagram_service.py`, `tests/` (nuovi), `.agents/specs/carta-instagram.md`.
- **Solo lettura** (contesto): `app/services/zernio_service.py`, `tests/test_webhook.py`, `tests/conftest.py`
  (`signed_webhook`, `zernio_mock`, `instagram_merchant`).

## Collaudo
Passi in `collaudo.md` (sezione «v0.4.1 — campagne»), con `scripts.replay_webhook` o un DM vero:
1. `--text NATALE` su un negozio attivo con la campagna `NATALE` → DM con la promo e la riga «Per utilizzare questa
   offerta…»; in `/admin` richieste da DM = 1.
2. `--text "natale!!"` → stessa risposta; `--text "natale per me"` → nessuna risposta, contatore invariato.
3. Limite 1 e una richiesta già contata → `--text NATALE` → «Le offerte disponibili sono terminate…».
4. Campagna archiviata o negozio in pausa → nessuna risposta, contatori invariati.
5. `--text CARTA` → la card di oggi, invariata.

## Metodo
- TDD con `/implement 03`: `ft-test-writer` scrive UN test da UN criterio e il coordinatore osserva il rosso;
  `ft-implementer` scrive il minimo senza leggere il test; il contract è l'unico canale; `ft-referee` solo se test e
  codice sono entrambi difendibili.
- Commenti italiani precisi e completi (regola 4 di AGENTS.md), anche in test e script.
- `python -m pytest` verde prima del commit; commit in italiano «… (ticket 03)»; aggiorna `planner/current.md`.
- A fine ticket: riepilogo di 3 righe e attesa dell'ok. Niente push né PR.

## Stato
✅ fatto il 2026-11-13 (1098 test verdi, da 1074; attende l'ok)

### Registro TDD

- AC-09 (caso «Black-Friday!» → promo + dm_requests 1) → tests/test_webhook_campaigns.py::test_dm_con_parola_chiave_scritta_diversamente_invia_la_promo_e_conta_una_richiesta — rosso asserzione, verde al tentativo 1
- AC-09 (varianti e non riconoscimenti) → test_dm_con_varianti_… e test_dm_che_non_coincide_… — coperto (passano subito col primo verde; asserzioni su invii, contatori, esito)
- AC-09 (archiviata + non archiviata) → test_dm_con_parola_in_una_campagna_archiviata_… — coperto (archiviata con created_at più recente: il test fallirebbe se is_archived fosse ignorato)
- AC-09 (risposta a una storia) → test_risposta_a_una_storia_segue_lo_stesso_riconoscimento_di_un_dm — coperto
- AC-10 → test_dm_di_chi_non_segue_riceve_un_solo_invio_di_testo_identico_a_quello_di_un_follower — coperto (isFollower false: un invio, nessuna carta né PointTransaction)
- AC-12 → test_parola_di_campagna_archiviata_o_di_negozio_non_attivo_e_ignorata_senza_contare (3 scenari) — coperto
- AC-11 (oltre il limite) → test_dm_oltre_il_limite_riceve_offerte_terminate_ed_e_contato — coperto
- AC-11 (ultimo posto, <= e non <) → test_dm_che_porta_il_totale_esattamente_al_limite_riceve_ancora_la_promo — coperto
- AC-11 (atomicità) → tests/test_campaign_register_request.py::test_il_totale_richieste_parte_dal_database_e_non_dall_oggetto_in_memoria — coperto (sessione B incrementa prima; A ottiene 2 e non 1)
- AC-13 (dedup) → test_evento_ripetuto_con_lo_stesso_event_id_non_invia_e_non_conta_una_seconda_volta — coperto
- AC-13 (standby) → test_dm_in_standby_non_invia_non_conta_ed_e_registrato_come_standby — coperto
- AC-13 (finestra 24 ore) → test_dm_piu_vecchio_di_24_ore_non_invia_ma_la_richiesta_e_contata — coperto
- AC-13 (quota riuscito; timeout → SEND_UNCERTAIN, quota +1, un solo tentativo, negozio non attivato) → test_invio_riuscito_conta_la_quota_… e test_timeout_di_lettura_e_esito_incerto_… — coperto
- AC-13 (log) → test_log_del_dm_di_campagna_non_contengono_… (2 casi) — coperto; prova di mutazione fatta (testo del cliente aggiunto al log → i 2 casi falliscono), poi ripristinato
- AC-09 (CARTA e voce di menu invariate) → test_carta_e_voce_di_menu_seguono_il_flusso_di_oggi_… (2 casi) — coperto

### Cosa è stato fatto
- `campaign_service`: `CampaignReply`, `register_request`, `handle_campaign_request`; `campaign_crud.increment_request_counter`
  (un solo `UPDATE … RETURNING` più commit; nome non nel contract, che lascia libere le funzioni del crud).
- `instagram_service`: `_reply_with_campaign` in `_process_message` dopo `CARTA`/menu; docstring di modulo aggiornato.
- Spec viva `specs/carta-instagram.md` (nuova), `specs/campagne.md`, passi 5-9 in `collaudo.md`.

### Scelte e limiti
- Tutti i criteri dopo il primo (AC-09) sono passati subito: li copre l'implementazione del primo verde, che ha
  scritto l'intero passo della campagna; i test successivi sono guardie di regressione, tutti con asserzioni su invii,
  contatori ed esito. Prova di mutazione fatta sul test dei log (testo del cliente aggiunto al log → fallisce).
- «Negozio non ACTIVE» del contract §5 è `ServiceState` (non `instagram_status`): un negozio `AWAITING_TEST_DM` risponde.
- Un postback diverso dal nostro → `IGNORED`. Un `MessageTooLongError` → `SEND_FAILED` con la richiesta già contata.
- L'atomicità su Postgres non è provata da SQLite (contract §11): regge sull'`UPDATE … RETURNING`.
- Il corpo dell'invio testo è quello già usato dagli altri test del webhook (`send_text`).
