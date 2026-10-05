"""Tests de las correcciones de 2026-10-02, la segunda tanda.

Medido contra el dominio real (SRVUCV01/SRVUCV02, DC=UBAGOCV,DC=local):
- Los grupos anidados como miembro de un grupo privilegiado hacian que
  audit_admin_accounts se cayera. La causa no era la tool sino
  LDAPManager.search.
- La busqueda de privilegios se evaluaba con descripcion, y ahi viven los
  falsos positivos: las cuentas de servicio de SQL Server describen al grupo
  como "...access and privileges to be assigned as the log on account for SQL
  Server FullText Search", y por "privileges" el clasificador las daba por
  grupos de administracion.
- Un RID no significa lo mismo en S-1-5-21- (relativo al dominio) que en
  S-1-5-32- (BUILTIN).
"""

import json
from unittest.mock import MagicMock

import pytest
from ldap3.core.exceptions import LDAPException

from active_directory_mcp.core.ldap_manager import LDAPManager
from active_directory_mcp.config.models import ActiveDirectoryConfig, SecurityConfig, PerformanceConfig
from active_directory_mcp.tools.privileged import clasificar, rid_de
from active_directory_mcp.tools.security import SecurityTools


DOMAIN_DN = "DC=test,DC=local"
SID_DOMINIO = "S-1-5-21-1112223333-4445556666-777888999"


@pytest.fixture
def ad_config():
    return ActiveDirectoryConfig(
        server="ldap://test.local:389",
        domain="test.local",
        base_dn=DOMAIN_DN,
        bind_dn="CN=admin,DC=test,DC=local",
        password="password123",
    )


@pytest.fixture
def security_config():
    return SecurityConfig()


@pytest.fixture
def performance_config():
    return PerformanceConfig()


def a_json(tool_result):
    return json.loads(tool_result[0].text)


def grupo(dn, sid, cn="grupo", member=None, description=""):
    return {
        "dn": dn,
        "attributes": {
            "cn": cn,
            "sAMAccountName": cn,
            "displayName": cn,
            "description": description,
            "member": member or [],
            "objectSid": sid,
        },
    }


def usuario(dn, sam="cuenta", uac=512):
    return {
        "dn": dn,
        "attributes": {
            "sAMAccountName": sam,
            "displayName": sam,
            "userAccountControl": uac,
            "lastLogon": 0,
            "pwdLastSet": 0,
            "logonCount": 1,
            "badPwdCount": 0,
        },
    }


# --------------------------------------------------------------------------
# 1. Una busqueda sin resultados no es una busqueda fallida
# --------------------------------------------------------------------------

class TestBusquedaVaciaNoEsFallo:
    """ldap3 devuelve False en un search con scope BASE que no encuentra nada,
    aunque connection.result diga 'success'. LDAPManager lo leia como fallo y
    este except lo traducía a "Search failed: ... description: success", que no
    significa nada."""

    @pytest.fixture
    def ldap_manager(self, ad_config, security_config, performance_config):
        m = LDAPManager(ad_config, security_config, performance_config)
        conn = MagicMock()
        # scope BASE sobre un grupo con filtro (objectClass=user): 0 entradas,
        # result 0 y description 'success'. Es lo que devuelven los grupos
        # anidados de un grupo privilegiado.
        conn.search.return_value = False
        conn.result = {
            "result": 0,
            "description": "success",
            "dn": "",
            "message": "",
            "referrals": None,
            "type": "searchResDone",
            "controls": {},
        }
        conn.entries = []
        m.connect = MagicMock(return_value=conn)
        return m

    def test_base_sin_resultados_devuelve_lista_vacia(self, ldap_manager):
        assert ldap_manager.search(
            search_base="CN=UnGrupo,CN=Users,DC=test,DC=local",
            search_filter="(objectClass=user)",
            search_scope="BASE",
        ) == []

    def test_un_error_de_ldap_real_si_se_sigue_propagando(self, ldap_manager):
        """Lo que no debe pasar: tragarnos tambien los errores de verdad."""
        conn = ldap_manager.connect()
        conn.search.return_value = False
        conn.result = {
            "result": 53,  # unwillingToPerform
            "description": "unwillingToPerform",
            "dn": "",
            "message": "algo va mal",
            "referrals": None,
            "type": "searchResDone",
            "controls": {},
        }
        with pytest.raises(LDAPException):
            ldap_manager.search(
                search_base=DOMAIN_DN,
                search_filter="(objectClass=user)",
                search_scope="BASE",
            )


# --------------------------------------------------------------------------
# 2. La description no decide si un grupo es privilegiado
# --------------------------------------------------------------------------

class TestLaDescripcionNoMarcaPrivilegios:
    """Comprobado en el dominio real: las cuentas de servicio de SQL Server
    describen el grupo con la palabra 'privileges'."""

    def test_una_cuenta_de_sql_no_es_un_grupo_de_administracion(self):
        entrada = grupo(
            "CN=SQLServerFDHostUser$SRV2008VM,CN=Users,DC=test,DC=local",
            f"{SID_DOMINIO}-9999",
            cn="SQLServerFDHostUser$SRV2008VM",
            description=("Members in the group have the required access and "
                         "privileges to be assigned as the log on account for "
                         "SQL Server FullText Search in SQL Server 2008."),
        )
        assert clasificar(entrada) is None

    def test_un_grupo_propio_con_admin_en_el_nombre_sigue_entrando(self):
        entrada = grupo("CN=GSL_AdministradorLocal,CN=Users,DC=test,DC=local",
                        f"{SID_DOMINIO}-3105", cn="GSL_AdministradorLocal")
        veredicto = clasificar(entrada)
        assert veredicto is not None
        assert veredicto["detected_by"] == "name"
        assert veredicto["risk_tier"] == "review"


