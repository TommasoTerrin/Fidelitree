# app/routes/consumer/api.py
# CONSUMER BUSINESS CALLS — Restituisce JSON / Redirect

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.core.dependencies import get_session
from app.models.models import TreeCard

router = APIRouter(tags=["Consumer API"])


# 1. CREAZIONE DI UNA NUOVA TREECARD (redirect alla visualizzazione)
@router.post("/get-card")
async def create_new_card(request: Request, session: Session = Depends(get_session)):
    """Crea una nuova TreeCard (per ora associata al merchant 1 di test)."""
    new_card = TreeCard(merchant_id=1)
    session.add(new_card)
    session.commit()
    session.refresh(new_card)

    return RedirectResponse(url=f"/card/{new_card.id}", status_code=303)
