"""
MCP (Model Context Protocol) Implementation for DIGIMON
"""

from .mcp_server import DigimonMCPServer, MCPRequest, MCPResponse, MCPError, MCPTool
from .mcp_client import MCPClientManager, MCPConnection, MCPServerInfo
from .mcp_client_enhanced import (
    EnhancedMCPClientManager, ConnectionState, ConnectionMetrics,
    ServerHealth, RequestCache, LoadBalancer, EnhancedMCPConnection
)
from .shared_context import SharedContextStore, SessionContext

__all__ = [
    'DigimonMCPServer',
    'MCPRequest',
    'MCPResponse',
    'MCPError',
    'MCPTool',
    'MCPClientManager',
    'MCPConnection',
    'MCPServerInfo',
    'EnhancedMCPClientManager',
    'ConnectionState',
    'ConnectionMetrics',
    'ServerHealth',
    'RequestCache',
    'LoadBalancer',
    'EnhancedMCPConnection',
    'SharedContextStore',
    'SessionContext',
    'DigimonToolServer'
]


def __getattr__(name: str):
    """Lazy-load heavyweight MCP server symbols on demand.

    Importing ``Core.MCP.tool_consolidation`` or the lightweight MCP client/server
    primitives should not force legacy tool-server imports and their optional
    runtime dependencies into the default path.
    """
    if name == "DigimonToolServer":
        from .digimon_mcp_server import DigimonToolServer

        return DigimonToolServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