# --------------------------------------------------------------------------
# 3. El RID depende de la familia del SID
# --------------------------------------------------------------------------

class TestFamiliaDelSid:
    def test_rid_se_lee_del_sid(self):
        assert rid_de(f"{SID_DOMINIO}-512") == 512
        assert rid_de("S-1-5-32-544") == 544
        assert rid_de(b"\x01\x02") is None
        assert rid_de("") is None
        assert rid_de(None) is None

    def test_builtin_544_es_administrators_y_no_domain_admins(self):
        builtin = clasificar(grupo("CN=Administradores,CN=Builtin,DC=test,DC=local",
                                    "S-1-5-32-544", cn="Administradores"))
        assert builtin["well_known_role"] == "Administrators"

    def test_512_en_builtin_no_es_domain_admins(self):
        """S-1-5-21-...-512 es Domain Admins por definicion, pero S-1-5-32-512
        no existe. Si se leyera solo el ultimo numero del SID, cualquier RID
        de la familia equivocado pasaria por un grupo de sistema."""
        entrada = grupo("CN=Cualquiera,CN=Builtin,DC=test,DC=local",
                        "S-1-5-32-512", cn="Cualquiera")
        assert clasificar(entrada) is None

    def test_un_grupo_de_empresa_no_se_inventa_un_rol_por_el_rid(self):
        """RID 3105 no esta en ninguna tabla: el grupo se evalua por nombre y
        se marca como revision, nunca como un rol de sistema."""
        entrada = grupo("CN=GSL_AdministradorLocal,CN=Users,DC=test,DC=local",
                        f"{SID_DOMINIO}-3105", cn="GSL_AdministradorLocal")
        veredicto = clasificar(entrada)
        assert veredicto["detected_by"] == "name"
        assert veredicto["well_known_role"] is None

    def test_operadores_de_configuracion_de_red_se_detecta_por_su_rid(self):
        """S-1-5-32-556 es Network Configuration Operators. Su nombre en
        cualquier idioma no tiene ni 'admin' ni 'privileg'."""
        entrada = grupo("CN=Operadores de configuracion de red,CN=Builtin,DC=test,DC=local",
                        "S-1-5-32-556", cn="Operadores de configuracion de red")
        veredicto = clasificar(entrada)
        assert veredicto["detected_by"] == "rid"
        assert veredicto["well_known_role"] == "Network Configuration Operators"


# --------------------------------------------------------------------------
# 4. Un miembro que es otro grupo no es una cuenta de administracion
# --------------------------------------------------------------------------

class TestMiembrosAnidados:
    def test_un_grupo_anidado_no_cuenta_como_cuenta(self):
        mock = MagicMock()
        mock.ad_config.base_dn = DOMAIN_DN

        def buscar(search_base=None, search_filter=None, **kwargs):
            if "objectClass=group" in (search_filter or ""):
                return [grupo("CN=Admins. del dominio,CN=Users,DC=test,DC=local",
                              f"{SID_DOMINIO}-512", cn="Admins. del dominio",
                              member=["CN=ana,CN=Users,DC=test,DC=local",
                                      "CN=Administradores,CN=Users,DC=test,DC=local"])]
            if search_base == "CN=Administradores,CN=Users,DC=test,DC=local":
                return []  # es un grupo, no un user
            return [usuario(search_base)]

        mock.search.side_effect = buscar

        d = a_json(SecurityTools(mock).audit_admin_accounts())

        assert d["total_admin_accounts"] == 1
        assert d["admin_accounts"][0]["sam_account_name"] == "cuenta"
        # y el modelo tiene que enterarse de que habia un grupo dentro
        assert d["skipped_group_members"] == 1


class TestContadoresDeRiesgo:
    """_calculate_admin_risk_level devuelve 'HIGH'/'MEDIUM'/'LOW' en mayusculas
    y los contadores del payload comparaban con 'high' en minuscula. Salian
    los tres a 0 con 35 cuentas listadas, y el modelo leia que no habia riesgo
    alto en un audit donde las 35 eran HIGH."""

    @pytest.fixture
    def mock(self):
        m = MagicMock()
        m.ad_config.base_dn = DOMAIN_DN

        def buscar(search_base=None, search_filter=None, **kwargs):
            if "objectClass=group" in (search_filter or ""):
                return [grupo("CN=Admins. del dominio,CN=Users,DC=test,DC=local",
                              f"{SID_DOMINIO}-512", cn="Admins. del dominio",
                              member=["CN=ana,CN=Users,DC=test,DC=local",
                                      "CN=bruno,CN=Users,DC=test,DC=local"])]
            if search_base.startswith("CN=ana"):
                return [usuario(search_base, sam="ana", uac=514)]      # deshabilitada
            return [usuario(search_base, sam="bruno", uac=512)]       # limpia

        m.search.side_effect = buscar
        return m

    def test_los_contadores_cuadran_con_las_cuentas(self, mock):
        d = a_json(SecurityTools(mock).audit_admin_accounts())

        assert d["total_admin_accounts"] == 2
        assert d["high_risk_count"] == 1
        assert d["medium_risk_count"] == 0
        assert d["low_risk_count"] == 1
        assert (d["high_risk_count"] + d["medium_risk_count"]
                + d["low_risk_count"]) == d["total_admin_accounts"]

    def test_lo_mas_peligroso_va_primero(self, mock):
        d = a_json(SecurityTools(mock).audit_admin_accounts())

        # por orden alfabetico HIGH < LOW y pasaria por casualidad; aqui se
        # comprueba que el orden es por gravedad y no por el azar del teclado
        assert [a["risk_level"] for a in d["admin_accounts"]] == ["HIGH", "LOW"]