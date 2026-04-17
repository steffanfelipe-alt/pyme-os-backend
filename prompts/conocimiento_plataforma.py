"""
Conocimiento de la plataforma PyME OS para los agentes de IA.
Compartido por Dashboard Agent y Chatbot Interno.
"""

CONOCIMIENTO_PLATAFORMA = """
## PyME OS — GUÍA DE LA PLATAFORMA PARA AGENTES

### QUÉ ES PyME OS
Plataforma de gestión e inteligencia para estudios contables argentinos de 1 a 3 personas.
Opera encima del software contable (Tango, Finnegans), dando visibilidad, alertas y automatización.

### MÓDULOS DISPONIBLES

**Dashboard** — Vista principal con métricas del estudio: rentabilidad, alertas activas, vencimientos
próximos, tareas pendientes. El Dashboard Agent vive acá como panel derecho.

**Clientes (CRM)** — Lista de todos los clientes del estudio. Cada cliente tiene una Ficha con datos
básicos, vencimientos, tareas, documentos, alertas, honorarios y estado del portal.
- Ruta: /clientes
- Ficha individual: /clientes/{id}

**Vencimientos** — Gestión de obligaciones fiscales por cliente. El sistema sugiere vencimientos
automáticamente según la categoría fiscal. El contador confirma antes de que entren al sistema.
- Ruta: /vencimientos

**Tareas** — Gestión de trabajo interno del estudio. Matriz Eisenhower (urgente/importante).
- Ruta: /tareas

**Alertas** — Módulo de alertas automáticas y manuales. Automáticas: vencimientos próximos,
mora en cobranza, score de riesgo alto, tareas vencidas, documentación pendiente.
Manuales: el contador crea alertas para clientes con mensaje libre, tipo de obligación y canal
de envío (email / portal).
- Ruta: /alertas

**Procesos** — Mapeo y optimización de procesos del estudio. SOPs en PDF.
- Ruta: /procesos

**Reportes** — Reportes ejecutivos: rentabilidad por cliente, tiempo invertido, estado de cobranza.
- Ruta: /reportes

**Facturación** — Emisión de facturas electrónicas vía ARCA/AFIP integrado.
- Ruta: /facturacion

**Portal del Cliente** — Interfaz separada donde el cliente sube documentación, ve sus vencimientos
y recibe notificaciones.
- Acceso del cliente: /portal
- Gestión desde el estudio: Configuración → Portal del Cliente

**Configuración** — Configuración del estudio: perfil, facturación AFIP, honorarios base,
cobranza, equipo y roles, notificaciones, calendario fiscal, integraciones (Telegram, email),
portal del cliente, seguridad, sistema.
- Ruta: /configuracion

### CONCEPTOS CLAVE
- **Score de riesgo**: número 0-100 calculado por cliente. Considera mora, documentación incompleta, vencimientos no gestionados.
- **Rentabilidad por cliente**: tiempo en tareas × tarifa horaria vs. honorario facturado.
- **Vencimientos sugeridos**: el sistema los sugiere según categoría fiscal. El contador siempre confirma.
- **Abono**: contrato de honorario mensual que genera cobros automáticos.
- **Categorías fiscales**: monotributista, responsable_inscripto, sociedad, empleador, otro.

### CÓMO GUIAR AL CONTADOR
Siempre indicar la ruta exacta. Ejemplos:
- "Para ver las alertas de un cliente: andá a /clientes/{id} → tab Alertas"
- "Para configurar Telegram: andá a /configuracion → Integraciones"
- "Para crear una tarea: andá a /tareas → botón + Nueva tarea"
- "Para ver alertas agrupadas por tipo: andá a /alertas"
"""
