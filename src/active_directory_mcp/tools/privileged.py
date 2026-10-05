"""Deteccion de grupos con privilegio que no depende del idioma del dominio.

Por que existe esto: las tools de auditoria buscaban los grupos privilegiados
por sAMAccountName con los nombres en ingles ("Domain Admins", "Account
Operators"...). En un dominio traducido eso no encuentra nada. Este dominio
esta en portugues y el grupo se llama "Admins. del dominio", asi que la
auditoria reportaba cero administradores sobre un dominio con 10 miembros en
Domain Admins.

Dos criterios, porque ninguno cubre el caso completo:

- **RID**: el ultimo componente del objectSid. Los grupos integrados siempre
  tienen el mismo RID en todos los dominios y en todos los idiomas (Domain
  Admins es 512 siempre). Es certeza. No se puede filtrar en el servidor
  (`(objectSid=S-1-5-21-...-512)` devuelve 0 resultados: AD no acepta el SID
  en texto), asi que se lee y se compara aqui.
- **Nombre**: para los grupos propios de la empresa, que no tienen RID
  conocido y no estan en ninguna lista universal. Aqui solo hay sospecha, y se
  marca como tal: `detected_by` dice como se encontro cada grupo para que nadie
  confunda una certeza con una conjetura.
"""

from typing import Any, Dict, List, Optional

# RIDs bien conocidos. OJO: el RID no significa lo mismo en las dos familias de
# SID, asi que van en tablas separadas. S-1-5-21-...-512 es Domain Admins y
# S-1-5-32-512 no existe, pero S-1-5-21-...-544 (Administrators, el viejo del
# dominio) y S-1-5-32-544 (Administrators, el de BUILTIN) son el numero 544.
# Verificado contra este dominio el 2026-10-02.
DOMAIN_RIDS: Dict[int, Dict[str, str]] = {
    512: {"role": "Domain Admins", "tier": "critical"},
    516: {"role": "Domain Controllers", "tier": "elevated"},
    518: {"role": "Schema Admins", "tier": "critical"},
    519: {"role": "Enterprise Admins", "tier": "critical"},
}

# S-1-5-32, el contenedor BUILTIN.
BUILTIN_RIDS: Dict[int, Dict[str, str]] = {
    544: {"role": "Administrators", "tier": "critical"},
    548: {"role": "Account Operators", "tier": "elevated"},
    549: {"role": "Server Operators", "tier": "elevated"},
    550: {"role": "Print Operators", "tier": "elevated"},
    551: {"role": "Backup Operators", "tier": "elevated"},
    552: {"role": "Remote Desktop Users", "tier": "elevated"},
    553: {"role": "RAS Servers", "tier": "elevated"},
    554: {"role": "Pre-Windows 2000 Compatible Access", "tier": "elevated"},
    555: {"role": "Pre-Windows 2000 Remote Access", "tier": "elevated"},
    556: {"role": "Network Configuration Operators", "tier": "elevated"},
    562: {"role": "Distributed COM Users", "tier": "elevated"},
}

# Subcadenas que delatan un grupo con privilegios. Deliberadamente corto: es
# mejor dejar pasar un grupo sospechoso que marcar 145 grupos como
# privilegiados y que el modelo deje de mirar la lista.
PRIVILEGED_NAME_HINTS = ("admin", "administrador", "privileg", "root")

ATTRIBUTES = ["cn", "sAMAccountName", "displayName", "description",
              "member", "objectSid"]


def rid_de(object_sid: Any) -> Optional[int]:
    """Ultimo componente del SID (el RID) como entero, o None si no se puede.

    Con get_info=ALL (como conecta LDAPManager) ldap3 devuelve objectSid ya
    como "S-1-5-21-...-512". Con get_info=NONE llega en bytes binarios little
    endian con byte de revision delante, y ahi el ultimo byte no es el RID, por
    eso se descarta en vez de adivinar una conversion.
    """
    if not object_sid:
        return None
    if isinstance(object_sid, (bytes, bytearray)):
        return None
    texto = str(object_sid).strip()
    partes = texto.rsplit("-", 1)
    if len(partes) != 2 or not partes[1].isdigit():
        return None
    return int(partes[1])


