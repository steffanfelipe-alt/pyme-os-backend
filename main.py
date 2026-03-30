import logging
import os
import traceback

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from database import Base, engine
from routers import auth_router, clientes, dashboard, documentos, empleados, plantillas, tareas, vencimientos

# --- Logging ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(levelname)-8s %(asctime)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pymeos")

# --- App ---
app = FastAPI(
    title="PyME OS",
    description="Plataforma de inteligencia operativa para estudios contables",
    version="0.1.0",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(auth_router.router)
app.include_router(clientes.router)
app.include_router(empleados.router)
app.include_router(vencimientos.router)
app.include_router(tareas.router)
app.include_router(plantillas.router)
app.include_router(dashboard.router)
app.include_router(documentos.router)


# --- Manejo global de errores ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


# --- Scheduler ---
scheduler = BackgroundScheduler()


# --- Startup ---
@app.on_event("startup")
async def startup() -> None:
    from services.notificacion_service import job_notificaciones_vencimientos

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Conexion a la base de datos exitosa")
        Base.metadata.create_all(bind=engine)
        logger.info("Tablas sincronizadas")
    except Exception as e:
        logger.error("Error conectando a la base de datos: %s", e)

    try:
        from database import SessionLocal
        from services.plantilla_service import seed_plantillas_default
        with SessionLocal() as db:
            seed_plantillas_default(db)
    except Exception as e:
        logger.error("Error cargando plantillas por defecto: %s", e)

    # Crear carpeta base de uploads si no existe
    import os
    os.makedirs("uploads", exist_ok=True)
    logger.info("Carpeta uploads lista")

    scheduler.add_job(
        job_notificaciones_vencimientos,
        trigger="cron",
        hour=8,
        minute=0,
        id="notificaciones_vencimientos",
    )
    scheduler.start()
    logger.info("Scheduler iniciado — job notificaciones programado a las 08:00")


@app.on_event("shutdown")
async def shutdown() -> None:
    scheduler.shutdown()
    logger.info("Scheduler detenido")


# --- Health check ---
@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "0.1.0"}
