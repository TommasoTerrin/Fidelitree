# Ticket 03 — Webhook: parola chiave di campagna in DM e risposte alle storie

> v0.4.1. Dipende da: 01 (02 consigliato prima, per creare campagne a mano nel collaudo). Criteri: AC-09..13; I1, I3,
> I4, I6.
> Priorità: bloccante. Chi lo fa: agente. Rischio esterno: Zernio/Meta (testo della risposta a una storia: da
> verificare nel collaudo finale, ticket 06).
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
⬜ da fare
