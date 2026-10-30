"""
Core puro dello stato del servizio (ticket 12): stato derivato da `is_approved` e `is_paused` e permessi di
aggiunta/rimozione del saldo. Nessun DB, nessun mock.
"""

import pytest

from app.core.enums import ServiceState
from app.core.errors import ForbiddenError
from app.services.card_service import can_add_balance, can_remove_balance, check_balance_change, service_state


@pytest.mark.parametrize("is_approved, is_paused, expected", [
    (False, False, ServiceState.PENDING),
    (False, True, ServiceState.PENDING),   # la pausa non conta se non è approvato
    (True, False, ServiceState.ACTIVE),
    (True, True, ServiceState.PAUSED),
])
def test_service_state_per_le_4_combinazioni(is_approved, is_paused, expected):
    assert service_state(is_approved, is_paused) is expected


@pytest.mark.parametrize("state, can_add", [
    (ServiceState.PENDING, False),
    (ServiceState.ACTIVE, True),
    (ServiceState.PAUSED, False),
])
def test_si_aggiunge_solo_se_attivo_e_si_toglie_sempre(state, can_add):
    assert can_add_balance(state) is can_add
    assert can_remove_balance(state) is True


@pytest.mark.parametrize("state", list(ServiceState))
@pytest.mark.parametrize("delta", [-50, -1, 0])
def test_togliere_e_delta_zero_sono_ammessi_in_ogni_stato(state, delta):
    check_balance_change(state, delta)  # non solleva


def test_aggiungere_se_attivo_e_ammesso():
    check_balance_change(ServiceState.ACTIVE, 1)
    check_balance_change(ServiceState.ACTIVE, 500)


def test_aggiungere_in_attesa_solleva_con_messaggio_chiaro():
    with pytest.raises(ForbiddenError) as error:
        check_balance_change(ServiceState.PENDING, 1)
    assert str(error.value) == "In attesa di approvazione: non puoi aggiungere punti"


def test_aggiungere_in_pausa_solleva_con_messaggio_chiaro():
    with pytest.raises(ForbiddenError) as error:
        check_balance_change(ServiceState.PAUSED, 25)
    assert str(error.value) == "Servizio in pausa: puoi solo togliere il saldo esistente"
