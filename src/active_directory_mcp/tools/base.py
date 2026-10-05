"""Base class for Active Directory tools."""

import json
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from mcp.types import TextContent as Content
from ldap3.core.exceptions import LDAPException

from ..core.ldap_manager import LDAPManager
from ..core.logging import get_logger, log_ldap_operation


class BaseTool(ABC):
    """Base class for all Active Directory tools."""
    
    def __init__(self, ldap_manager: LDAPManager):
        """
        Initialize base tool.
        
        Args:
            ldap_manager: LDAP manager instance
        """
        self.ldap = ldap_manager
        self.logger = get_logger(self.__class__.__name__)

    def _default_ou(self, attribute: str, fallback: str) -> str:
        """Devuelve el OU por defecto para crear objetos.

        Los OU se configuran en Config.organizational_units y llegan aqui
        como ldap_manager.ou_config. No estan en ldap_manager.ad_config, que
        es solo la seccion ActiveDirectoryConfig: leerlos de ahi daba
        AttributeError y hacia fallar create_group y create_computer.

        Args:
            attribute: nombre del campo ('users_ou', 'groups_ou', ...)
            fallback: contenedor a usar si no hay config de OUs
        """
        ou_config = getattr(self.ldap, "ou_config", None)
        value = getattr(ou_config, attribute, None) if ou_config is not None else None
        if not isinstance(value, str) or not value:
            return fallback
        return value
    
    def _serialize_datetime(self, obj):
        """Helper function to serialize datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {key: self._serialize_datetime(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_datetime(item) for item in obj]
        else:
            return obj
    
    def _format_response(self, data: Any, operation: str = "operation") -> List[Content]:
        """
        Format response data for MCP.
        
        Args:
            data: Data to format
            operation: Operation name for logging
            
        Returns:
            List of MCP content objects
        """
        try:
            # Serialize datetime objects before JSON conversion
            serialized_data = self._serialize_datetime(data)
            
            if isinstance(serialized_data, dict):
                formatted_data = json.dumps(serialized_data, indent=2, ensure_ascii=False)
            elif isinstance(serialized_data, list):
                formatted_data = json.dumps(serialized_data, indent=2, ensure_ascii=False)
            else:
                formatted_data = str(serialized_data)
            
            return [Content(type="text", text=formatted_data)]
            
        except Exception as e:
            self.logger.error(f"Error formatting response for {operation}: {e}")
            error_response = {
                "error": f"Failed to format response: {str(e)}",
                "operation": operation
            }
            return [Content(type="text", text=json.dumps(error_response, indent=2))]
    
    def _handle_ldap_error(self, e: Exception, operation: str, dn: str = "") -> List[Content]:
        """
        Handle LDAP errors and format error response.
        
        Args:
            e: Exception that occurred
            operation: Operation that failed
            dn: Distinguished name (if applicable)
            
        Returns:
            List of MCP content objects with error information
        """
        error_msg = str(e)
        
        if isinstance(e, LDAPException):
            self.logger.error(f"LDAP error during {operation}: {error_msg}")
        else:
            self.logger.error(f"Unexpected error during {operation}: {error_msg}")
        
        # Log for audit
        if dn:
            log_ldap_operation(operation, dn, False, error_msg)
        
        error_response = {
            "success": False,
            "error": error_msg,
            "operation": operation,
            "type": type(e).__name__
        }
        
        if dn:
            error_response["dn"] = dn
        
        return [Content(type="text", text=json.dumps(error_response, indent=2))]
    
    def _validate_dn(self, dn: str) -> bool:
        """
        Validate Distinguished Name format.
        
        Args:
            dn: Distinguished name to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not dn or not isinstance(dn, str):
            return False
        
        # Basic DN validation - should contain at least one component
        dn_parts = dn.split(',')
        for part in dn_parts:
            part = part.strip()
            if '=' not in part:
                return False
            
            key, value = part.split('=', 1)
            if not key.strip() or not value.strip():
                return False
        
        return True
    
    def _build_dn(self, name: str, ou: str) -> str:
        """
        Build Distinguished Name from name and organizational unit.
        
        Args:
            name: Object name (CN)
            ou: Organizational unit DN
            
        Returns:
            Complete DN
        """
        return f"CN={name},{ou}"
    
    def _success_response(self, message: str, data: Optional[Dict[str, Any]] = None) -> List[Content]:
        """
        Create success response.
        
        Args:
            message: Success message
            data: Optional additional data
            
        Returns:
            List of MCP content objects
        """
        response = {
            "success": True,
            "message": message
        }
        
        if data:
            response.update(data)
        
        return [Content(type="text", text=json.dumps(response, indent=2, ensure_ascii=False))]
    
    def _escape_ldap_filter(self, value: str) -> str:
        """
        Escape special characters in LDAP filter values.

        Args:
            value: Value to escape

        Returns:
            Escaped value
        """
        # Escape special LDAP filter characters
        escape_chars = {
            '*': r'\2a',
            '(': r'\28',
            ')': r'\29',
            '\\': r'\5c',
            '\x00': r'\00'
        }

        for char, escaped in escape_chars.items():
            value = value.replace(char, escaped)

        return value

    def _get_attr_value(self, attributes: Dict[str, Any], attr_name: str, default: Any = None) -> Any:
        """
        Safely get an attribute value from LDAP attributes dict.

        LDAP attributes can be returned as:
        - A single value (int, str, bytes, datetime)
        - A list of values
        - None if not present

        This method normalizes access to always return a single value (first element if list).

        Args:
            attributes: Dictionary of LDAP attributes
            attr_name: Name of attribute to get
            default: Default value if attribute not found

        Returns:
            Single attribute value or default
        """
        value = attributes.get(attr_name)

        if value is None:
            return default

        # If it's a list, return the first element
        if isinstance(value, (list, tuple)):
            return value[0] if value else default

        # Otherwise return the value directly
        return value

    def _get_attr_list(self, attributes: Dict[str, Any], attr_name: str, default: Any = None) -> list:
        """
        Safely get an attribute value as a list from LDAP attributes dict.

        LDAP attributes can be returned as:
        - A single value (int, str, bytes, datetime)
        - A list of values
        - None if not present

        This method normalizes access to always return a list.

        Args:
            attributes: Dictionary of LDAP attributes
            attr_name: Name of attribute to get
            default: Default value if attribute not found (will be wrapped in list)

        Returns:
            List of attribute values
        """
        value = attributes.get(attr_name)

        if value is None:
            return [default] if default is not None else []

        # If it's already a list, return it
        if isinstance(value, (list, tuple)):
            return list(value)

        # Otherwise wrap in a list
        return [value]

    def _convert_filetime_to_datetime(self, filetime) -> datetime:
        """
        Convert Windows FILETIME to datetime.

        ldap3 decodes FILETIME attributes (lastLogon, pwdLastSet, ...) as
        datetime.datetime in some entries and as int FILETIME in others.
        This helper accepts both representations.

        Args:
            filetime: int/float FILETIME or datetime

        Returns:
            Naive datetime
        """
        # If already datetime, return as is
        if isinstance(filetime, datetime):
            return filetime

        # Convert integer FILETIME (100-nanosecond intervals since January 1, 1601)
        if isinstance(filetime, (int, float)) and filetime != 0:
            # Rango valido de FILETIME para AD: desde 1601 hasta ~2100.
            # Un FILETIME que produce una fecha fuera de este rango es un valor
            # corrupto (p.ej. maximo de 64 bits 9223372036854775807 que daria
            # el ano 30828, o un valor futuro absurdo). Se trata como
            # "nunca logueado" en lugar de propagar fechas imposibles.
            MAX_VALID_FILETIME = 157455360000000000  # ~ ano 2100
            if filetime > MAX_VALID_FILETIME:
                return datetime(1601, 1, 1)
            try:
                return datetime(1601, 1, 1) + timedelta(microseconds=int(filetime // 10))
            except (OverflowError, ValueError, OSError):
                # FILETIME corrupto o fuera del rango representable: tratar como
                # "nunca logueado" en lugar de propagar y tumbar la operacion.
                return datetime(1601, 1, 1)

        # Default fallback (value 0 or missing)
        return datetime.now()

    def _convert_datetime_to_filetime(self, dt: datetime) -> int:
        """
        Convert datetime to Windows FILETIME.

        Args:
            dt: Datetime (naive or timezone-aware)

        Returns:
            FILETIME integer (100-nanosecond intervals since January 1, 1601)
        """
        # If dt is timezone-aware, convert to UTC and make naive
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

        epoch = datetime(1601, 1, 1)
        delta = dt - epoch
        return int(delta.total_seconds() * 10000000)

    def _get_days_since_last_logon(self, attributes: Dict[str, Any]) -> Optional[int]:
        """
        Get number of days since last logon.

        Args:
            attributes: LDAP attributes dict (lastLogon may be int FILETIME
                or datetime, as returned by ldap3)

        Returns:
            Days since last logon, or None if never logged on / unknown
        """
        last_logon = self._get_attr_value(attributes, 'lastLogon', 0)
        if last_logon == 0 or last_logon is None:
            return None

        try:
            last_logon_date = self._convert_filetime_to_datetime(last_logon)
            return (datetime.now() - last_logon_date).days
        except:
            return None

    def _normalize_last_logon(self, last_logon: Any) -> Optional[datetime]:
        """
        Normalize a lastLogon value to a naive UTC datetime.

        ldap3 decodes FILETIME attributes (lastLogon, pwdLastSet, ...) as
        datetime.datetime in some entries and as int FILETIME in others.
        Normalize both representations to a naive UTC datetime.

        Args:
            last_logon: int/float FILETIME, datetime, or 0/None

        Returns:
            Naive UTC datetime, or None when the computer has never logged
            on (value 0 or missing)
        """
        if isinstance(last_logon, datetime):
            dt = last_logon
            # ldap3 decodifica el FILETIME maximo (9223372036854775807) como
            # datetime(9999, 12, 31) - un valor imposible para una cuenta real.
            # Cualquier fecha mas alla de ~2100 es corrupta: tratar como "nunca".
            if dt.year > 2100:
                return None
        elif isinstance(last_logon, (int, float)) and last_logon > 0:
            try:
                dt = self._convert_filetime_to_datetime(last_logon)
            except (OverflowError, ValueError, OSError):
                # Valor corrupto o fuera de rango: tratar como "nunca logueado".
                return None
            if dt.year > 2100:
                return None
        else:
            return None

        # Sentinel de valor corrupto: _convert_filetime_to_datetime devuelve
        # datetime(1601, 1, 1) cuando el FILETIME excede el rango valido.
        # En AD, 1601-01-01 es semanticamente "nunca logueado" (epoch FILETIME).
        if dt == datetime(1601, 1, 1):
            return None

        # Ensure naive UTC for consistent comparison with cutoff dates
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @abstractmethod
    def get_schema_info(self) -> Dict[str, Any]:
        """
        Get schema information for this tool's operations.
        
        Returns:
            Dictionary with schema information
        """
        pass
