"""Tests del falso negativo de las tools de auditoria.

En un dominio con los grupos integrados traducidos (este esta en portugues:
"Admins. del dominio", "Administradores de esquema"), las tools buscaban por
sAMAccountName en ingles y no encontraban nada. Devolvian 0 administradores
sobre un dominio con 10 miembros en Domain Admins y 7 en Administrators.

El RID del SID no depende del idioma: el Domain Admins es el 512 en cualquier
idioma. Ese es el criterio, y por nombre solo se marca lo que no tiene RID
conocido (grupos propios de la empresa, que no existen en ninguna lista).
"""

import json
from unittest.mock import MagicMock, Mock

import pytest

from active_directory_mcp.tools.security import SecurityTools


@pytest.fixture
def mock_ldap_manager():
    manager = Mock()
    manager.ad_config = Mock()
    manager.ad_config.base_dn = "DC=test,DC=local"
    return manager


def grupo(dn, cn, sam, rid=None, description="", members=(), familia="dominio"):
    """Una entrada de grupo tal y como las devuelve LDAPManager.search.

    `familia` decide el prefijo del objectSid: los RIDs 512/518/519 son
    relativos al dominio (S-1-5-21-...) y los 544/548/... al contenedor
    BUILTIN (S-1-5-32-...). El 544 en la familia equivocada no significa lo
    mismo, y el test lo cubre.
    """
    attrs = {
        "cn": cn,
        "sAMAccountName": sam,
        "description": description,
        "member": list(members),
    }
    if rid is not None:
        prefijo = "S-1-5-21-111-222-333" if familia == "dominio" else "S-1-5-32"
        attrs["objectSid"] = f"{prefijo}-{rid}"
    return {"dn": dn, "attributes": attrs}


DOMINIO_SID = "S-1-5-21-111-222-333-500"
USUARIOS = [
    grupo(f"CN=Ana,OU=Users,{DOMINIO_SID}", "Ana", "ana", 1100),
    grupo(f"CN=Bob,OU=Users,{DOMINIO_SID}", "Bob", "bob", 1101),
]


def a_json(resultado):
    return json.loads(resultado[0].text)


class TestGetPrivilegedGroupsPorRID:
    """El criterio real: RID del objectSid, no nombre."""

    def test_encuentra_domain_admins_en_un_dominio_traducido(self, mock_ldap_manager):
        mock_ldap_manager.search.return_value = [
            grupo(f"CN=Admins. del dominio,CN=Users,{DOMINIO_SID}",
                  "Admins. del dominio", "Admins. del dominio", 512,
                  "Administradores designados del dominio",
                  [USUARIOS[0]["dn"]]),
        ]

        d = a_json(SecurityTools(mock_ldap_manager).get_privileged_groups())

        assert d["total_groups"] == 1
        assert d["privileged_groups"][0]["display_name"] == "Admins. del dominio"
        assert d["privileged_groups"][0]["member_count"] == 1

    def test_no_depende_del_samaccountname_ingles(self, mock_ldap_manager):
        """Regression: la busqueda por sAMAccountName en ingles es lo que fallaba."""
        mock_ldap_manager.search.return_value = [
            grupo(f"CN=Administradores,{DOMINIO_SID}", "Administradores",
                  "Administradores", 544, "Los administradores tienen acceso completo"),
        ]

        d = a_json(SecurityTools(mock_ldap_manager).get_privileged_groups())

        filtros = [c.kwargs.get("search_filter", "") for c in mock_ldap_manager.search.call_args_list]
        assert not any("Domain Admins" in f for f in filtros), filtros
        assert d["total_groups"] == 1

    def test_incluye_el_rol_del_rid_para_que_el_modelo_no_invente(self, mock_ldap_manager):
        mock_ldap_manager.search.return_value = [
            grupo("CN=Administradores,CN=Builtin,DC=test,DC=local",
                  "Administradores", "Administradores", 544, familia="builtin"),
        ]

        d = a_json(SecurityTools(mock_ldap_manager).get_privileged_groups())

        g = d["privileged_groups"][0]
        assert g["well_known_role"] == "Administrators"
        assert g["detected_by"] == "rid"
        assert g["risk_tier"] in ("critical", "elevated")

    def test_no_devuelve_grupos_normales(self, mock_ldap_manager):
        mock_ldap_manager.search.return_value = [
            grupo(f"CN=Recepcion,{DOMINIO_SID}", "Recepcion", "Recepcion", 2001),
            grupo(f"CN=Contabilidad,{DOMINIO_SID}", "Contabilidad", "Contabilidad", 2002),
        ]

        d = a_json(SecurityTools(mock_ldap_manager).get_privileged_groups())

        assert d["total_groups"] == 0

    def test_marca_los_grupos_propios_por_nombre(self, mock_ldap_manager):
        """GSL_AdministradorLocal no tiene RID conocido y tiene 52 miembros.

        El RID no lo cubre, asi que hace falta el criterio por nombre. Y hay que
        decir COMO se detecto, para que el modelo distinga certeza de sospecha.
        """
        mock_ldap_manager.search.return_value = [
            grupo(f"CN=GSL_AdministradorLocal,OU=G,{DOMINIO_SID}",
                  "GSL_AdministradorLocal", "GSL_AdministradorLocal", 3105,
                  "Administradores locales", [USUARIOS[0]["dn"], USUARIOS[1]["dn"]]),
        ]

        d = a_json(SecurityTools(mock_ldap_manager).get_privileged_groups())

        g = d["privileged_groups"][0]
        assert g["display_name"] == "GSL_AdministradorLocal"
        assert g["detected_by"] == "name"
        assert g["well_known_role"] is None
        assert g["member_count"] == 2


