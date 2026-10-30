"""
Logica di business del pool alberi: livelli, avanzamento, periodi e piano di chiusura.

Regole di business
------------------
- Ogni negozio ha un **pool mensile** di punti: la somma dei tree points assegnati
  dai suoi scan nel mese (UTC). Il pool riparte da zero a ogni mese.
- Il **livello** dipende dai punti del pool: bronzo / argento / oro, con soglie
  strettamente crescenti (default da config, override per negozio).
- Gli alberi piantati a fine mese dipendono dal solo livello raggiunto e **non sono
  cumulativi**: bronzo = 1, argento = 3, oro = 5 alberi totali (non 1+3+5).
- Il mese di un movimento è fissato in scrittura come `period` 'YYYY-MM' (mese UTC).
- La chiusura del periodo produce un **piano**; se il totale degli alberi supera il
  cap globale mensile il piano lo **segnala** (`exceeds_cap`, `excess`) ma non ripartisce
  né taglia: la decisione resta al founder.

Questo modulo contiene per ora solo il **core puro**: usa solo Pydantic e stdlib, nessun
accesso a DB, rete o orologio, e solleva errori di dominio (mai `HTTPException`).
La sezione `# --- Shell ---` in fondo legge il pool dal DB e chiude il periodo piantando
gli alberi su Ecologi con la chiave di piattaforma (`close_period`).
"""

from datetime import date, datetime, timezone

from pydantic import BaseModel, model_validator

from app.core.enums import Level
from app.core.errors import InvalidInputError, InvalidThresholdsError

# --- Core puro ---

TREES_PER_LEVEL: dict[Level, int] = {
    Level.NONE: 0,
    Level.BRONZE: 1,
    Level.SILVER: 3,
    Level.GOLD: 5,
}


class LevelThresholds(BaseModel):
    """Soglie di punti per i tre livelli: devono essere ≥ 1 e strettamente crescenti."""

    bronze: int
    silver: int
    gold: int

    @model_validator(mode="after")
    def _check_coherence(self) -> "LevelThresholds":
        """Solleva `InvalidThresholdsError` se le soglie non sono ≥ 1 e crescenti."""
        if not (1 <= self.bronze < self.silver < self.gold):
            raise InvalidThresholdsError(
                "Le soglie devono essere ≥ 1 e crescenti: bronzo < argento < oro "
                f"(ricevute {self.bronze}/{self.silver}/{self.gold})"
            )
        return self


def resolve_thresholds(
    defaults: LevelThresholds,
    bronze: int | None = None,
    silver: int | None = None,
    gold: int | None = None,
) -> LevelThresholds:
    """Applica gli override per singolo livello ai default e rivalida la coerenza finale."""
    return LevelThresholds(
        bronze=defaults.bronze if bronze is None else bronze,
        silver=defaults.silver if silver is None else silver,
        gold=defaults.gold if gold is None else gold,
    )


def compute_level(points: int, thresholds: LevelThresholds) -> Level:
    """Livello raggiunto con `points` punti; zero o negativi significano nessun livello."""
    if points >= thresholds.gold:
        return Level.GOLD
    if points >= thresholds.silver:
        return Level.SILVER
    if points >= thresholds.bronze:
        return Level.BRONZE
    return Level.NONE


def trees_for_level(level: Level) -> int:
    """Alberi totali (non cumulativi) previsti per il livello."""
    return TREES_PER_LEVEL[level]


class PoolProgress(BaseModel):
    """Stato del pool e avanzamento verso il livello successivo."""

    points: int
    level: Level
    trees_at_month_end: int
    next_level: Level | None
    points_to_next: int | None
    percent_to_next: int  # 0..100; 100 se già oro


def compute_pool_progress(points: int, thresholds: LevelThresholds) -> PoolProgress:
    """
    Livello attuale, alberi a fine mese e avanzamento verso il livello successivo.
    La percentuale misura il tratto tra la soglia del livello attuale (0 se nessuno)
    e quella del successivo, arrotondata per difetto. Punti negativi valgono 0.
    """
    points = max(points, 0)
    level = compute_level(points, thresholds)
    floors = {
        Level.NONE: 0,
        Level.BRONZE: thresholds.bronze,
        Level.SILVER: thresholds.silver,
        Level.GOLD: thresholds.gold,
    }
    successors = {
        Level.NONE: Level.BRONZE,
        Level.BRONZE: Level.SILVER,
        Level.SILVER: Level.GOLD,
        Level.GOLD: None,
    }
    next_level = successors[level]
    if next_level is None:
        points_to_next, percent = None, 100
    else:
        floor, ceiling = floors[level], floors[next_level]
        points_to_next = ceiling - points
        percent = (points - floor) * 100 // (ceiling - floor)
    return PoolProgress(
        points=points,
        level=level,
        trees_at_month_end=trees_for_level(level),
        next_level=next_level,
        points_to_next=points_to_next,
        percent_to_next=percent,
    )


