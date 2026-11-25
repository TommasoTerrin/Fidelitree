-- v0.4.1: crea la tabella delle campagne dei negozi e l'indice sul negozio.
-- Si applica a mano su Neon: prima sul branch development, poi su production
-- dopo il branch di backup (procedura in deploy.md).
-- E' idempotente: si puo' rieseguire senza errori e senza toccare i dati esistenti.

CREATE TABLE IF NOT EXISTS campaign (
	id SERIAL NOT NULL,
	merchant_id INTEGER NOT NULL,
	name VARCHAR(40) NOT NULL,
	keyword VARCHAR(30) NOT NULL,
	promo_text VARCHAR(850) NOT NULL,
	value_cents INTEGER NOT NULL,
	request_limit INTEGER,
	is_archived BOOLEAN NOT NULL,
	dm_requests INTEGER NOT NULL,
	comment_requests INTEGER NOT NULL,
	uses INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(merchant_id) REFERENCES merchant (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_campaign_merchant_id ON campaign (merchant_id);
