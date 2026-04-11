"""
Servicio de integración con ARCA (ex AFIP) via Web Services SOAP.
Implementa WSAA (autenticación) y WSFE (facturación electrónica).

Endpoints:
  Homologación: wsaahomo.afip.gov.ar / wswhomo.afip.gov.ar
  Producción:   wsaa.afip.gov.ar / wsfev1.afip.gov.ar
"""
import base64
import logging
import os
from datetime import datetime, date, timedelta, timezone
from typing import Optional

logger = logging.getLogger("pymeos")

# URLs de los web services
_WS_URLS = {
    "homologacion": {
        "wsaa": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?WSDL",
        "wsfe": "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL",
    },
    "produccion": {
        "wsaa": "https://wsaa.afip.gov.ar/ws/services/LoginCms?WSDL",
        "wsfe": "https://wsfev1.afip.gov.ar/wsfev1/service.asmx?WSDL",
    },
}

# Cache de tickets en memoria: {(cuit, modo) -> {"token": str, "sign": str, "expira": datetime}}
_ticket_cache: dict[tuple, dict] = {}


def _modo_env() -> str:
    return os.environ.get("AFIP_MODO", "homologacion")


def _fernet_arca():
    from cryptography.fernet import Fernet
    key = os.environ.get("AFIP_CERT_KEY", "")
    if not key:
        raise RuntimeError("AFIP_CERT_KEY no está configurada en .env")
    return Fernet(key.encode() if isinstance(key, str) else key)


def decrypt_cert(cifrado: str) -> str:
    return _fernet_arca().decrypt(cifrado.encode()).decode()


def encrypt_cert(texto: str) -> str:
    return _fernet_arca().encrypt(texto.encode()).decode()


def _obtener_ticket(cuit: str, cert_pem: str, key_pem: str, modo: str) -> tuple[str, str]:
    """
    Obtiene un ticket WSAA (token + sign). Usa caché en memoria.
    Lanza RuntimeError si la autenticación falla.
    """
    cache_key = (cuit, modo)
    cached = _ticket_cache.get(cache_key)
    if cached and cached["expira"] > datetime.now(timezone.utc):
        return cached["token"], cached["sign"]

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        from cryptography.x509 import CertificateBuilder
        import cms
    except ImportError:
        pass

    try:
        import zeep
        from lxml import etree
        from signxml import XMLSigner, methods
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography import x509 as cx509
    except ImportError as e:
        raise RuntimeError(f"Dependencia faltante para ARCA: {e}. Instalá: pip install zeep lxml signxml cryptography")

    # Construir el TRA (Ticket de Requerimiento de Acceso)
    ahora = datetime.now(timezone.utc)
    expira = ahora + timedelta(hours=12)
    tra_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>{int(ahora.timestamp())}</uniqueId>
    <generationTime>{ahora.strftime('%Y-%m-%dT%H:%M:%S-03:00')}</generationTime>
    <expirationTime>{expira.strftime('%Y-%m-%dT%H:%M:%S-03:00')}</expirationTime>
  </header>
  <service>wsfe</service>