def period_label(year: int, month: int) -> str:
    """Etichetta 'YYYY-MM' di un periodo."""
    return f"{year:04d}-{month:02d}"


def period_for(moment: datetime) -> str:
    """Periodo 'YYYY-MM' del mese UTC a cui appartiene l'istante; `ValueError` se naive."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("L'istante deve avere un fuso orario (datetime aware)")
    utc = moment.astimezone(timezone.utc)
    return period_label(utc.year, utc.month)


def previous_period(today: date) -> tuple[int, int]:
    """(anno, mese) del mese precedente a quello di `today`."""
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


_MONTHS_IT = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)
_DEFAULT_PLANTING_NAME = "Negozio Fidelitree"
_MAX_PLANTING_NAME_LEN = 60  # la doc Ecologi non dà un limite: scelta prudente


def planting_name(business_name: str, period: str) -> str:
    """
    Etichetta della tessera sulla foresta Ecologi: "Bar Demo · ottobre 2026".
    Il nome del negozio ha spazi normalizzati, è troncato a 60 caratteri e, se vuoto,
    diventa "Negozio Fidelitree". `InvalidInputError` se `period` non è 'YYYY-MM' valido.
    """
    try:
        year_text, month_text = period.split("-")
        year, month = int(year_text), int(month_text)
        valid = len(year_text) == 4 and len(month_text) == 2 and 1 <= month <= 12
    except ValueError:
        valid = False
    if not valid:
        raise InvalidInputError(f"Periodo non valido: {period!r} (atteso AAAA-MM)")
    name = " ".join(business_name.split())[:_MAX_PLANTING_NAME_LEN].rstrip() or _DEFAULT_PLANTING_NAME
    return f"{name} · {_MONTHS_IT[month - 1]} {year}"


class PoolInput(BaseModel):
    """Pool di un negozio in ingresso al piano di chiusura (non è la tabella `MerchantPool`)."""

    merchant_id: int
    business_name: str
    points: int
    thresholds: LevelThresholds


class ClosureLine(BaseModel):
    """Riga del piano: quanti alberi spettano a un negozio per il periodo."""

    merchant_id: int
    business_name: str
    points: int
    level: Level
    trees: int


class ClosurePlan(BaseModel):
    """Piano di chiusura di un periodo, con il controllo sul cap globale degli alberi."""

    period: str
    lines: list[ClosureLine]
    total_trees: int
    global_cap: int
    exceeds_cap: bool
    excess: int


def plan_period_closure(
    period: str,
    pools: list[PoolInput],
    already_closed: set[int],
    global_cap: int,
) -> ClosurePlan:
    """
    Costruisce il piano di chiusura: esclude i negozi già chiusi, calcola livello e alberi
    di ciascun pool, ordina le righe per `merchant_id` e confronta il totale col cap globale.
    Se il cap è sforato lo segnala (`excess` = alberi oltre il cap) senza modificare le righe.
    """
    lines = []
    for pool in sorted(pools, key=lambda p: p.merchant_id):
        if pool.merchant_id in already_closed:
            continue
        level = compute_level(pool.points, pool.thresholds)
        lines.append(ClosureLine(
            merchant_id=pool.merchant_id,
            business_name=pool.business_name,
            points=pool.points,
            level=level,
            trees=trees_for_level(level),
        ))
    total = sum(line.trees for line in lines)
    return ClosurePlan(
        period=period,
        lines=lines,
        total_trees=total,
        global_cap=global_cap,
        exceeds_cap=total > global_cap,
        excess=max(0, total - global_cap),
    )


# --- Shell ---

import logging  # noqa: E402
from typing import Callable, Literal, Optional  # noqa: E402

from sqlalchemy import func  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.enums import PointTransactionKind  # noqa: E402
from app.models.models import (  # noqa: E402
    Merchant, MerchantPool, PointTransaction, TreePlanting,
)
from app.services import ecologi_service  # noqa: E402

logger = logging.getLogger(__name__)


def pool_points(session: Session, merchant_id: int, period: str) -> int:
    """Punti del pool di un negozio per un periodo: legge il contatore, 0 se la riga manca."""
    pool = session.get(MerchantPool, (merchant_id, period))
    return pool.points if pool else 0


def pool_points_by_merchant(session: Session, merchant_ids: list[int], period: str) -> dict[int, int]:
    """Punti del pool di un periodo per più negozi con una sola query (chi non ha la riga manca dal dizionario)."""
    if not merchant_ids:
        return {}
    rows = session.exec(
        select(MerchantPool.merchant_id, MerchantPool.points)
        .where(MerchantPool.merchant_id.in_(merchant_ids), MerchantPool.period == period)
    ).all()
    return {merchant_id: points for merchant_id, points in rows}


def current_pool_progress(session: Session, merchant: Merchant, now: datetime) -> PoolProgress:
    """Avanzamento del pool del mese di `now`, con le soglie effettive del negozio."""
    points = pool_points(session, merchant.id, period_for(now))
    return compute_pool_progress(points, effective_thresholds(merchant))


def _default_thresholds() -> LevelThresholds:
    """Soglie di default di piattaforma lette dalla config."""
    return LevelThresholds(
        bronze=settings.TIER_BRONZE_POINTS,
        silver=settings.TIER_SILVER_POINTS,
        gold=settings.TIER_GOLD_POINTS,
    )


def effective_thresholds(
    merchant: Merchant,
    overrides: Optional[dict] = None,
) -> LevelThresholds:
    """
    Soglie effettive di un negozio: default di piattaforma + override del negozio.
    `overrides` (chiavi `bronze_threshold`/`silver_threshold`/`gold_threshold`) sostituisce
    quelli salvati sul merchant: serve a validare una modifica PRIMA di salvarla.
    Solleva `InvalidThresholdsError` se il risultato è incoerente.
    """
    values = {
        "bronze_threshold": merchant.bronze_threshold,
        "silver_threshold": merchant.silver_threshold,
        "gold_threshold": merchant.gold_threshold,
        **(overrides or {}),
    }
    return resolve_thresholds(
        _default_thresholds(),
        values["bronze_threshold"], values["silver_threshold"], values["gold_threshold"],
    )


def build_pools(session: Session, period: str) -> list[PoolInput]:
    """
    Pool del periodo dei soli negozi approvati, con le soglie effettive (default + override).
    I punti si leggono dal contatore (0 se la riga manca): nessuna `SUM` sul registro.
    """
    defaults = _default_thresholds()
    merchants = session.exec(select(Merchant).where(Merchant.is_approved == True)).all()  # noqa: E712
    return [
        PoolInput(
            merchant_id=m.id,
            business_name=m.business_name,
            points=pool_points(session, m.id, period),
            thresholds=resolve_thresholds(
                defaults, m.bronze_threshold, m.silver_threshold, m.gold_threshold
            ),
        )
        for m in merchants
    ]


def closed_merchant_ids(session: Session, period: str, test: bool) -> set[int]:
    """Negozi già chiusi per `(period, test)`: una prova non esclude la chiusura vera e viceversa."""
    rows = session.exec(
        select(TreePlanting.merchant_id).where(
            TreePlanting.period == period, TreePlanting.test == test
        )
    ).all()
    return set(rows)


class PoolMismatch(BaseModel):
    """Divergenza tra contatore del pool e registro dei movimenti per un negozio."""

    merchant_id: int
    counter: int
    ledger: int


def pool_mismatches(session: Session, period: str) -> list[PoolMismatch]:
    """
    Confronta `MerchantPool.points` con `SUM(delta)` dei movimenti `scan` del periodo, per i
    negozi approvati. Il registro è la fonte di verità: ogni differenza è una deviazione.
    """
    approved = session.exec(select(Merchant.id).where(Merchant.is_approved == True)).all()  # noqa: E712
    counters = dict(session.exec(
        select(MerchantPool.merchant_id, MerchantPool.points).where(MerchantPool.period == period)
    ).all())
    ledgers = dict(session.exec(
        select(PointTransaction.merchant_id, func.sum(PointTransaction.delta))
        .where(
            PointTransaction.period == period,
            PointTransaction.kind == PointTransactionKind.SCAN,
        )
        .group_by(PointTransaction.merchant_id)
    ).all())
    mismatches = []
    for merchant_id in sorted(approved):
        counter, ledger = counters.get(merchant_id, 0), int(ledgers.get(merchant_id, 0) or 0)
        if counter != ledger:
            mismatches.append(PoolMismatch(merchant_id=merchant_id, counter=counter, ledger=ledger))
    return mismatches


def build_closure_plan(session: Session, period: str, global_cap: int) -> ClosurePlan:
    """Piano di chiusura del periodo (esclude i negozi già chiusi nella modalità corrente)."""
    return plan_period_closure(
        period,
        build_pools(session, period),
        closed_merchant_ids(session, period, settings.ECOLOGI_TEST_MODE),
        global_cap,
    )


class ClosureEntry(BaseModel):
    """Esito della chiusura per un negozio."""

    merchant_id: int
    business_name: str
    status: Literal["planted", "failed", "skipped"]
    level: Optional[Level] = None
    trees: int = 0
    pool_points: int = 0
    ecologi_ref: Optional[str] = None
    detail: Optional[str] = None  # motivo di failed/skipped


class ClosureReport(BaseModel):
    """Esito di `close_period`: righe per negozio, divergenze e motivo dell'eventuale blocco."""

    period: str
    test: bool
    blocked_by: Optional[Literal["mismatch", "cap"]] = None
    mismatches: list[PoolMismatch] = []
    plan: Optional[ClosurePlan] = None
    entries: list[ClosureEntry] = []