def familia_del_sid(object_sid: Any) -> Optional[str]:
    """'domain', 'builtin' o None si el SID no esta en una familia conocida.

    Sin esto, un grupo de la empresa con RID 512 pasaria por Domain Admin y un
    grupo normal con el RID de BUILTIN pasaria por un grupo de sistema.
    """
    if not object_sid or isinstance(object_sid, (bytes, bytearray)):
        return None
    texto = str(object_sid).strip().upper()
    if texto.startswith("S-1-5-21-"):
        return "domain"
    if texto.startswith("S-1-5-32-"):
        return "builtin"
    return None


def _texto(entry: Dict[str, Any], atributo: str) -> str:
    valor = entry.get("attributes", {}).get(atributo) or ""
    if isinstance(valor, (list, tuple)):
        valor = valor[0] if valor else ""
    return str(valor).strip()


def cn_de_dn(dn: str) -> str:
    """CN del RDN izquierdo del DN. El atributo cn siempre viene, el DN
    tambien, y el CN del DN es la ultima red de seguridad."""
    if not dn:
        return ""
    rdn = str(dn).split(",", 1)[0].strip()
    if rdn.lower().startswith("cn="):
        return rdn[3:].strip()
    return rdn


def _parece_privilegiado(entry: Dict[str, Any]) -> bool:
    # Solo el nombre, y el CN del DN como red de seguridad. La description NO
    # entra: en el dominio real las cuentas de servicio de SQL Server describen
    # su grupo como "...access and privileges to be assigned as the log on
    # account for SQL Server FullText Search", y con description dentro cuatro
    # grupos de servicio de SQL salian como grupos de administracion.
    for atributo in ("cn", "sAMAccountName"):
        valor = _texto(entry, atributo).lower()
        if any(pista in valor for pista in PRIVILEGED_NAME_HINTS):
            return True
    valor = cn_de_dn(entry.get("dn", "")).lower()
    return any(pista in valor for pista in PRIVILEGED_NAME_HINTS)


def clasificar(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Como se detecta el privilegio de un grupo.

    Devuelve None si el grupo no es privilegiado, para que la tool no devuelva
    una lista de 145 grupos y el modelo deje de mirarla.
    """
    sid = entry.get("attributes", {}).get("objectSid")
    rid = rid_de(sid)
    familia = familia_del_sid(sid)
    tabla = {"domain": DOMAIN_RIDS, "builtin": BUILTIN_RIDS}.get(familia, {})
    conocido = tabla.get(rid) if rid is not None else None

    if conocido:
        return {"detected_by": "rid", "well_known_role": conocido["role"],
                "risk_tier": conocido["tier"], "rid": rid}

    if _parece_privilegiado(entry):
        return {"detected_by": "name", "well_known_role": None,
                "risk_tier": "review", "rid": rid}

    return None


class PrivilegedGroupScanner:
    """Localiza los grupos privilegiados del dominio con una sola busqueda.

    Antes se hacia una busqueda por cada nombre en ingles (9 en total). Ahora se
    leen todos los grupos de una vez y se clasifican en memoria: 145 entradas no
    son nada, y de paso no hay nombres en ingles que dependan del idioma.
    """

    def __init__(self, tool):
        self.tool = tool

    def escanear(self) -> List[Dict[str, Any]]:
        entradas = self.tool.ldap.search(
            search_base=self.tool.ldap.ad_config.base_dn,
            search_filter="(objectClass=group)",
            attributes=ATTRIBUTES,
        )
        encontrados: List[Dict[str, Any]] = []
        for entrada in entradas or []:
            veredicto = clasificar(entrada)
            if veredicto is None:
                continue
            miembros = entrada.get("attributes", {}).get("member") or []
            if isinstance(miembros, str):
                miembros = [miembros]
            encontrados.append({
                "dn": entrada.get("dn", ""),
                "sam_account_name": _texto(entrada, "sAMAccountName"),
                "display_name": (_texto(entrada, "displayName")
                                 or _texto(entrada, "cn")
                                 or cn_de_dn(entrada.get("dn", ""))),
                "description": _texto(entrada, "description"),
                "member_count": len(miembros),
                "members": list(miembros),
                "object_sid": entrada.get("attributes", {}).get("objectSid", ""),
                **veredicto,
            })
        # primero los grupos de riesgo alto, luego por numero de miembros:
        # lo que mas se parece a "10 admins en Domain Admins" va primero.
        orden = {"critical": 0, "elevated": 1, "review": 2}
        encontrados.sort(key=lambda g: (orden.get(g["risk_tier"], 3),
                                        -g["member_count"]))
        return encontrados