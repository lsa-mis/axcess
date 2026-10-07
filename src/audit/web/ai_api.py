"""Browser API for the desktop AI setup page (``/settings/ai``).

Only mounted when the desktop app starts the server (``AUDIT_DESKTOP=1``).
Nothing here downloads anything until the person presses the button that
calls ``POST /api/ai/install``.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from audit.ai.installer import InstallStatus
from audit.ai.manager import AIBusyError, AIManager, AIPlan, NotEnoughSpaceError
from audit.ai.runtime import RuntimeSetupError
from audit.ai.state import AIPreferences, AIStateError


class InstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: Literal["small", "standard", "large"]


class PreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool


def build_ai_router(manager: AIManager) -> APIRouter:
    router = APIRouter()

    @router.get("/ai/plan")
    async def ai_plan() -> AIPlan:
        """This computer, the model sizes it can run, and the current setup."""
        try:
            return await asyncio.to_thread(manager.plan)
        except AIStateError as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.get("/ai/preferences")
    def ai_preferences() -> AIPreferences:
        try:
            return manager.preferences()
        except AIStateError as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.put("/ai/preferences")
    async def ai_set_preferences(body: PreferenceRequest) -> AIPreferences:
        try:
            return await asyncio.to_thread(manager.set_enabled, body.enabled)
        except AIBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (RuntimeSetupError, AIStateError) as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.get("/ai/install")
    def ai_install_status() -> InstallStatus:
        return manager.installer.status

    @router.post("/ai/install", status_code=202)
    def ai_install(body: InstallRequest) -> InstallStatus:
        """Start or resume the download for one size."""
        current = manager.installer.status
        if manager.installer.running and current.tier != body.tier:
            raise HTTPException(409, "Another AI download is running. Pause it first.")
        try:
            return manager.install(body.tier)
        except NotEnoughSpaceError as exc:
            raise HTTPException(507, str(exc)) from exc

    @router.delete("/ai/install")
    async def ai_pause() -> InstallStatus:
        """Pause the download. What is already downloaded is kept."""
        return await asyncio.to_thread(manager.pause)

    @router.delete("/ai", status_code=204)
    async def ai_remove() -> None:
        """Turn AI features off and delete what Axcess downloaded."""
        try:
            await asyncio.to_thread(manager.remove)
        except AIBusyError as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
