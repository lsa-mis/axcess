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
from audit.ai.manager import AIManager, AIPlan, NotEnoughSpaceError


class InstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: Literal["small", "standard", "large"]


def build_ai_router(manager: AIManager) -> APIRouter:
    router = APIRouter()

    @router.get("/ai/plan")
    async def ai_plan() -> AIPlan:
        """This computer, the model sizes it can run, and the current setup."""
        return await asyncio.to_thread(manager.plan)

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
        await asyncio.to_thread(manager.remove)

    return router