</loginTicketRequest>"""

    # Firmar el TRA con el certificado del estudio
    cert_obj = cx509.load_pem_x509_certificate(cert_pem.encode())
    key_obj = load_pem_private_key(key_pem.encode(), password=None)

    signer = XMLSigner(
        method=methods.detached,
        signature_algorithm="rsa-sha256",
        digest_algorithm="sha256",
        c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
    )
    root = etree.fromstring(tra_xml.encode())
    signed = signer.sign(root, key=key_obj, cert=cert_obj)
    cms_data = base64.b64encode(etree.tostring(signed)).decode()

    # Llamar a WSAA
    url_wsaa = _WS_URLS[modo]["wsaa"]
    client_wsaa = zeep.Client(url_wsaa)
    resultado = client_wsaa.service.loginCms(in0=cms_data)

    # Parsear respuesta
    resp_root = etree.fromstring(resultado.encode())
    ns = {"ta": "http://ar.gov.afip.dif.FEV1/"}
    token = resp_root.find(".//token").text
    sign = resp_root.find(".//sign").text
    expira_ta = resp_root.find(".//expirationTime").text

    _ticket_cache[cache_key] = {
        "token": token,
        "sign": sign,
        "expira": datetime.fromisoformat(expira_ta.replace("-03:00", "+00:00")),
    }
    return token, sign


def obtener_ultimo_numero(
    cuit: str,
    punto_venta: int,
    tipo_cbte: int,
    cert_pem: str,
    key_pem: str,
    modo: str,
) -> int:
    """Retorna el último número emitido para el punto de venta y tipo de comprobante."""
    import zeep

    token, sign = _obtener_ticket(cuit, cert_pem, key_pem, modo)
    url_wsfe = _WS_URLS[modo]["wsfe"]
    client = zeep.Client(url_wsfe)

    auth = {"Token": token, "Sign": sign, "Cuit": int(cuit.replace("-", ""))}
    resp = client.service.FECompUltimoAutorizado(
        Auth=auth,
        PtoVta=punto_venta,
        CbteTipo=tipo_cbte,
    )
    return resp.CbteNro


def emitir_comprobante(
    cuit: str,
    punto_venta: int,
    tipo_cbte: int,
    numero: int,
    fecha_cbte: str,         # "YYYYMMDD"
    concepto: int,
    cuit_receptor: str,
    importe_neto: float,
    importe_iva: float,
    importe_total: float,
    alicuota_id: int,        # 5=21%, 4=10.5%, 6=27%, 3=0%
    cert_pem: str,
    key_pem: str,
    modo: str,
) -> dict:
    """
    Llama a FECAESolicitar y devuelve {cae, fecha_vto_cae, numero}.
    Lanza RuntimeError si ARCA rechaza el comprobante.
    """
    import zeep

    token, sign = _obtener_ticket(cuit, cert_pem, key_pem, modo)
    url_wsfe = _WS_URLS[modo]["wsfe"]
    client = zeep.Client(url_wsfe)

    auth = {"Token": token, "Sign": sign, "Cuit": int(cuit.replace("-", ""))}

    iva_array = []
    if alicuota_id != 3:   # 3 = exento
        iva_array = [{"Id": alicuota_id, "BaseImp": importe_neto, "Importe": importe_iva}]

    detalle = {
        "Concepto": concepto,
        "DocTipo": 80,                                      # 80=CUIT, 99=Consumidor Final
        "DocNro": int(cuit_receptor.replace("-", "")),
        "CbteDesde": numero,
        "CbteHasta": numero,
        "CbteFch": fecha_cbte,
        "ImpTotal": importe_total,
        "ImpTotConc": 0,
        "ImpNeto": importe_neto,
        "ImpOpEx": 0,
        "ImpIVA": importe_iva,
        "ImpTrib": 0,
        "MonId": "PES",
        "MonCotiz": 1,
        "Iva": {"AlicIva": iva_array},
    }

    solicitud = {
        "FeCabReq": {"CantReg": 1, "PtoVta": punto_venta, "CbteTipo": tipo_cbte},
        "FeDetReq": {"FECAEDetRequest": [detalle]},
    }

    resp = client.service.FECAESolicitar(Auth=auth, FeCAEReq=solicitud)
    det = resp.FeDetResp.FECAEDetResponse[0]

    if det.Resultado == "R":  # Rechazado
        observaciones = getattr(det, "Observaciones", None)
        obs_txt = ""
        if observaciones:
            obs_list = getattr(observaciones, "Obs", [])
            obs_txt = "; ".join(f"{o.Code}: {o.Msg}" for o in obs_list)
        raise RuntimeError(f"ARCA rechazó el comprobante: {obs_txt}")

    return {
        "cae": det.CAE,
        "fecha_vto_cae": det.CAEFchVto,   # "YYYYMMDD"
        "numero": det.CbteDesde,
    }


def tipo_cbte_a_int(tipo: str) -> int:
    """Convierte tipo 'A'/'B'/'C' al código de comprobante AFIP para servicios."""
    return {"A": 1, "B": 6, "C": 11}.get(tipo.upper(), 6)


def alicuota_a_id(alicuota: float) -> int:
    """Convierte la alícuota de IVA al ID de AFIP."""
    return {21.0: 5, 10.5: 4, 27.0: 6, 0.0: 3}.get(alicuota, 5)
