from app.models.models import Merchant, TreeCard
from pydantic import ValidationError

#############################
# TEST MODELS
#############################

def test_merchant_valid():
    # Merchant corretto - Usiamo model_validate per forzare la validazione Pydantic
    data = {
        "business_name": 'test services',
        "phone_number": '+391234567890',
        "password": 'CiaoProviamoPassword',
        "humami_api_key": "humamina",
        "humami_enterprise_id": "enterprise",
        "points_to_tree": 7,
        "cb_points_per_tree": 3,
        "type": 'pro'
    }
    test_merchant = Merchant.model_validate(data)
    assert test_merchant.business_name == 'test services'
    assert test_merchant.type == 'pro'
    print("Test merchant_valid passato")

def test_merchant_invalid_phone():
    # Telefono senza +39
    data = {
        "business_name": 'test phone',
        "phone_number": '1234567890',
        "password": 'pass',
        "humami_api_key": "key",
        "humami_enterprise_id": "id"
    }
    try:
        Merchant.model_validate(data)
        assert False, "Dovrebbe sollevare ValidationError per phone_number"
    except ValidationError as e:
        print(f"Test invalid_phone passato: {e.errors()[0]['msg']}")

def test_merchant_invalid_type():
    # Tipo non valido
    data = {
        "business_name": 'test type',
        "phone_number": '+391234567890',
        "password": 'pass',
        "humami_api_key": "key",
        "humami_enterprise_id": "id",
        "type": 'invalid_type'
    }
    try:
        Merchant.model_validate(data)
        assert False, "Dovrebbe sollevare ValidationError per type"
    except ValidationError as e:
        print(f"Test invalid_type passato: {e.errors()[0]['msg']}")

def test_tree_card_defaults():
    card = TreeCard(merchant_id=1)
    assert card.current_points == 0
    assert card.cashback_point == 0
    assert card.trees_planted == 0
    print("Test tree_card_defaults passato")


##########################
# TEST SERVICES (NEON DB)
##########################
from app.services.db_crud import merchant_crud, card_crud
from sqlmodel import Session
from app.main import engine

def test_merchant_crud_lifecycle():
    merchant_id = None
    try:
        with Session(engine) as session:
            # Create
            data = {
                "business_name": "CRUD Test Neon",
                "phone_number": "+390000000001",
                "password": "testpassword",
                "humami_api_key": "test_key",
                "humami_enterprise_id": "test_id",
                "type": "pro"
            }
            merchant = merchant_crud.create_merchant(session, data)
            merchant_id = merchant.id
            assert merchant.id is not None
            assert merchant.business_name == "CRUD Test Neon"
            
            # Read
            fetched = merchant_crud.get_merchant_by_id(session, merchant.id)
            assert fetched.id == merchant.id
            
            # Update
            updated = merchant_crud.update_merchant(session, fetched, {"business_name": "Updated Neon"})
            assert updated.business_name == "Updated Neon"
    finally:
        # Cleanup finale obbligatorio
        if merchant_id:
            with Session(engine) as session:
                merchant_crud.delete_merchant(session, merchant_id)
                assert merchant_crud.get_merchant_by_id(session, merchant_id) is None
    print("Test merchant_crud_lifecycle (Neon) passato e pulito")

def test_card_crud_lifecycle():
    merchant_id = None
    card_id = None
    try:
        with Session(engine) as session:
            # Serve un merchant per creare una carta
            m_data = {
                "business_name": "Card Test Neon",
                "phone_number": "+391111111112",
                "password": "p",
                "humami_api_key": "k",
                "humami_enterprise_id": "i"
            }
            merchant = merchant_crud.create_merchant(session, m_data)
            merchant_id = merchant.id
            
            # Create Card
            card = card_crud.create_card(session, merchant.id)
            card_id = card.id
            assert card.id is not None
            assert card.merchant_id == merchant.id
            
            # Update points
            updated_card = card_crud.update_card_points(session, card, 10)
            assert updated_card.current_points == 10
            
            # Read
            fetched = card_crud.get_card_by_id(session, card.id)
            assert fetched.id == card.id
    finally:
        # Cleanup - Elimina card e poi merchant
        with Session(engine) as session:
            if card_id:
                card_crud.delete_card(session, card_id)
                assert card_crud.get_card_by_id(session, card_id) is None
            if merchant_id:
                merchant_crud.delete_merchant(session, merchant_id)
                assert merchant_crud.get_merchant_by_id(session, merchant_id) is None
    print("Test card_crud_lifecycle (Neon) passato e pulito")


if __name__ == "__main__":
    try:
        test_merchant_valid()
        test_merchant_invalid_phone()
        test_merchant_invalid_type()
        test_tree_card_defaults()
        test_merchant_crud_lifecycle()
        test_card_crud_lifecycle()
        print("\nTutti i test completati con successo!")
    except AssertionError as e:
        print(f"\nERRORE DI ASSERZIONE: {e}")
        exit(1)
    except Exception as e:
        print(f"\nERRORE INASPETTATO: {e}")
        exit(1)