def idempotency_key(merchant_id: int, period: str, test: bool) -> str:
    """Chiave di idempotenza deterministica; distinta per le prove così non occupa quella vera."""
    prefix = "fidelitree-test" if test else "fidelitree"
    return f"{prefix}-{merchant_id}-{period}"


async def close_period(
    session: Session,
    period: str,
    *,
    global_cap: int,
    confirm: Callable[[ClosurePlan], bool],
    now: datetime,
) -> ClosureReport:
    """
    Pianta su Ecologi gli alberi del periodo e registra una `TreePlanting` per negozio.

    - Se contatore e registro divergono non pianta nulla (si spendono soldi veri).
    - Se il piano supera il cap e `confirm(plan)` non lo autorizza non pianta nulla.
    - Una riga viene scritta (commit per riga) solo a piantumazione riuscita, con lo snapshot
      dei punti; un errore Ecologi su un negozio lo segna `failed` e si prosegue con gli altri.
    - Idempotente: i negozi già chiusi nella stessa modalità (prova/vera) risultano `skipped`.
    """
    test = settings.ECOLOGI_TEST_MODE
    mismatches = pool_mismatches(session, period)
    if mismatches:
        return ClosureReport(period=period, test=test, blocked_by="mismatch", mismatches=mismatches)

    closed = closed_merchant_ids(session, period, test)
    plan = plan_period_closure(period, build_pools(session, period), closed, global_cap)
    if plan.exceeds_cap and not confirm(plan):
        return ClosureReport(period=period, test=test, blocked_by="cap", plan=plan)

    entries: list[ClosureEntry] = []
    for pool in build_pools(session, period):
        if pool.merchant_id in closed:
            entries.append(ClosureEntry(
                merchant_id=pool.merchant_id, business_name=pool.business_name,
                status="skipped", detail="già chiuso",
            ))
    for line in plan.lines:
        base = dict(
            merchant_id=line.merchant_id, business_name=line.business_name,
            level=line.level, trees=line.trees, pool_points=line.points,
        )
        if line.trees == 0:
            entries.append(ClosureEntry(**base, status="skipped", detail="sotto la soglia bronzo"))
            continue
        try:
            response = await ecologi_service.purchase_trees(
                line.trees,
                name=planting_name(line.business_name, period),
                idempotency_key=idempotency_key(line.merchant_id, period, test),
            )
            ref = ecologi_service.extract_ref(response)
        except ecologi_service.EcologiError as e:
            logger.error("Chiusura %s negozio %d fallita: %s", period, line.merchant_id, e)
            entries.append(ClosureEntry(**base, status="failed", detail=str(e)))
            continue
        try:
            session.add(TreePlanting(
                merchant_id=line.merchant_id, period=period, level=line.level,
                tree_count=line.trees, pool_points=line.points,
                ecologi_ref=ref, test=test, created_at=now,
            ))
            session.commit()
        except Exception as e:
            # alberi piantati ma riga non salvata: va segnalato con forza (la riesecuzione è sicura
            # grazie all'idempotency key, ma serve un intervento)
            session.rollback()
            logger.critical("Piantati %d alberi (%s, negozio %d) ma riga non salvata: %s",
                            line.trees, period, line.merchant_id, e)
            entries.append(ClosureEntry(**base, status="failed", ecologi_ref=ref,
                                        detail=f"piantati ma non registrati: {e}"))
            continue
        entries.append(ClosureEntry(**base, status="planted", ecologi_ref=ref))
    return ClosureReport(period=period, test=test, plan=plan, entries=entries)
