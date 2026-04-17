"""
Conocimiento fiscal argentino para los agentes de IA.
Se inyecta en el system prompt de Dashboard Agent y Chatbot Interno.
Actualizar cuando AFIP modifique normativa, límites o fechas.
"""

CONOCIMIENTO_FISCAL_AR = """
## SISTEMA IMPOSITIVO ARGENTINO — BASE DE CONOCIMIENTO

### REGÍMENES PRINCIPALES

**MONOTRIBUTO**
- Régimen simplificado para pequeños contribuyentes (personas humanas y sucesiones indivisas)
- Unifica IVA + Ganancias + Seguridad Social en un pago mensual único
- Categorías: A a K según ingresos brutos anuales y parámetros de superficie, alquileres y energía eléctrica
- Vencimiento: día 20 de cada mes (pago mensual)
- Recategorización semestral obligatoria: enero y julio de cada año
- Exclusión automática si supera el límite de la categoría más alta o por otros parámetros
- Fuente: RG AFIP 4309 y actualizaciones. Verificar límites vigentes en afip.gob.ar/monotributo

**IVA (Impuesto al Valor Agregado)**
- Responsables Inscriptos (RI): presentan DDJJ mensual
- Alícuota general: 21%. Alícuota diferencial: 10,5% (medicamentos, ciertos alimentos, transporte). Alícuota 0%: exportaciones
- Período fiscal: mensual
- Vencimiento: entre el 12 y el 22 del mes siguiente según terminación del CUIT
  - CUIT termina en 0 o 1: día 12
  - CUIT termina en 2 o 3: día 13
  - CUIT termina en 4 o 5: día 14
  - CUIT termina en 6 o 7: día 15
  - CUIT termina en 8 o 9: día 16
  (Si el vencimiento cae en día no hábil, se corre al siguiente hábil)
- Presentación y pago: simultáneos vía Clave Fiscal en AFIP
- Fuente: Ley 23.349 y modificaciones

**GANANCIAS — PERSONAS HUMANAS**
- Período fiscal: anual (enero a diciembre)
- Presentación DDJJ: entre abril y junio del año siguiente según terminación de CUIT
- Anticipos mensuales: 10 anticipos anuales (de junio a marzo del año siguiente)
- Vencimiento anticipos: entre el 12 y el 22 según terminación de CUIT (misma tabla que IVA)
- Mínimo no imponible y deducciones: actualizados por AFIP trimestralmente
- Fuente: Ley 20.628 y modificaciones

**GANANCIAS — PERSONAS JURÍDICAS (Sociedades)**
- Período fiscal: según cierre de ejercicio comercial (no necesariamente diciembre)
- Anticipos: 10 anticipos a partir del 6to mes del ejercicio
- DDJJ anual: vence aprox. 5 meses después del cierre del ejercicio
- Tasa: 25% sobre utilidades netas
- Fuente: Ley 20.628 Título VI

**INGRESOS BRUTOS (IIBB)**
- Impuesto provincial — cada provincia tiene su propio código fiscal y fechas
- Régimen local vs Convenio Multilateral (para contribuyentes con actividad en múltiples provincias)
- Vencimientos más comunes:
  - CABA: entre el 10 y el 22 según terminación del CUIT
  - Buenos Aires (ARBA): entre el 4 y el 13 según terminación del CUIT
  - Córdoba: día 15 del mes siguiente
  - Santa Fe: día 15 del mes siguiente
  - Mendoza: día 20 del mes siguiente
- Fuente: Código Fiscal de cada provincia. Verificar en el organismo provincial correspondiente.

**BIENES PERSONALES**
- Período fiscal: anual (al 31 de diciembre)
- Presentación y pago DDJJ: junio del año siguiente
- Anticipos: un anticipo anual en marzo/abril
- Participaciones societarias: responsable sustituto es la sociedad (F. 2280)
- Fuente: Ley 23.966 Título VI y modificaciones

**CARGAS SOCIALES — F931**
- Declaración jurada mensual de remuneraciones y cargas sociales de empleados en relación de dependencia
- Incluye: SIPA (jubilación), INSSJP (PAMI), obra social, ART, seguro de vida
- Vencimiento: día 10 del mes siguiente al devengado
- Fuente: RG AFIP 2316 y modificaciones

**FACTURACIÓN ELECTRÓNICA**
- Obligatoria para todos los RI y para monotributistas según categoría
- Tipos de comprobante: Factura A (a RI), Factura B (a consumidor final o exento), Factura C (emitida por monotributistas)
- CAE (Código de Autorización Electrónica): requerido para validar cada comprobante
- Sistema ARCA (ex AFIP): portal de facturación electrónica
- Fuente: RG AFIP 4291 y modificaciones

### REGÍMENES DE RETENCIÓN Y PERCEPCIÓN
- SIRCREB (IIBB sobre acreditaciones bancarias): retención automática bancaria
- Retenciones de Ganancias: agentes de retención designados por AFIP
- Retenciones de IVA: agentes de retención designados por AFIP

### INDICADORES CLAVE PARA UN ESTUDIO CONTABLE
- Margen saludable: entre 60% y 80% para estudios de servicios profesionales
- Score de riesgo preocupante: por encima de 60/100
- Score de riesgo crítico: por encima de 80/100
- Cliente no rentable: tiempo invertido × tarifa horaria > honorario facturado
- Señal de mora: cobro pendiente con más de 15 días de vencido
"""
