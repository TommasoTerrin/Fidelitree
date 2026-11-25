# 0002 — Commenti Instagram: risposta privata di solo testo

- **Stato**: accettata
- **Data**: 2026-11-12
- **Versione**: v0.4.1 (spec: `.agents/tickets/v0.4.1/README.md`, decisioni 5, 6, 9, 10, 13, default D2, D4-D7, D9)
- **Area**: `carta-instagram.md`

## Contesto
Fino a v0.3.0 l'unico trigger è il DM `CARTA` (o la voce di menu); commenti e storie erano fuori scope. Le campagne
vivono di commenti sotto i post. Meta permette **una sola risposta privata per commento**, entro 7 giorni, e la
risposta privata di Zernio accetta **solo testo** (bottoni e card possono essere rifiutati a chi non segue, e il
rifiuto consuma l'unica risposta).

## Decisione
- Il webhook del negozio sottoscrive `message.received` e **`comment.received`**. Le risposte alle storie arrivano
  come DM e seguono il riconoscimento dei DM.
- Commento uguale (dopo la normalizzazione) alla parola di una campagna attiva → una risposta privata con il testo
  della campagna. Commento uguale a `CARTA` → risposta privata «Per ricevere la tua carta scrivici CARTA qui in chat»,
  in ogni stato del negozio; la card arriva poi dal flusso DM di oggi (solo a chi segue). Mai risposte pubbliche.
- I commenti dell'account del negozio non hanno un filtro: valgono come gli altri.
- Una risposta privata conta nella quota Zernio come un DM. Nessun nuovo tentativo sugli invii. Esiti con le etichette
  esistenti di `WebhookOutcome`; dettagli (campagna, canale) solo nei log, senza testo né id del cliente.
- I negozi già collegati (solo i profili del founder) si aggiornano con «Scollega» e un nuovo collegamento.

## Alternative scartate
- «Comment automations» di Zernio: due fonti di verità (in `fuori-scope.md`).
- Card inviata direttamente dal commento: non consentita dalla risposta privata di solo testo (roadmap).
- Script per cambiare gli eventi dei webhook già collegati (`PUT /v1/webhooks/settings`): inutile con i soli profili
  del founder (roadmap).

## Conseguenze
- Non verificato prima del codice (collaudo alla fine, decisione del founder): `comment.received` con l'account
  Zernio gratuito, campi del payload, consegna a chi non segue, quota. **Piano B**: ramo dei commenti spento e
  `WEBHOOK_EVENTS` di nuovo solo `message.received` (altrimenti un rifiuto della sottoscrizione farebbe fallire
  l'intero collegamento Instagram).
- Un commento con altre parole oltre alla parola chiave non riceve niente (corrispondenza esatta, scelta per il
  pilota).
