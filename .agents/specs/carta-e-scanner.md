# Pagina carta, QR, scanner del merchant

> Questo file descrive per ora **solo la parte campagne dello scanner**, che è **da v0.4.1, non ancora in produzione**
> (ticket 05). Il resto dell'area (pagina `/c/<token>`, QR, scan, PWA, aggiunta e rimozione di punti e cashback)
> resta da scrivere a partire da AGENTS.md e dal codice. Scheda: [0004](../decisions/0004-applica-nello-scanner.md). Spec della versione:
> [tickets/v0.4.1/README.md](../tickets/v0.4.1/README.md) (AC-21..26).

## Campagne nella gestione della carta (da v0.4.1, non ancora in produzione)

Pagina `GET /merchant/card/{card_id}/manage` (sessione merchant; carta inesistente o di un altro negozio → 404).

- **Blocco campagne** (AC-21): se il negozio ha campagne **non archiviate**, la pagina contiene `id="campaigns-section"`
  con un `<button data-campaign-id>` per campagna, etichetta «Applica <nome> (+X €)» oppure «Applica <nome>» con
  importo 0, ordinate dalla più recente. Senza campagne la pagina è identica a prima: né blocco né script.
- **Bottoni disattivati** (AC-24): con importo > 0 e negozio in attesa o in pausa il bottone è `disabled` (banner di
  oggi); un bottone senza importo resta attivo.
- **Conferma** (AC-22): il bottone apre la finestra sì/no già presente; il testo entra solo con `textContent`. Con
  «ANNULLA» non parte nessuna richiesta (verifica solo a mano, nel collaudo).

### «Applica»: `POST /api/merchant/card/{card_id}/campaigns/{campaign_id}/apply`

Sessione merchant, nessun corpo. Risposta 200 `{"card": CardResponse, "applied_cashback": euro}`.

- Ordine dei controlli (AC-24, AC-25): carta non del negozio → 404; campagna inesistente o di un altro negozio → 404;
  negozio non attivo con importo attuale > 0 → 403. Tutto prima di scrivere.
- Una campagna **archiviata** dopo il caricamento della pagina si applica comunque (AC-25).
- Scrittura (AC-23): `cashback_cents += importo ATTUALE` e `uses += 1` con due `UPDATE` atomici in **un** commit
  (nessun incremento perso). Importo 0 → solo l'utilizzo, anche a negozio non attivo.
- **Cosa non tocca** (AC-26): tree points, pool del mese, conversione, registro `PointTransaction`; la pagina cliente
  `/c/<token>` cambia solo nel saldo cashback.

Codice: `app/services/campaign_service.py` (`scanner_campaigns`, `apply_campaign`), `app/services/db_crud/campaign_crud.py`
(`apply_to_card`), `app/routes/merchant/views.py` e `api.py`, `app/templates/merchant/update_card.html`.
