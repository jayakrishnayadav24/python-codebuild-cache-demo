from fastapi import FastAPI
from src.api.routes import router
from src.config.settings import settings

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Production Python app with heavy dependencies"
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
