# 0004 — «Applica» nello scanner

- **Stato**: accettata
- **Data**: 2026-11-12
- **Versione**: v0.4.1 (spec: `.agents/tickets/v0.4.1/README.md`, decisione 11, default D1, D8 sostituito, D12)
- **Area**: `carta-e-scanner.md`

## Contesto
Il coupon è il DM: in cassa il merchant deve accreditare la promo sulla carta del cliente e la campagna deve contare
quante volte è stata usata in negozio. Oggi la gestione della carta aggiunge e toglie tree points e cashback.

## Decisione
- Dopo lo scan del QR della carta, la gestione della carta mostra le campagne **non archiviate** del negozio con
  «Applica <nome> (+X €)» o «Applica <nome>» (importo 0).
- «Applica» apre una conferma sì/no; al «sì», in **una** transazione con `UPDATE` atomici: cashback della carta +
  importo attuale e utilizzi della campagna +1. Due conferme = due utilizzi.
- Stesso blocco di oggi per le aggiunte di cashback (`check_balance_change`: 403 per importo > 0 con negozio in attesa
  o in pausa). Un negozio in pausa non ha campagne non archiviate (0003).
- Confermato funziona anche se la campagna è stata archiviata dopo il caricamento della pagina.
- Tree points, pool, conversione, `PointTransaction` e pagina carta del cliente non cambiano.

## Alternative scartate
- Annullare un utilizzo: il cashback si toglie con il pulsante di oggi; il contatore resta.
- Ricontrollare l'archiviazione alla conferma: controllo in più senza valore per il pilota.
- Colonna «cashback erogato»: si calcola da importo × utilizzi.

## Conseguenze
- Un «Applica» per errore corretto togliendo il cashback lascia il contatore degli utilizzi gonfiato: accettato.
