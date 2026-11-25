# Ticket 08 — Log della risposta privata senza id di commento e post

> v0.4.1. Nasce da **F-02 (a)**. Criterio: **AC-31**. Priorità: consigliata (non blocca il merge se rimandata, ma
> la decisione D10 la chiede). Chi lo fa: agente. Dipende da: —. Rischio esterno: nessuno (solo log).
> Contract: invariato. Spec: [README.md](README.md).

## Obiettivo
`zernio_service._request` scrive nel log il path delle richieste, che per la risposta privata contiene id di post e di
commento. Il log deve riportare solo l'esito e l'id della campagna.

## Da fare
1. **Test rosso** (ft-test-writer): AC-31 — una risposta privata che passa per `_request` non scrive nel log né il path con
   `post_id`/`comment_id`, né il testo del commento. Il test controlla il log con `caplog`.
2. Correzione minima in `app/services/zernio_service.py` (il log scrive il path con gli id sostituiti, o non scrive il path):
   test verde.
3. Il test di log dei DM (AC-13) resta verde.

## File coinvolti
- **Modifica**: `app/services/zernio_service.py` (`_request`), `tests/test_zernio_client.py` (test nuovo, docstring con `AC-31`).
- **Solo lettura**: `app/services/instagram_service.py` (ramo commenti, che logga solo l'esito).

## Metodo
- Un criterio per volta, TDD: rosso osservato prima della correzione.
- Commit locale in italiano: «… (ticket 08)». Riepilogo di 3 righe, attesa dell'ok. Niente push.

## Stato
✅ fatto il 2026-11-25 (1140 test verdi; attende l'ok)

Registro TDD:
- AC-31 → tests/test_zernio_client.py::test_risposta_privata_con_errore_non_logga_id_di_post_ne_di_commento — rosso asserzione, verde al tentativo 1 (funzione `log_safe_path` in `zernio_service`)
