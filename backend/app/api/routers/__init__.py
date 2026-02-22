from .projects import router as projects_router
from .transcription import router as transcription_router
from .translation import router as translation_router
from .dubbing import router as dubbing_router

# Export all for main.py to include
# router_list = [projects_router, transcription_router, translation_router, dubbing_router]
# (Actually individual imports are better for specific prefix management)
