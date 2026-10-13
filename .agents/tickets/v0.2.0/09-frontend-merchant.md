# 09 — Frontend merchant

## Obiettivo
Adeguare le pagine del merchant al nuovo modello, **mantenendo lo stile attuale** (Tailwind via CDN, card arrotondate `rounded-[2.5rem]`, modal di conferma, toast, palette verde/blu).

## Contesto
Template esistenti: `merchant/login_merchant.html`, `register_merchant.html`, `settings.html`, `qr_scanner.html`, `update_card.html`. `update_card.html` mostra `tree_points/tree_threshold`, `trees_planted`, sezione cashback condizionata a `merchant.mode`. Leggi ciascun template prima di modificarlo e riusa i suoi componenti (modal, toast, `submitPending`).

## Dipendenze
04, 07.

## Modifiche
1. **`login_merchant.html`**: campo **email** al posto del telefono; messaggio chiaro per account non approvato non necessario (può lavorare).
2. **`register_merchant.html`**: campi nome attività, email, password (≥8), telefono di contatto **facoltativo** (+39); **rimuovi** il campo chiave Ecologi e il testo che la spiega; aggiungi nota: *"Il tuo account sarà attivato per la piantumazione dopo l'approvazione. Puoi iniziare subito a usare le carte."*
3. **`settings.html`**: sostituisci soglia/cap/chiave Ecologi con: interruttore **conversione tree points → cashback**, **soglia** (punti) e **valore** (€), con anteprima testuale ("Ogni 50 tree points → € 2,00 di cashback"); mostra a sola lettura le soglie effettive del negozio (bronzo/argento/oro) e lo stato "In attesa di approvazione"/"Approvato"; sezione **QR del negozio** (generato client-side con qrcodejs, stesso stile della carta cliente) che codifica `{origin}/join/{merchant.id}`, con pulsante per scaricarlo/stamparlo.
4. **`update_card.html`** (gestione carta dopo lo scan):
   - riga stato: saldo tree points della carta (senza `/soglia`), cashback sempre visibile;
   - blocco **"Pool del negozio"**: livello attuale (🥉/🥈/🥇 o "nessun livello"), punti del mese, barra di avanzamento verso il livello successivo (dati da `pool` del context); testo *"Questo mese il negozio sta piantando N alberi"*;
   - sezione tree points: testo "Ogni {soglia} punti → € {valore} di cashback" solo se la conversione è attiva;
   - **sezione cashback sempre presente** (non più condizionata a `mode`);
   - dopo l'aggiunta di tree points: se `converted` è valorizzato mostra toast `💶 Convertiti X punti in € Y di cashback`, altrimenti toast standard; rimuovi il toast "Piantato albero"/`warning`.
5. **`qr_scanner.html`**: nessuna modifica funzionale; verifica che la trasformazione `/card/` → `/merchant/card/.../manage` funzioni con il nuovo URL.
6. **Route/views** (`app/routes/merchant/views.py`): passano ai template i dati necessari (`pool` = `PoolProgress` del mese corrente, soglie effettive, QR URL) calcolati tramite i service, **senza logica nelle route**.

## File coinvolti
`app/templates/merchant/*.html`, `app/routes/merchant/views.py`, `tests/test_views.py`.

## Test da superare (render server-side, `TestClient`)
- `GET /merchant/login` e `/register` → 200; **non** contengono "Ecologi" né il campo telefono obbligatorio; la registrazione contiene il campo email.
- `GET /merchant/settings` autenticato → 200; contiene l'interruttore conversione, il valore della soglia, le soglie livello effettive (con un override impostato i numeri cambiano) e l'URL `…/join/{id}` del QR; non contiene "monthly"/"cap"/"chiave".
- `GET /merchant/card/{id}/manage`: contiene il livello del pool e i punti del mese (con movimenti preparati nel DB), contiene la sezione cashback **anche** con conversione disattivata, non contiene `trees_planted`/"alberi piantati" per la carta.
- Con conversione disattivata la pagina non mostra il testo "Ogni N punti → cashback".
- Carta di un altro merchant → 404 (invariato); non autenticato → 401 (invariato).
- Verifica manuale con `python local_main.py` (checklist nel ticket 11): registrazione, login, impostazioni, scan e aggiunta punti con toast di conversione.

## Fuori scope
Dashboard merchant con elenco carte, redirect intelligente per non autenticati (roadmap).

## Definition of Done
Test verdi, suite verde, stile coerente con le pagine esistenti (stessi componenti Tailwind), nessun riferimento residuo a `mode`, `ecologi`, `tree_threshold` nei template.
