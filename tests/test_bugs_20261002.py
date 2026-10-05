"""Tests de los bugs encontrados al auditar las tools contra un AD real.

Los tres vienen de la misma familia: la tool le pide al servidor algo que el
servidor no puede dar, y en vez de degradar devuelve un error o un falso
resultado. Estan agrupados aqui porque los encontro la misma auditoria
(2026-10-02), no porque pertenezcan al mismo modulo.
"""

import json
from datetime import timedelta

import pytest
from unittest.mock import Mock
from ldap3.core.exceptions import LDAPException

from active_directory_mcp.tools.group import GroupTools
from active_directory_mcp.tools.security import SecurityTools
from active_directory_mcp.tools.user import UserTools
from active_directory_mcp.tools.organizational_unit import OrganizationalUnitTools


@pytest.fixture
def mock_ldap_manager():
    manager = Mock()
    manager.ad_config = Mock()
    manager.ad_config.base_dn = "DC=test,DC=local"
    manager.ou_config = Mock()
    manager.ou_config.users_ou = "OU=Users,DC=test,DC=local"
    manager.ou_config.groups_ou = "OU=Groups,DC=test,DC=local"
    return manager


def atributos_pedidos(manager):
    """Atributos pedidos en cada llamada a search de una tool."""
    return [c.kwargs.get("attributes") or [] for c in manager.search.call_args_list]


def a_texto(resultado):
    return json.dumps(resultado, default=str)


class TestAtributosQueNoExisten:
    """Pedir a LDAP un atributo inexistente es un error duro del servidor.

    'dn' no es un atributo: el DN lo devuelve ldap3 aparte, en la clave 'dn'
    de cada entrada (LDAPManager.search ya lo pone). Pedirlo en 'attributes'
    hace que AD conteste invalid attribute type y la tool muere.
    """

    def test_get_user_groups_no_pide_dn_como_atributo(self, mock_ldap_manager):
        mock_ldap_manager.search.return_value = [
            {"dn": "CN=user,OU=Users,DC=test,DC=local",
             "attributes": {"memberOf": ["CN=grp,OU=Groups,DC=test,DC=local"]}}
        ]
        UserTools(mock_ldap_manager).get_user_groups("user")
        for attrs in atributos_pedidos(mock_ldap_manager):
            assert "dn" not in attrs

    def test_get_group_members_no_pide_dn_como_atributo(self, mock_ldap_manager):
        mock_ldap_manager.search.return_value = [
            {"dn": "CN=grp,OU=Groups,DC=test,DC=local",
             "attributes": {"member": ["CN=user,OU=Users,DC=test,DC=local"]}}
        ]
        GroupTools(mock_ldap_manager).get_members("grp")
        for attrs in atributos_pedidos(mock_ldap_manager):
            assert "dn" not in attrs

    def test_get_domain_info_no_pide_functional_level(self, mock_ldap_manager):
        """functionalLevel no existe en el esquema de Active Directory."""
        mock_ldap_manager.search.return_value = [
            {"dn": "DC=test,DC=local", "attributes": {"name": "test", "dc": "test"}}
        ]
        SecurityTools(mock_ldap_manager).get_domain_info()
        for attrs in atributos_pedidos(mock_ldap_manager):
            assert "functionalLevel" not in attrs


class TestCreateOuNoSabeSiYaExiste:
    """La comprobacion "ya existe" nunca podia decir que si.

    Un search con search_scope=BASE sobre un DN que todavia no existe devuelve
    noSuchObject (codigo 32), no una lista vacia. El manager convierte eso en
    LDAPException, con lo que create_ou reventaba siempre ANTES de llegar al
    add: ningun OU se podia crear jamas, ni nuevo ni de otro nombre.
    """

    def test_no_reventa_cuando_el_ou_no_existe_todavia(self, mock_ldap_manager):
        mock_ldap_manager.search.side_effect = LDAPException(
            "LDAPNoSuchObjectResult - 32 - noSuchObject")
        mock_ldap_manager.add.return_value = True

        resultado = OrganizationalUnitTools(mock_ldap_manager).create_ou(
            "Nuevo", "OU=Padre,DC=test,DC=local")

        assert "created successfully" in a_texto(resultado)
        mock_ldap_manager.add.assert_called_once()

    def test_sigue_avanzando_si_el_ou_ya_existe(self, mock_ldap_manager):
        """Que no se haya arreglado de mas: si existe, debe negarse a crearlo."""
        mock_ldap_manager.search.return_value = [
            {"dn": "OU=Nuevo,OU=Padre,DC=test,DC=local", "attributes": {"name": "Nuevo"}}
        ]

        resultado = OrganizationalUnitTools(mock_ldap_manager).create_ou(
            "Nuevo", "OU=Padre,DC=test,DC=local")

        assert "already exists" in a_texto(resultado)
        mock_ldap_manager.add.assert_not_called()

class TestIntervalosDeTiempoEnDominio:
    """get_domain_info revienta siempre que ldap3 devuelve un timedelta.

    _convert_time_interval espera un int en unidades de 100 nanosegundos, pero
    con get_info=ALL (que es como conecta LDAPManager) ldap3 devuelve lockout-
    Duration, maxPwdAge y minPwdAge ya convertidos a datetime.timedelta. La
    division y las comparaciones contra int son un TypeError, y eso tumba la
    tool entera. La de passwords (linea ~350) ya contemplaba el timedelta; aqui
    no.
    """

    def test_acepta_timedelta(self):
        tool = SecurityTools(Mock())
        assert tool._convert_time_interval(timedelta(days=42))["description"] == "42 days"
        assert tool._convert_time_interval(timedelta(hours=2))["description"] == "2 hours"
        assert tool._convert_time_interval(timedelta(minutes=30))["description"] == "30 minutes"
        assert tool._convert_time_interval(timedelta(seconds=30))["description"] == "30 seconds"

    def test_sigue_aceptando_el_int_que_ya_aceptaba(self):
        tool = SecurityTools(Mock())
        assert tool._convert_time_interval(0)["description"] == "Never"
        assert tool._convert_time_interval(18000000000)["description"] == "30 minutes"
        assert tool._convert_time_interval(-18000000000)["description"] == "30 minutes"

    def test_get_domain_info_no_revienta_con_timedelta(self, mock_ldap_manager):
        """El fallo de punta a punta: la tool entera, no solo el helper."""
        mock_ldap_manager.search.return_value = [{
            "dn": "DC=test,DC=local",
            "attributes": {
                "name": "test", "dc": "test",
                "maxPwdAge": timedelta(days=42),
                "minPwdAge": timedelta(days=1),
                "lockoutDuration": timedelta(minutes=30),
                "lockoutThreshold": 10, "minPwdLength": 8,
            },
        }]
        texto = a_texto(SecurityTools(mock_ldap_manager).get_domain_info())
        assert "no supported between instances" not in texto
        assert "42 days" in texto
