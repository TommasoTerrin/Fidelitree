# Ticket 09 — «Applica»: accredito solo se la campagna è attiva, e pulsante bloccato dopo errore di rete

> v0.4.1. Nasce da **F-02 (b) e (c)**. Criteri: **AC-32** (atomicità con campagna sparita) e **AC-33** (pulsante dopo
> errore di rete). Priorità: consigliata. Chi lo fa: agente. Dipende da: —. Rischio esterno: nessuno.
> Contract: invariato. Spec: [README.md](README.md). Il criterio AC-33 si prova anche a mano nel collaudo (come AC-22).

## Obiettivo
- **(c) AC-32**: il controllo sulla campagna e l'accredito devono essere nella stessa condizione atomica. Se la campagna
  è stata eliminata o archiviata tra la lettura e la scrittura, nessun accredito e nessun utilizzo, con errore leggibile.
- **(b) AC-33**: dopo un errore di rete su «Applica», il pulsante resta bloccato finché l'esito non è noto. Il merchant
  ricarica la pagina per vedere il cashback reale.

## Da fare
1. **Test rosso per AC-32** (ft-test-writer): campagna archiviata o eliminata nell'istante dell'accredito (simulata con una
   modifica tra la lettura e la scrittura) → nessun accredito, nessun utilizzo, errore 404 o 409.
2. Correzione in `app/services/campaign_service.py` (`apply_to_card` / `apply_campaign`): condizione atomica con `UPDATE`
   sulla campagna nello stesso passo, oppure controllo del `rowcount` nella stessa transazione. Test verde.
3. **AC-33** (`app/templates/merchant/update_card.html`, JavaScript di «Applica», riga ~387): dopo un errore di rete il
   pulsante resta disabilitato con l'avviso «ricarica la pagina per vedere l'esito». Nessun secondo invio automatico.
   Non c'è test automatico per il JavaScript: si verifica a mano sul telefono (aggiungere il passo al `collaudo.md`).

## File coinvolti
- **Modifica**: `app/services/campaign_service.py`, `app/templates/merchant/update_card.html`, `tests/test_scanner_campaigns.py`,
  `.agents/workflows/collaudo.md` (passo per AC-33).
- **Solo lettura**: `app/routes/merchant/` (route di «Applica»), `.agents/specs/carta-e-scanner.md`.

## Metodo
- AC-32 in TDD (rosso prima). AC-33 a mano, con il passo scritto nel collaudo.
- Commit locale in italiano: «… (ticket 09)». Riepilogo di 3 righe, attesa dell'ok. Niente push.

## Stato
⛔ superato da F-02 (b, c): AC-32 e AC-33 accettati come rischi (2026-11-25), nessun ticket da implementare.
