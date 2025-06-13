"""Tool registry for dynamic tool discovery and management."""

import importlib
import inspect
import logging
from pathlib import Path
from typing import Dict, List, Optional, Type

from ..tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for discovering and managing tools."""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._tool_classes: Dict[str, Type[BaseTool]] = {}
        
    def discover_tools(self, tools_path: Optional[Path] = None) -> None:
        """Discover and register all tools in the tools directory."""
        if tools_path is None:
            # Default to the tools package
            tools_path = Path(__file__).parent.parent / "tools"
        
        logger.info(f"Discovering tools in {tools_path}")
        
        # Get all Python files in the tools directory
        tool_files = list(tools_path.glob("*.py"))
        logger.debug(f"Found {len(tool_files)} Python files in {tools_path}")
        
        for tool_file in tool_files:
            if tool_file.name.startswith("_") or tool_file.name == "base.py":
                continue
                
            # Try both import paths
            module_names = [
                f"gemini_mcp.tools.{tool_file.stem}",
                f"src.gemini_mcp.tools.{tool_file.stem}"
            ]
            
            module = None
            for module_name in module_names:
                try:
                    logger.debug(f"Attempting to import {module_name}")
                    module = importlib.import_module(module_name)
                    break
                except ImportError:
                    continue
            
            if module is None:
                logger.error(f"Failed to import tool from {tool_file}")
                continue
            
            try:
                
                # Find all classes that inherit from BaseTool
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseTool) and obj != BaseTool:
                        logger.debug(f"Found tool class: {name}")
                        self._register_tool_class(obj)
                        
            except Exception as e:
                logger.error(f"Failed to import tool from {tool_file}: {e}")
    
    def _register_tool_class(self, tool_class: Type[BaseTool]) -> None:
        """Register a tool class."""
        try:
            # Instantiate the tool to get its metadata
            tool_instance = tool_class()
            tool_name = tool_instance.metadata.name
            
            if tool_name in self._tools:
                logger.warning(f"Tool {tool_name} already registered, skipping")
                return
                
            self._tools[tool_name] = tool_instance
            self._tool_classes[tool_name] = tool_class
            logger.info(f"Registered tool: {tool_name}")
            
        except Exception as e:
            logger.error(f"Failed to register tool {tool_class.__name__}: {e}")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool instance by name."""
        return self._tools.get(name)
    
    def get_tool_class(self, name: str) -> Optional[Type[BaseTool]]:
        """Get a tool class by name."""
        return self._tool_classes.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    def get_all_tools(self) -> Dict[str, BaseTool]:
        """Get all registered tools."""
        return self._tools.copy()
    
    def get_mcp_tool_definitions(self) -> List[Dict]:
        """Get MCP tool definitions for all registered tools."""
        definitions = []
        for tool in self._tools.values():
            try:
                definitions.append(tool.get_mcp_definition())
            except Exception as e:
                logger.error(f"Failed to get MCP definition for {tool.metadata.name}: {e}")
        return definitions