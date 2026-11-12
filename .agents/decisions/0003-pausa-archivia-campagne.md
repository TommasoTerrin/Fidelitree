# 0003 — La pausa del negozio archivia le campagne

- **Stato**: accettata
- **Data**: 2026-11-12
- **Versione**: v0.4.1 (spec: `.agents/tickets/v0.4.1/README.md`, decisione 2, default D13)
- **Area**: `merchant-auth-stato.md`, `admin.md`

## Contesto
Il founder mette in pausa un negozio quando la prova è finita o l'abbonamento non è pagato. Se le sue campagne
restassero vive, i clienti riceverebbero coupon che in negozio non si possono applicare.

## Decisione
Quando un negozio passa ad «in pausa» — «Metti in pausa» della dashboard o `PUT /api/merchant/{id}` con `is_paused` —
tutte le sue campagne non archiviate si archiviano nella stessa transazione. «Riattiva» e «Avvia» non le ripristinano:
lo fa il founder a mano. Inoltre le campagne di un negozio non attivo (in attesa o in pausa) non rispondono mai.

## Alternative scartate
- Lasciare le campagne vive e bloccare solo «Applica»: clienti con un coupon inutilizzabile.
- Uno stato «in pausa» della campagna: basta archiviare e ripristinare.

## Conseguenze
- Dopo una riattivazione il founder ripristina le campagne che servono (il ripristino ricontrolla l'unicità della
  parola chiave).
- La regola sta nel service, così vale per ogni strada che mette in pausa.
