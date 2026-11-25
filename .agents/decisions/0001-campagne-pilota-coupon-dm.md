# 0001 — Campagne pilota: il coupon è il DM

- **Stato**: accettata
- **Data**: 2026-11-12
- **Versione**: v0.4.1 (spec: `.agents/tickets/v0.4.1/README.md`, decisioni 1-4, 6-12, default D1, D3, D10-D13, D15)
- **Area**: `campagne.md`

## Contesto
Per partire con i primi pilota serve una funzione spettacolare e leggera. La v0.4.0 delle campagne (adesioni salvate
nella carta, pagina `/p/<token>`, secondo QR, più promozioni, limiti per cliente, date in ora di Roma) è risultata
troppo pesante in logica e DB ed è archiviata sul branch `feature/campagne`.

## Decisione
- Una **campagna** = negozio, nome, parola chiave, testo della promo, importo di cashback (0 = nessun importo), limite
  di richieste facoltativo, archiviata sì/no, contatori (richieste da DM, richieste da commento, utilizzi). Nessuna
  data: la validità la scrive il founder nel testo. Una sola tabella nuova, nessuna modifica alle tabelle o agli enum
  esistenti.
- La crea, modifica, archivia, ripristina ed elimina **solo il founder** da `/admin`.
- **Attiva** = non archiviata e negozio attivo. Parola chiave: una parola senza spazi, diversa da `CARTA`, unica tra
  le campagne non archiviate del negozio.
- Chi scrive la parola chiave (corrispondenza esatta dopo la normalizzazione) riceve **un DM di testo**: promo + riga
  fissa che invita a scrivere `CARTA`. **Quel DM è il coupon**: nessuna promo salvata nella carta, nessun limite per
  cliente, decide il merchant in cassa. Oltre il limite di richieste: testo «offerte terminate».
- Nello scanner, «Applica» confermato accredita l'importo e conta un utilizzo (vedi 0004).

## Alternative scartate
- Adesioni nella carta, pagina `/p/` e QR della promo (v0.4.0): troppa logica e DB per un pilota.
- Più promozioni per campagna: una campagna = una promo.
- Date di inizio e fine: rimandate; nel pilota il founder archivia a mano.

## Conseguenze
- Uno screenshot del DM si può girare: accettato (passaparola).
- Il cashback dato da una campagna non ha un registro: si ricava da importo × utilizzi.
- In roadmap: date, campagne create dal merchant (con limiti più stretti), promo nella carta e limite per cliente,
  «porta un amico», dati per cliente.
