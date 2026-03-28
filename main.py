from fastapi import FastAPI
from sqlalchemy import text

from database import engine

app = FastAPI(
    title="PyME OS",
    description="Plataforma de inteligencia operativa para estudios contables",
    version="0.1.0",
)


@app.on_event("startup")
async def startup() -> None:
    """Verify database connection on startup."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[OK] Conexion a la base de datos exitosa")
    except Exception as e:
        print(f"[ERROR] Error conectando a la base de datos: {e}")


@app.get("/api/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
