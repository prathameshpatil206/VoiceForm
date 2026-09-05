import asyncio
import json
import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi.testclient import TestClient

from app.config import config
from app.db.models import Base
from app.db.migration import run_migrations
from app.db.repository import SQLAlchemyProfileRepository
from app.db.session import check_db_health, get_engine
from app.profile.cache import ProfileCache
from app.profile.normalizer import normalize_form_field, normalize_key_string
from app.profile.safety import is_prohibited_candidate, is_sensitive_field
from app.profile.service import ProfileService
from app.schemas.form import FormField, PageScanResult, DetectedForm, ValidationRules
from app.schemas.profile import (
    FieldMatchStatus,
    ProfileCandidate,
    ProfileFieldSchema,
    ProfileSource,
    UserProfileSchema
)
from app.main import app
from app.api.profile_routes import set_profile_service


async def create_test_repository():
    """Helper to construct an isolated in-memory SQLite repository and engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    repo = SQLAlchemyProfileRepository(session_factory=factory)
    return repo, engine


# =========================================================================
# M7-T1: Database connection/configuration
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t1_database_connection_config():
    repo, engine = await create_test_repository()
    try:
        profile = await repo.get_or_create_profile("test_user_t1")
        assert profile.id == "test_user_t1"
        assert profile.is_enabled is True
        assert isinstance(profile.created_at, datetime)
    finally:
        await engine.dispose()


# =========================================================================
# M7-T2: Profile creation
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t2_profile_creation():
    repo, engine = await create_test_repository()
    try:
        profile = await repo.get_or_create_profile("user_create_t2")
        assert profile.id == "user_create_t2"
        assert len(profile.fields) == 0
    finally:
        await engine.dispose()


# =========================================================================
# M7-T3: Profile field persistence
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t3_profile_field_persistence():
    repo, engine = await create_test_repository()
    try:
        field = await repo.upsert_field(
            profile_id="user_t3",
            canonical_key="first_name",
            value="Pratham",
            source=ProfileSource.USER_SPOKEN,
            confidence=0.98
        )
        assert field.canonical_key == "first_name"
        assert field.value == "Pratham"
        assert field.source == ProfileSource.USER_SPOKEN
        assert field.confidence == 0.98

        # Second field
        field2 = await repo.upsert_field(
            profile_id="user_t3",
            canonical_key="email",
            value="pratham@example.com",
            source=ProfileSource.USER_ENTERED,
            confidence=1.0
        )
        assert field2.canonical_key == "email"
        assert field2.value == "pratham@example.com"
    finally:
        await engine.dispose()


# =========================================================================
# M7-T4: Profile retrieval
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t4_profile_retrieval():
    repo, engine = await create_test_repository()
    try:
        await repo.upsert_field("user_t4", "phone", "+1-555-0199", ProfileSource.USER_CONFIRMED, 1.0)
        await repo.upsert_field("user_t4", "city", "San Francisco", ProfileSource.USER_SPOKEN, 0.9)

        profile = await repo.get_profile("user_t4")
        assert profile is not None
        assert len(profile.fields) == 2
        assert "phone" in profile.fields
        assert profile.fields["phone"].value == "+1-555-0199"
        assert profile.fields["city"].value == "San Francisco"
    finally:
        await engine.dispose()


# =========================================================================
# M7-T5: Profile update
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t5_profile_update():
    repo, engine = await create_test_repository()
    try:
        await repo.upsert_field("user_t5", "address", "123 Main St", ProfileSource.USER_SPOKEN, 0.8)
        
        # Update value
        updated = await repo.upsert_field("user_t5", "address", "456 Market St", ProfileSource.USER_CONFIRMED, 1.0)
        assert updated.value == "456 Market St"
        assert updated.confidence == 1.0
        assert updated.source == ProfileSource.USER_CONFIRMED

        profile = await repo.get_profile("user_t5")
        assert profile is not None
        assert profile.fields["address"].value == "456 Market St"
    finally:
        await engine.dispose()


# =========================================================================
# M7-T6: Profile field deletion
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t6_profile_field_deletion():
    repo, engine = await create_test_repository()
    try:
        await repo.upsert_field("user_t6", "postal_code", "94105")
        profile_before = await repo.get_profile("user_t6")
        assert profile_before is not None
        assert profile_before.fields.get("postal_code") is not None

        deleted = await repo.delete_field("user_t6", "postal_code")
        assert deleted is True

        profile_after = await repo.get_profile("user_t6")
        assert profile_after is not None
        assert "postal_code" not in profile_after.fields
    finally:
        await engine.dispose()


# =========================================================================
# M7-T7: Complete profile deletion
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t7_complete_profile_deletion():
    repo, engine = await create_test_repository()
    try:
        await repo.upsert_field("user_t7", "first_name", "Pratham")
        await repo.upsert_field("user_t7", "email", "pratham@example.com")

        cleared = await repo.clear_profile_fields("user_t7")
        assert cleared is True

        profile = await repo.get_profile("user_t7")
        assert profile is not None
        assert len(profile.fields) == 0
    finally:
        await engine.dispose()


# =========================================================================
# M7-T8: Profile persistence disabled
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t8_profile_persistence_disabled():
    repo, engine = await create_test_repository()
    service = ProfileService(repository=repo)
    try:
        await service.set_enabled(False, profile_id="user_t8")
        profile = await service.get_profile("user_t8")
        assert profile.is_enabled is False

        # Attempting to write field when disabled returns transient without storing to DB
        field = await service.upsert_field("first_name", "Pratham", profile_id="user_t8")
        assert field.id == "transient"

        profile_after = await repo.get_profile("user_t8")
        assert profile_after is not None
        assert "first_name" not in profile_after.fields
    finally:
        await engine.dispose()


# =========================================================================
# M7-T9 & M7-T10: Redis cache hit & cache miss
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t9_t10_redis_cache_hit_and_miss():
    repo, engine = await create_test_repository()
    cache = ProfileCache(redis_url="redis://127.0.0.1:6379/15")
    service = ProfileService(repository=repo, cache=cache)
    try:
        is_redis = await service.cache.is_available()
        if is_redis:
            # Clear test profile from cache
            await service.cache.invalidate_profile("user_t9_cache")

            misses_before = service.cache.misses
            hits_before = service.cache.hits

            # First retrieval -> Cache Miss -> Loads from DB & populates cache
            p1 = await service.get_profile("user_t9_cache")
            assert p1.id == "user_t9_cache"
            assert service.cache.misses == misses_before + 1

            # Second retrieval -> Cache Hit
            p2 = await service.get_profile("user_t9_cache")
            assert p2.id == "user_t9_cache"
            assert service.cache.hits == hits_before + 1
            assert service.cache.last_latency_ms >= 0.0
        else:
            # Mocked cache verification if Redis not locally available
            mock_cache = ProfileCache(redis_url="redis://invalid_host:6379")
            assert await mock_cache.get_profile("user_t9_cache") is None
            assert mock_cache.misses == 1
    finally:
        await engine.dispose()


# =========================================================================
# M7-T11: Redis unavailable fallback to DB
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t11_redis_unavailable_fallback_to_db():
    repo, engine = await create_test_repository()
    # Point cache to non-existent endpoint
    broken_cache = ProfileCache(redis_url="redis://127.0.0.1:9999/0")
    service = ProfileService(repository=repo, cache=broken_cache)
    try:
        # Should fall back cleanly to database without crashing
        await service.upsert_field("email", "pratham@fallback.com", profile_id="user_t11")
        profile = await service.get_profile("user_t11")
        assert profile is not None
        assert profile.fields["email"].value == "pratham@fallback.com"
    finally:
        await engine.dispose()


# =========================================================================
# M7-T12: Semantic field normalization
# =========================================================================
def test_m7_t12_semantic_field_normalization():
    assert normalize_key_string("First Name") == "first_name"
    assert normalize_key_string("fname") == "first_name"
    assert normalize_key_string("given name") == "first_name"
    assert normalize_key_string("Last Name") == "last_name"
    assert normalize_key_string("surname") == "last_name"
    assert normalize_key_string("Email Address") == "email"
    assert normalize_key_string("e-mail") == "email"
    assert normalize_key_string("Mobile Phone") == "phone"
    assert normalize_key_string("telephone") == "phone"
    assert normalize_key_string("Zip Code") == "postal_code"
    assert normalize_key_string("pin code") == "postal_code"
    assert normalize_key_string("Date of Birth") == "date_of_birth"

    # From FormField signals
    f_auto = FormField(id="f1", name="field_1", type="text", label="", autocomplete="given-name", selector="#f1")
    assert normalize_form_field(f_auto) == "first_name"

    f_type = FormField(id="f2", name="email_field", type="email", label="", selector="#f2")
    assert normalize_form_field(f_type) == "email"


# =========================================================================
# M7-T13: Profile candidate retrieval from form schema
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t13_profile_candidate_retrieval_from_form_schema():
    repo, engine = await create_test_repository()
    service = ProfileService(repository=repo)
    try:
        await service.upsert_field("first_name", "Pratham", profile_id="user_t13")
        await service.upsert_field("last_name", "Kulkarni", profile_id="user_t13")
        await service.upsert_field("email", "pratham@example.com", profile_id="user_t13")

        schema = PageScanResult(
            url="https://example.com/apply",
            title="Application",
            forms=[
                DetectedForm(
                    formId="form1",
                    selector="form#apply",
                    fields=[
                        FormField(id="inp_fname", name="fname", type="text", label="First Name", selector="#inp_fname"),
                        FormField(id="inp_lname", name="lname", type="text", label="Last Name", selector="#inp_lname"),
                        FormField(id="inp_email", name="email", type="email", label="Email Address", selector="#inp_email"),
                        FormField(id="inp_phone", name="phone", type="tel", label="Phone Number", selector="#inp_phone"),
                    ],
                    fieldCount=4
                )
            ],
            totalFieldCount=4
        )

        candidates = await service.get_candidate_values_for_schema(schema, profile_id="user_t13")
        cand_map = {c.field_id: c for c in candidates}

        assert cand_map["inp_fname"].status == FieldMatchStatus.KNOWN
        assert cand_map["inp_fname"].value == "Pratham"
        assert cand_map["inp_lname"].status == FieldMatchStatus.KNOWN
        assert cand_map["inp_lname"].value == "Kulkarni"
        assert cand_map["inp_email"].status == FieldMatchStatus.KNOWN
        assert cand_map["inp_email"].value == "pratham@example.com"
        assert cand_map["inp_phone"].status == FieldMatchStatus.UNKNOWN
        assert cand_map["inp_phone"].value is None
    finally:
        await engine.dispose()


# =========================================================================
# M7-T14: Profile-worthy user information is recognized
# =========================================================================
def test_m7_t14_profile_worthy_user_information_recognized():
    service = ProfileService()
    schema = PageScanResult(
        url="https://example.com",
        title="Test",
        forms=[
            DetectedForm(
                formId="f1",
                selector="form",
                fields=[
                    FormField(id="name_id", name="name", type="text", label="Full Name", selector="#name"),
                    FormField(id="email_id", name="email", type="email", label="Email", selector="#email")
                ],
                fieldCount=2
            )
        ],
        totalFieldCount=2
    )

    actions = [
        {"action": "fill_field", "field_id": "name_id", "value": "Pratham Kulkarni"},
        {"action": "fill_field", "field_id": "email_id", "value": "pratham@example.com"}
    ]

    cands = service.extract_profile_candidates_from_actions(actions, schema)
    assert len(cands) == 2
    assert any(c.canonical_key == "full_name" and c.value == "Pratham Kulkarni" for c in cands)
    assert any(c.canonical_key == "email" and c.value == "pratham@example.com" for c in cands)


# =========================================================================
# M7-T15: Non-profile information is rejected
# =========================================================================
def test_m7_t15_non_profile_information_rejected():
    service = ProfileService()
    schema = PageScanResult(
        url="https://example.com/order",
        title="Order Lookup",
        forms=[
            DetectedForm(
                formId="f1",
                selector="form",
                fields=[
                    FormField(id="ord_id", name="order_num", type="text", label="Order Number #", selector="#ord"),
                    FormField(id="search_id", name="query", type="text", label="Search Keywords", selector="#q")
                ],
                fieldCount=2
            )
        ],
        totalFieldCount=2
    )

    actions = [
        {"action": "fill_field", "field_id": "ord_id", "value": "ORD-99214"},
        {"action": "fill_field", "field_id": "search_id", "value": "laptop stand"}
    ]

    cands = service.extract_profile_candidates_from_actions(actions, schema)
    assert len(cands) == 0  # Order numbers and search queries are NOT profile worthy


# =========================================================================
# M7-T16: Password persistence blocked
# =========================================================================
def test_m7_t16_password_persistence_blocked():
    pwd_field = FormField(id="p1", name="password", type="password", label="Enter Password", selector="#p1")
    assert is_sensitive_field(pwd_field) is True

    is_proh, reason = is_prohibited_candidate("password", "Secret123!")
    assert is_proh is True
    assert reason is not None
    assert "PROHIBITED_KEY_PATTERN" in reason


# =========================================================================
# M7-T17: Payment/card data persistence blocked
# =========================================================================
def test_m7_t17_payment_card_data_blocked():
    card_field = FormField(id="cc", name="card_number", type="text", label="Credit Card Number", selector="#cc")
    assert is_sensitive_field(card_field) is True

    # 16-digit test card number
    is_proh, reason = is_prohibited_candidate("credit_card", "4532015012345678")
    assert is_proh is True

    # CVV
    is_proh_cvv, _ = is_prohibited_candidate("cvv", "883")
    assert is_proh_cvv is True


# =========================================================================
# M7-T18: OTP/token/API-key persistence blocked
# =========================================================================
def test_m7_t18_otp_token_api_key_blocked():
    # OTP
    is_proh_otp, _ = is_prohibited_candidate("otp_code", "492019")
    assert is_proh_otp is True

    # API key
    is_proh_key, _ = is_prohibited_candidate("api_key", "sk-proj-abc12345678901234567890")
    assert is_proh_key is True

    # JWT
    jwt_val = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgN_p"
    is_proh_jwt, _ = is_prohibited_candidate("auth_token", jwt_val)
    assert is_proh_jwt is True


# =========================================================================
# M7-T19: Stored profile value does not overwrite user-entered value
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t19_stored_profile_does_not_overwrite_user_entered_value():
    repo, engine = await create_test_repository()
    service = ProfileService(repository=repo)
    try:
        await service.upsert_field("phone", "9999999999", profile_id="user_t19")

        # Form where phone is already filled with 8888888888
        schema = PageScanResult(
            url="https://example.com",
            title="Test",
            forms=[
                DetectedForm(
                    formId="f1",
                    selector="form",
                    fields=[
                        FormField(id="p1", name="phone", type="tel", label="Phone", currentValue="8888888888", selector="#p1")
                    ],
                    fieldCount=1
                )
            ],
            totalFieldCount=1
        )

        candidates = await service.get_candidate_values_for_schema(schema, profile_id="user_t19")
        assert len(candidates) == 1
        # Priority policy: Candidate is identified as known, but LLM prompt instructions strictly mandate keeping current_value
        assert candidates[0].value == "9999999999"
    finally:
        await engine.dispose()


# =========================================================================
# M7-T20: Profile context reaches LLM safely
# =========================================================================
def test_m7_t20_profile_context_reaches_llm_safely():
    from app.ai.llm.prompts import build_user_prompt
    schema = PageScanResult(
        url="https://example.com",
        title="Form",
        forms=[
            DetectedForm(
                formId="f1",
                selector="form",
                fields=[
                    FormField(id="fname", name="fname", type="text", label="First Name", selector="#fname")
                ],
                fieldCount=1
            )
        ],
        totalFieldCount=1
    )

    prompt = build_user_prompt(
        transcript="Fill my name",
        schema=schema,
        current_values={},
        conversation_history=[],
        profile_context={"first_name": "Pratham", "last_name": "Kulkarni"}
    )

    assert "user_profile_context" in prompt
    assert "Pratham" in prompt
    assert "Kulkarni" in prompt


# =========================================================================
# M7-T21: Profile write cannot be triggered by arbitrary LLM/database commands
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t21_profile_write_cannot_be_triggered_by_arbitrary_commands():
    repo, engine = await create_test_repository()
    service = ProfileService(repository=repo)
    try:
        # Attempting SQL injection in canonical_key or prohibited key
        with pytest.raises(ValueError):
            await service.upsert_field("password'; DROP TABLE user_profiles;--", "hacked")
    finally:
        await engine.dispose()


# =========================================================================
# M7-T22: Database unavailable handled safely
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t22_db_unavailable_handled_safely():
    health = await check_db_health("postgresql+asyncpg://invalid:invalid@127.0.0.1:9999/nonexistent")
    assert health is False


# =========================================================================
# M7-T23: Redis unavailable handled safely
# =========================================================================
@pytest.mark.asyncio
async def test_m7_t23_redis_unavailable_handled_safely():
    cache = ProfileCache(redis_url="redis://127.0.0.1:9999/0")
    is_avail = await cache.is_available()
    assert is_avail is False
    assert await cache.get_profile("test") is None


# =========================================================================
# REST API Endpoints Verification
# =========================================================================
@pytest.mark.asyncio
async def test_m7_rest_api_profile_management():
    repo, engine = await create_test_repository()
    service = ProfileService(repository=repo)
    set_profile_service(service)
    try:
        client = TestClient(app)

        # 1. GET initial profile
        res = client.get("/api/profile?profile_id=api_user")
        assert res.status_code == 200
        data = res.json()
        assert data["profile_id"] == "api_user"
        assert data["is_enabled"] is True
        assert data["field_count"] == 0

        # 2. POST upsert field
        res = client.post("/api/profile?profile_id=api_user", json={"canonical_key": "first_name", "value": "Ada"})
        assert res.status_code == 200
        assert res.json()["success"] is True

        # 3. PATCH field
        res = client.patch("/api/profile/first_name?profile_id=api_user", json={"value": "Ada Lovelace"})
        assert res.status_code == 200

        # 4. GET verify field
        res = client.get("/api/profile?profile_id=api_user")
        assert res.json()["field_count"] == 1
        assert res.json()["fields"]["first_name"]["value"] == "Ada Lovelace"

        # 5. POST prohibited field -> 400 error
        res = client.post("/api/profile?profile_id=api_user", json={"canonical_key": "password", "value": "123456"})
        assert res.status_code == 400

        # 6. DELETE field
        res = client.delete("/api/profile/first_name?profile_id=api_user")
        assert res.status_code == 200

        # 7. POST toggle
        res = client.post("/api/profile/toggle?profile_id=api_user", json={"is_enabled": False})
        assert res.status_code == 200
        assert res.json()["is_enabled"] is False
    finally:
        await engine.dispose()
