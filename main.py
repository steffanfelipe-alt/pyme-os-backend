import logging
import os
import traceback

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from database import Base, engine

# Registrar modelos en Base.metadata — necesario para create_all y FK resolution
import models.studio  # noqa: F401
import models.dashboard_conversation  # noqa: F401
import models.assistant_conversation  # noqa: F401
import models.email_log  # noqa: F401

from routers import (
    agent_assistant, agent_dashboard, alerts, auth_router, automatizaciones, clientes,
    conocimiento, dashboard, documentos, emails, empleados, plantillas, procesos,
    profitability, reportes, reports, risk, sop_asistido, tareas, vencimientos, webhooks,
)
from modules.asistente.router import router as asistente_router

# --- Logging ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(levelname)-8s %(asctime)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pymeos")

# --- Rate Limiter ---
from rate_limiter import limiter  # noqa: E402

# --- App ---
app = FastAPI(
    title="PyME OS",
    description="Plataforma de inteligencia operativa para estudios contables",
    version="0.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS ---
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
_allowed_origins = (
    [o.strip() for o in _allowed_origins_env.split(",")]
    if _allowed_origins_env != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
app.include_router(profitability.router)
app.include_router(alerts.router)
app.include_router(risk.router)
app.include_router(reports.router)
app.include_router(emails.router)
app.include_router(procesos.router)
app.include_router(conocimiento.router)
app.include_router(automatizaciones.router)
app.include_router(sop_asistido.router)
app.include_router(reportes.router)
app.include_router(agent_dashboard.router)
app.include_router(agent_assistant.router)
app.include_router(asistente_router)
app.include_router(webhooks.router)


# --- Manejo global de errores ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": "Ocurrió un error inesperado. Contactá al administrador."},
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

    # Crear carpetas de uploads si no existen
    import os
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("uploads/sops", exist_ok=True)
    logger.info("Carpetas uploads listas")

    scheduler.add_job(
        job_notificaciones_vencimientos,
        trigger="cron",
        hour=8,
        minute=0,
        id="notificaciones_vencimientos",
    )

    from services.gmail_service import job_renovar_gmail_watch
    from database import SessionLocal as _SessionLocal

    def _job_renovar_watch():
        with _SessionLocal() as db:
            job_renovar_gmail_watch(db)

    scheduler.add_job(
        _job_renovar_watch,
        trigger="interval",
        days=3,
        id="renovar_gmail_watch",
    )

    from modules.asistente.scheduler import job_resumen_diario_empleados
    scheduler.add_job(
        job_resumen_diario_empleados,
        trigger="cron",
        hour=8,
        minute=0,
        timezone="America/Argentina/Buenos_Aires",
        id="asistente_resumen_diario",
    )

    from services.notificacion_service import job_resumen_semanal_email
    scheduler.add_job(
        job_resumen_semanal_email,
        trigger="cron",
        day_of_week="mon",
        hour=8,
        minute=0,
        timezone="America/Argentina/Buenos_Aires",
        id="resumen_semanal_email",
    )

    scheduler.start()
    logger.info("Scheduler iniciado — notificaciones 08:00, watch Gmail cada 3 días, resumen asistente 08:00 AR, resumen semanal lunes 08:00 AR")


@app.on_event("shutdown")
async def shutdown() -> None:
    scheduler.shutdown()
    logger.info("Scheduler detenido")


# --- Health check ---
@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "0.1.0"}
