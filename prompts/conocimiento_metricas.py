"""
Métricas y mejora de negocio para el Dashboard Agent.
Exclusivo del Dashboard Intelligence Agent — no usado por el chatbot.
"""

CONOCIMIENTO_METRICAS = """
## MÉTRICAS Y MEJORA DE NEGOCIO — BASE DE CONOCIMIENTO PARA EL DASHBOARD AGENT

### RENTABILIDAD

**Cómo se calcula:**
Rentabilidad = Honorario facturado - (Horas invertidas × Tarifa horaria estimada)
Margen = (Honorario - Costo) / Honorario × 100

**Benchmarks para estudios contables argentinos:**
- Margen saludable: 60% a 80%
- Margen preocupante: menos del 50%
- Margen crítico: menos del 30% o negativo

**Causas frecuentes de baja rentabilidad:**
1. Honorario desactualizado (no se actualizó con la inflación)
2. El cliente genera más trabajo del esperado (muchas consultas, documentación desordenada)
3. Tarea subestimada al presupuestar el servicio

**Acciones sugeridas:**
- Si margen bajó más del 15% respecto al mes anterior: revisar qué tareas consumieron más tiempo
- Si cliente tiene margen negativo 2 meses seguidos: considerar ajuste de honorario
- Para ajustar: ir a /clientes/{id} → tab Honorarios → Ajustar honorario

### SCORE DE RIESGO

**Qué mide:** probabilidad de que el cliente genere un problema operativo o financiero.

**Factores que suben el score:**
- Cobros vencidos sin pagar (peso alto)
- Vencimientos fiscales no gestionados a menos de 3 días (peso alto)
- Documentación solicitada no recibida a menos de 5 días del vencimiento (peso alto)
- Tareas del cliente vencidas sin completar (peso medio)
- Sin contacto registrado en más de 30 días (peso bajo)

**Interpretación:**
- 0-30: riesgo bajo — cliente sin problemas activos
- 31-60: riesgo medio — hay algo a revisar, no es urgente
- 61-80: riesgo alto — requiere atención esta semana
- 81-100: riesgo crítico — intervención inmediata

**Acciones sugeridas:**
- Score 61-80: revisar documentación pendiente y tareas vencidas del cliente → /clientes/{id}
- Score 81-100: contactar al cliente directamente, no esperar

### COBRANZA

**Señales de problema:**
- Cobro vencido hace más de 15 días sin respuesta
- Mora recurrente (segundo mes consecutivo)

**Acciones sugeridas:**
- Primer cobro vencido: enviar recordatorio → /alertas → Nueva alerta manual → canal email
- 15 días vencido: llamado directo o email personalizado → /clientes/{id} → tab Honorarios
- 30 días vencido: evaluar si continuar el servicio

**Métrica clave de cobranza:**
- 95%+: cobranza saludable
- 80-95%: cobranza aceptable
- Menos del 80%: problema sistémico

### CARGA DE TRABAJO

**Indicadores de sobrecarga:**
- Más de 20 tareas activas al mismo tiempo
- Tareas con vencimiento en los próximos 3 días sin tiempo registrado

**Acciones sugeridas:**
- 5+ vencimientos próximos 7 días con documentación incompleta: priorizar pedido de documentación
- Tareas vencidas hace más de 3 días: revisar si están bloqueadas → /tareas

### CÓMO HACER SUGERENCIAS EFECTIVAS
Cada sugerencia debe tener tres partes:
1. **Qué observás**: el dato concreto
2. **Por qué importa**: la consecuencia si no se actúa
3. **Acción concreta**: qué hacer y dónde en la plataforma

Ejemplo correcto:
"Tu cliente XYZ tiene un cobro vencido hace 18 días ($15.000). Si no se cobra este mes, el ratio
de cobranza baja al 78%. Te recomiendo enviarle un recordatorio desde /clientes/{id} → tab
Honorarios → Enviar recordatorio."

Ejemplo incorrecto: "Deberías revisar la cobranza de tus clientes."
"""
