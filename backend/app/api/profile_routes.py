import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.profile.service import ProfileService
from app.schemas.profile import (
    BatchUpsertProfileRequest,
    ProfileFieldSchema,
    ProfileResponse,
    ProfileSettingsRequest,
    ProfileSource,
    UpsertProfileFieldRequest,
    UserProfileSchema
)

logger = logging.getLogger("voiceform.api.profile")

router = APIRouter(prefix="/api/profile", tags=["profile"])

# Shared singleton service instance
_profile_service: Optional[ProfileService] = None


def get_profile_service() -> ProfileService:
    global _profile_service
    if _profile_service is None:
        _profile_service = ProfileService()
    return _profile_service


def set_profile_service(service: ProfileService) -> None:
    global _profile_service
    _profile_service = service


@router.get("", response_model=ProfileResponse)
async def get_profile_endpoint(
    profile_id: Optional[str] = Query(None),
    service: ProfileService = Depends(get_profile_service)
) -> ProfileResponse:
    """
    Retrieves stored profile fields and persistence settings for the active user.
    """
    try:
        profile: UserProfileSchema = await service.get_profile(profile_id)
        fields_summary: Dict[str, Dict[str, Any]] = {}
        for k, f in profile.fields.items():
            fields_summary[k] = {
                "id": f.id,
                "canonical_key": f.canonical_key,
                "value": f.value,
                "source": f.source.value if hasattr(f.source, "value") else str(f.source),
                "confidence": f.confidence,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None
            }

        return ProfileResponse(
            profile_id=profile.id,
            is_enabled=profile.is_enabled,
            fields=fields_summary,
            field_count=len(fields_summary)
        )
    except Exception as e:
        logger.error(f"Failed to retrieve profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user profile")


@router.post("", response_model=Dict[str, Any])
async def upsert_profile_endpoint(
    req: UpsertProfileFieldRequest,
    profile_id: Optional[str] = Query(None),
    service: ProfileService = Depends(get_profile_service)
) -> Dict[str, Any]:
    """
    Upserts a single profile field.
    """
    try:
        saved: ProfileFieldSchema = await service.upsert_field(
            canonical_key=req.canonical_key,
            value=req.value,
            profile_id=profile_id,
            source=req.source,
            confidence=req.confidence
        )
        return {
            "success": True,
            "field": saved.model_dump(mode="json")
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to upsert profile field: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile field")


@router.post("/batch", response_model=Dict[str, Any])
async def batch_upsert_profile_endpoint(
    req: BatchUpsertProfileRequest,
    profile_id: Optional[str] = Query(None),
    service: ProfileService = Depends(get_profile_service)
) -> Dict[str, Any]:
    """
    Batch upserts multiple profile fields.
    """
    saved_list = []
    errors = []
    for item in req.fields:
        try:
            saved = await service.upsert_field(
                canonical_key=item.canonical_key,
                value=item.value,
                profile_id=profile_id,
                source=item.source,
                confidence=item.confidence
            )
            saved_list.append(saved.model_dump(mode="json"))
        except Exception as e:
            errors.append({"key": item.canonical_key, "error": str(e)})

    return {
        "success": len(errors) == 0,
        "saved_count": len(saved_list),
        "saved": saved_list,
        "errors": errors
    }


class UpdateFieldRequest(BaseModel):
    value: str
    confidence: Optional[float] = 1.0


@router.patch("/{canonical_key}", response_model=Dict[str, Any])
async def patch_field_endpoint(
    canonical_key: str,
    req: UpdateFieldRequest,
    profile_id: Optional[str] = Query(None),
    service: ProfileService = Depends(get_profile_service)
) -> Dict[str, Any]:
    """
    Updates the value of a specific profile field.
    """
    try:
        saved = await service.upsert_field(
            canonical_key=canonical_key,
            value=req.value,
            profile_id=profile_id,
            source=ProfileSource.USER_CONFIRMED,
            confidence=req.confidence or 1.0
        )
        return {
            "success": True,
            "field": saved.model_dump(mode="json")
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to update profile field: {e}")
        raise HTTPException(status_code=500, detail="Failed to patch profile field")


@router.delete("/{canonical_key}", response_model=Dict[str, Any])
async def delete_field_endpoint(
    canonical_key: str,
    profile_id: Optional[str] = Query(None),
    service: ProfileService = Depends(get_profile_service)
) -> Dict[str, Any]:
    """
    Deletes an individual profile field.
    """
    try:
        deleted = await service.delete_field(canonical_key, profile_id=profile_id)
        return {
            "success": deleted,
            "canonical_key": canonical_key
        }
    except Exception as e:
        logger.error(f"Failed to delete profile field: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete profile field")


@router.delete("", response_model=Dict[str, Any])
async def clear_profile_endpoint(
    profile_id: Optional[str] = Query(None),
    service: ProfileService = Depends(get_profile_service)
) -> Dict[str, Any]:
    """
    Clears all fields in the user's profile.
    """
    try:
        cleared = await service.clear_profile(profile_id=profile_id)
        return {
            "success": cleared,
            "message": "User profile cleared successfully"
        }
    except Exception as e:
        logger.error(f"Failed to clear profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear profile")


@router.post("/toggle", response_model=Dict[str, Any])
async def toggle_persistence_endpoint(
    req: ProfileSettingsRequest,
    profile_id: Optional[str] = Query(None),
    service: ProfileService = Depends(get_profile_service)
) -> Dict[str, Any]:
    """
    Enables or disables persistent profile storage for the user.
    """
    try:
        updated = await service.set_enabled(req.is_enabled, profile_id=profile_id)
        return {
            "success": updated,
            "is_enabled": req.is_enabled
        }
    except Exception as e:
        logger.error(f"Failed to toggle profile settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle profile persistence")
