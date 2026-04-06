"""Validaciones específicas para el dominio fiscal argentino."""


def validar_cuit(cuit: str) -> bool:
    """
    Valida un CUIT/CUIL argentino usando el algoritmo de dígito verificador.

    Multiplicadores: [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    Dígito verificador = 11 - (suma % 11)
    Si resultado es 11 → dígito = 0. Si es 10 → CUIT inválido.
    """
    limpio = cuit.replace("-", "").replace(" ", "")

    if len(limpio) != 11 or not limpio.isdigit():
        return False

    multiplicadores = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(int(limpio[i]) * multiplicadores[i] for i in range(10))
    resto = suma % 11
    verificador = 11 - resto

    if verificador == 11:
        verificador = 0
    elif verificador == 10:
        return False

    return verificador == int(limpio[10])
