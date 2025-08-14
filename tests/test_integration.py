"""Integration tests for Active Directory MCP server."""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch

from active_directory_mcp.server import ActiveDirectoryMCPServer
from active_directory_mcp.server_http import ActiveDirectoryMCPHTTPServer


@pytest.fixture
def test_config():
    """Test configuration data."""
    return {
        "active_directory": {
            "server": "ldap://test.local:389",
            "domain": "test.local",
            "base_dn": "DC=test,DC=local",
            "bind_dn": "CN=admin,DC=test,DC=local",
            "password": "password123"
        },
        "organizational_units": {
            "users_ou": "OU=Users,DC=test,DC=local",
            "groups_ou": "OU=Groups,DC=test,DC=local",
            "computers_ou": "OU=Computers,DC=test,DC=local",
            "service_accounts_ou": "OU=Service Accounts,DC=test,DC=local"
        }
    }


@pytest.fixture
def config_file(test_config):
    """Temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_config, f)
        config_path = f.name
    
    yield config_path
    
    # Cleanup
    os.unlink(config_path)


class TestServerIntegration:
    """Integration tests for the main server."""
    
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.test_connection')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.connect')
    def test_server_initialization(self, mock_connect, mock_test_connection, config_file):
        """Test server initialization with config file."""
        # Mock successful connection
        mock_test_connection.return_value = {'connected': True, 'server': 'test.local'}
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        
        # Initialize server
        server = ActiveDirectoryMCPServer(config_file)
        
        # Verify initialization
        assert server.config is not None
        assert server.ldap_manager is not None
        assert server.user_tools is not None
        assert server.group_tools is not None
        assert server.computer_tools is not None
        assert server.ou_tools is not None
        assert server.security_tools is not None
        
        # Verify MCP server setup
        assert server.mcp is not None
        
        # Test connection was called
        mock_test_connection.assert_called_once()
    
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.test_connection')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.connect')
    def test_http_server_initialization(self, mock_connect, mock_test_connection, config_file):
        """Test HTTP server initialization."""
        # Mock successful connection
        mock_test_connection.return_value = {'connected': True, 'server': 'test.local'}
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        
        # Initialize HTTP server
        server = ActiveDirectoryMCPHTTPServer(
            config_path=config_file,
            host="127.0.0.1",
            port=8814,
            path="/test-ad-mcp"
        )
        
        # Verify initialization
        assert server.config is not None
        assert server.ldap_manager is not None
        assert server.host == "127.0.0.1"
        assert server.port == 8814
        assert server.path == "/test-ad-mcp"
        
        # Verify tools
        assert server.user_tools is not None
        assert server.group_tools is not None
        assert server.computer_tools is not None
        assert server.ou_tools is not None
        assert server.security_tools is not None
    
    def test_server_with_invalid_config(self):
        """Test server initialization with invalid config."""
        with pytest.raises(FileNotFoundError):
            ActiveDirectoryMCPServer("/nonexistent/config.json")
    
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.test_connection')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.connect')
    def test_server_tools_registration(self, mock_connect, mock_test_connection, config_file):
        """Test that all tools are properly registered."""
        # Mock successful connection
        mock_test_connection.return_value = {'connected': True}
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        
        # Initialize server
        server = ActiveDirectoryMCPServer(config_file)
        
        # Get registered tools (this would require access to FastMCP internals)
        # For now, just verify the server initialized without errors
        assert server.mcp is not None
    
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.test_connection')
    def test_connection_failure_handling(self, mock_test_connection, config_file):
        """Test handling of connection failures during initialization."""
        # Mock connection failure
        mock_test_connection.side_effect = Exception("Connection failed")
        
        # Server should still initialize but log the error
        server = ActiveDirectoryMCPServer(config_file)
        assert server is not None
        
        # Connection test should have been called
        mock_test_connection.assert_called_once()


class TestToolIntegration:
    """Integration tests for tool interactions."""
    
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.test_connection')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.connect')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.search')
    def test_user_tools_integration(self, mock_search, mock_connect, mock_test_connection, config_file):
        """Test user tools integration."""
        # Mock successful connection and search
        mock_test_connection.return_value = {'connected': True}
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        mock_search.return_value = [
            {
                'dn': 'CN=Test User,OU=Users,DC=test,DC=local',
                'attributes': {
                    'sAMAccountName': ['testuser'],
                    'displayName': ['Test User'],
                    'userAccountControl': [512]
                }
            }
        ]
        
        # Initialize server
        server = ActiveDirectoryMCPServer(config_file)
        
        # Test user tools
        result = server.user_tools.list_users()
        assert len(result) == 1
        
        # Verify search was called
        mock_search.assert_called()
    
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.test_connection')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.connect')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.search')
    def test_group_tools_integration(self, mock_search, mock_connect, mock_test_connection, config_file):
        """Test group tools integration."""
        # Mock successful connection and search
        mock_test_connection.return_value = {'connected': True}
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        mock_search.return_value = [
            {
                'dn': 'CN=Test Group,OU=Groups,DC=test,DC=local',
                'attributes': {
                    'sAMAccountName': ['testgroup'],
                    'displayName': ['Test Group'],
                    'groupType': [-2147483646]
                }
            }
        ]
        
        # Initialize server
        server = ActiveDirectoryMCPServer(config_file)
        
        # Test group tools
        result = server.group_tools.list_groups()
        assert len(result) == 1
        
        # Verify search was called
        mock_search.assert_called()
    
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.test_connection')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.connect')
    def test_security_tools_integration(self, mock_connect, mock_test_connection, config_file):
        """Test security tools integration."""
        # Mock successful connection
        mock_test_connection.return_value = {'connected': True}
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        
        # Initialize server
        server = ActiveDirectoryMCPServer(config_file)
        
        # Verify security tools initialized
        assert server.security_tools is not None
        assert hasattr(server.security_tools, 'get_domain_info')
        assert hasattr(server.security_tools, 'get_privileged_groups')
        assert hasattr(server.security_tools, 'audit_admin_accounts')


class TestErrorHandling:
    """Test error handling in integration scenarios."""
    
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.test_connection')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.connect')
    @patch('active_directory_mcp.core.ldap_manager.LDAPManager.search')
    def test_ldap_error_propagation(self, mock_search, mock_connect, mock_test_connection, config_file):
        """Test that LDAP errors are properly handled and propagated."""
        # Mock successful connection but failing operations
        mock_test_connection.return_value = {'connected': True}
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        
        # Mock LDAP exception for search operations
        from ldap3.core.exceptions import LDAPException
        mock_search.side_effect = LDAPException("Test error")
        
        # Initialize server
        server = ActiveDirectoryMCPServer(config_file)
        
        # Test that error is handled gracefully
        result = server.user_tools.list_users()
        assert len(result) == 1
        
        # Parse response to check error handling
        response_text = result[0].text
        response_data = json.loads(response_text)
        assert response_data['success'] == False
        assert 'Test error' in response_data['error']
    
    def test_config_validation_errors(self, test_config):
        """Test configuration validation error handling."""
        # Create invalid config (missing required fields)
        invalid_config = test_config.copy()
        del invalid_config['active_directory']['domain']
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_config, f)
            config_path = f.name
        
        try:
            with pytest.raises(Exception):  # Should raise validation error
                ActiveDirectoryMCPServer(config_path)
        finally:
            os.unlink(config_path)
