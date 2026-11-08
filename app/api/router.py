from fastapi import APIRouter

from app.api.v1.assistant_chats import router as assistant_chats_router
from app.api.v1.handovers import router as handovers_router
from app.api.v1.health import router as health_router
from app.api.v1.invitations import router as invitations_router
from app.api.v1.manuals import router as manuals_router
from app.api.v1.owner_questions import router as owner_questions_router
from app.api.v1.recipe_scans import router as recipe_scans_router
from app.api.v1.recipes import router as recipes_router
from app.api.v1.stores import router as stores_router
from app.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(users_router)
api_router.include_router(stores_router)
api_router.include_router(invitations_router)
api_router.include_router(manuals_router)
api_router.include_router(recipes_router)
api_router.include_router(recipe_scans_router)
api_router.include_router(assistant_chats_router)
api_router.include_router(owner_questions_router)
api_router.include_router(handovers_router)