class TestAuditAdminAccountsPorRID:
    def test_audita_los_miembros_de_un_grupo_localizado(self, mock_ldap_manager):
        def buscar(**kw):
            base = kw.get("search_base", "")
            filtro = kw.get("search_filter", "")
            if "objectClass=group" in filtro:
                return [grupo(f"CN=Admins. del dominio,CN=Users,{DOMINIO_SID}",
                              "Admins. del dominio", "Admins. del dominio", 512,
                              members=[USUARIOS[0]["dn"]])]
            if "sAMAccountName=ana" in filtro or USUARIOS[0]["dn"] == base:
                return [{"dn": USUARIOS[0]["dn"], "attributes": {
                    "sAMAccountName": "ana", "displayName": "Ana Ruiz",
                    "mail": "ana@test.local", "userAccountControl": 512,
                    "lastLogon": 130000000000000000, "pwdLastSet": 130000000000000000,
                    "logonCount": 12, "badPwdCount": 0}}]
            return []

        mock_ldap_manager.search.side_effect = buscar

        tool = SecurityTools(mock_ldap_manager)
        d = a_json(tool.audit_admin_accounts())

        filtros = [c.kwargs.get("search_filter", "") for c in mock_ldap_manager.search.call_args_list]
        assert not any("Domain Admins" in f for f in filtros), filtros
        assert d["total_admin_accounts"] == 1
        assert d["admin_accounts"][0]["sam_account_name"] == "ana"

    def test_sigue_avisando_si_el_directorio_no_se_puede_leer(self, mock_ldap_manager):
        """Un fallo de busqueda no puede disfrazarse de "no hay admins"."""
        from ldap3.core.exceptions import LDAPException
        mock_ldap_manager.search.side_effect = LDAPException("no se pudo leer")

        d = a_json(SecurityTools(mock_ldap_manager).audit_admin_accounts())

        assert d.get("success") is not True


def test_una_sola_busqueda_de_grupos_para_ambas_tools():
    """Las dos tools leen el directorio una vez, no una por cada nombre.

    Antes eran 9 busquedas con nombres en ingles. Ademas de lento, eso hacia
    que el resultado dependiera del idioma del dominio.
    """
    for metodo in ("get_privileged_groups", "audit_admin_accounts"):
        mock = MagicMock()
        mock.ad_config.base_dn = "DC=test,DC=local"
        mock.search.return_value = [grupo(
            "CN=Administradores,CN=Usuarios,DC=test,DC=local",
            "Administradores", "Administradores", 544,
            familia="builtin",
            members=["CN=ana,CN=Usuarios,DC=test,DC=local"])]
        tool = SecurityTools(mock)

        d = a_json(getattr(tool, metodo)())

        filtros = [c.kwargs.get("search_filter", "")
                   for c in mock.search.call_args_list]
        de_grupos = [f for f in filtros if "objectClass=group" in f]
        assert len(de_grupos) == 1, f"{metodo}: {de_grupos}"
        assert d["detection"], f"{metodo} no explica como detecto los grupos"