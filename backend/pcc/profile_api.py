"""Profile CRUD changes local software data only; it never opens a device."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .profiles import ProfileConflictError, ProfileNotFoundError, ProfileStorageError, ProfileStore
from .settings import ProfileDelete, ProfileDraft, ProfileId, ProfileList, ProfileUpdate, SoftwareProfile

router = APIRouter(prefix="/api/profiles")
_store = ProfileStore()


def get_profile_store() -> ProfileStore:
    return _store


Store = Annotated[ProfileStore, Depends(get_profile_store)]


def profile_error(error: Exception) -> HTTPException:
    if isinstance(error, ProfileNotFoundError):
        return HTTPException(404, "Profile not found.")
    if isinstance(error, ProfileConflictError):
        return HTTPException(409, str(error))
    return HTTPException(503, "Local profile storage is unavailable.")


@router.get("", response_model=ProfileList)
def list_profiles(store: Store) -> ProfileList:
    try:
        return ProfileList(profiles=store.list())
    except (ProfileConflictError, ProfileStorageError) as error:
        raise profile_error(error) from None


@router.post("", response_model=SoftwareProfile, status_code=201)
def create_profile(body: ProfileDraft, store: Store) -> SoftwareProfile:
    try:
        return store.create(body)
    except (ProfileConflictError, ProfileStorageError) as error:
        raise profile_error(error) from None


@router.put("/{profile_id}", response_model=SoftwareProfile)
def update_profile(profile_id: ProfileId, body: ProfileUpdate, store: Store) -> SoftwareProfile:
    try:
        return store.update(profile_id, body)
    except (ProfileNotFoundError, ProfileConflictError, ProfileStorageError) as error:
        raise profile_error(error) from None


@router.delete("/{profile_id}")
def delete_profile(profile_id: ProfileId, body: ProfileDelete, store: Store) -> dict[str, bool]:
    try:
        store.delete(profile_id, body.revision)
        return {"deleted": True}
    except (ProfileNotFoundError, ProfileConflictError, ProfileStorageError) as error:
        raise profile_error(error) from None
