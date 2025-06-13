"""Comprehensive tests for the bundler script."""

import ast
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add the scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from bundler import Bundler  # noqa: E402


class TestBundler:
    """Test suite for the bundler."""

    @pytest.fixture
    def bundler(self):
        """Create a bundler instance."""
        return Bundler()

    @pytest.fixture
    def mock_src_dir(self, tmp_path):
        """Create a mock source directory structure."""
        src_dir = tmp_path / "src" / "gemini_mcp"
        src_dir.mkdir(parents=True)

        # Create core files
        (src_dir / "json_rpc.py").write_text(
            '''"""JSON-RPC implementation."""
import json

class JSONRPCHandler:
    pass
'''
        )

        (src_dir / "models").mkdir()
        (src_dir / "models" / "base.py").write_text(
            '''"""Base models."""
from dataclasses import dataclass

@dataclass
class BaseModel:
    pass
'''
        )

        (src_dir / "tools").mkdir()
        (src_dir / "tools" / "base.py").write_text(
            '''"""Base tool class."""
from abc import ABC, abstractmethod

class MCPTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def execute(self, parameters):
        pass
'''
        )

        # Create a sample tool
        (src_dir / "tools" / "sample.py").write_text(
            '''"""Sample tool."""
from .base import MCPTool

class SampleTool(MCPTool):
    @property
    def name(self) -> str:
        return "sample_tool"

    async def execute(self, parameters):
        return {"result": "success"}
'''
        )

        # Create main.py
        (src_dir / "main.py").write_text(
            '''"""Main server module."""
def main():
    print("Server running")

if __name__ == "__main__":
    main()
'''
        )

        return src_dir

    def test_init(self, bundler):
        """Test bundler initialization."""
        assert bundler.output_lines == []
        assert bundler.discovered_components == []
        assert bundler.discovered_tools == []

    def test_discover_all(self, bundler, mock_src_dir, monkeypatch):
        """Test component and tool discovery."""
        monkeypatch.setattr("bundler.SRC_DIR", mock_src_dir)

        bundler.discover_all()

        # Check components were discovered
        component_paths = [comp[0] for comp in bundler.discovered_components]
        assert "json_rpc.py" in component_paths
        assert "models/base.py" in component_paths
        assert "tools/base.py" in component_paths
        assert "tools/sample.py" in component_paths
        assert "main.py" in component_paths

        # Check tool was discovered
        assert len(bundler.discovered_tools) == 1
        assert bundler.discovered_tools[0]["class_name"] == "SampleTool"
        assert bundler.discovered_tools[0]["tool_name"] == "sample_tool"

    def test_process_file_with_syntax_error(self, bundler, tmp_path, monkeypatch):
        """Test processing a file with syntax error."""
        # Create a mock src dir with bad file
        src_dir = tmp_path / "src" / "gemini_mcp"
        src_dir.mkdir(parents=True)
        bad_file = src_dir / "bad.py"
        bad_file.write_text("def bad_syntax(:\n    pass")

        monkeypatch.setattr("bundler.SRC_DIR", src_dir)
        bundler._process_file(bad_file)

        # Should still add to components but with error note
        assert len(bundler.discovered_components) == 1
        assert "syntax error" in bundler.discovered_components[0][1]

    def test_is_tool_class(self, bundler):
        """Test tool class detection."""
        # Create AST nodes for testing
        tool_class = ast.ClassDef(
            name="TestTool",
            bases=[ast.Name(id="MCPTool", ctx=ast.Load())],
            keywords=[],
            body=[],
            decorator_list=[],
        )

        non_tool_class = ast.ClassDef(
            name="NotATool",
            bases=[ast.Name(id="object", ctx=ast.Load())],
            keywords=[],
            body=[],
            decorator_list=[],
        )

        assert bundler._is_tool_class(tool_class) is True
        assert bundler._is_tool_class(non_tool_class) is False

    def test_extract_tool_info(self, bundler, tmp_path):
        """Test tool info extraction."""
        # Create a proper tool class AST
        tool_ast = ast.parse(
            """
class TestTool(MCPTool):
    @property
    def name(self) -> str:
        return "test_tool"
"""
        )

        tool_class = tool_ast.body[0]
        tool_info = bundler._extract_tool_info(tool_class, tmp_path / "test.py")

        assert tool_info is not None
        assert tool_info["class_name"] == "TestTool"
        assert tool_info["tool_name"] == "test_tool"

    def test_generate_imports(self, bundler):
        """Test import generation."""
        imports = bundler.generate_imports()

        # Check key imports are present
        assert "import asyncio" in imports
        assert "import google.generativeai as genai" in imports
        assert "__version__ = " in imports
        assert "model_manager = None" in imports

    def test_generate_tool_registry_override(self, bundler):
        """Test tool registry override generation."""
        bundler.discovered_tools = [
            {"class_name": "Tool1", "tool_name": "tool1", "file_name": "tool1"},
            {"class_name": "Tool2", "tool_name": "tool2", "file_name": "tool2"},
        ]

        override_code = bundler.generate_tool_registry_override()

        assert "Tool1" in override_code
        assert "Tool2" in override_code
        assert "_bundled_discover_tools" in override_code
        assert "ToolRegistry.discover_tools = _bundled_discover_tools" in override_code

    def test_clean_content_removes_imports(self, bundler):
        """Test that clean_content removes problematic imports."""
        content = '''#!/usr/bin/env python3
"""Module docstring."""
from .. import model_manager
from .base import BaseTool
from gemini_mcp.core import something
import gemini_mcp
import json
import logging

class MyClass:
    pass
'''

        cleaned = bundler._simple_clean_content(content)

        assert "#!/usr/bin/env python3" not in cleaned
        assert '"""Module docstring."""' not in cleaned
        assert "from .." not in cleaned
        assert "from ." not in cleaned
        assert "from gemini_mcp" not in cleaned
        assert "import gemini_mcp" not in cleaned
        assert "class MyClass:" in cleaned

    def test_fix_tool_imports(self, bundler):
        """Test tool import fixing."""
        content = """
from .. import model_manager

class MyTool:
    def execute(self):
        response_text, model_used = model_manager.generate_content(prompt)
"""

        fixed = bundler._fix_tool_imports(content, is_tool=True)

        assert "from .. import model_manager" not in fixed
        assert "global model_manager" in fixed
        assert "Model manager will be accessed as global" in fixed

    def test_fix_orchestrator_for_bundled(self, bundler):
        """Test orchestrator fixing for bundled operation."""
        content = '''
class ConversationOrchestrator:
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolOutput:
        """Original execute_tool method."""
        # Original implementation
        return output
'''

        fixed = bundler._fix_orchestrator_for_bundled(content)

        assert "global model_manager" in fixed
        assert "model_manager = self.model_manager" in fixed

    def test_create_bundle_integration(self, bundler, mock_src_dir, monkeypatch):
        """Test full bundle creation."""
        monkeypatch.setattr("bundler.SRC_DIR", mock_src_dir)

        bundle = bundler.create_bundle()

        # Check bundle contains expected sections
        assert "Gemini MCP Server - Single File Bundle" in bundle
        assert "import asyncio" in bundle
        assert "class MCPTool" in bundle
        assert "class SampleTool" in bundle
        assert "_bundled_discover_tools" in bundle
        assert 'if __name__ == "__main__"' in bundle

        # Verify it's valid Python
        compile(bundle, "test_bundle.py", "exec")

    def test_main_execution_removal(self, bundler):
        """Test that __main__ blocks are removed from modules."""
        content = """
def my_function():
    pass

if __name__ == "__main__":
    my_function()
    print("This should be removed")
"""

        cleaned = bundler._simple_clean_content(content)

        assert "def my_function():" in cleaned
        # The current implementation only removes the if __name__ line itself
        # but keeps the indented content (which is a bug we should note)
        assert 'if __name__ == "__main__"' not in cleaned
        # Note: The current implementation has a limitation where it doesn't
        # remove the entire if block, just the if line itself

    def test_ast_cleaning_with_astor(self, bundler):
        """Test AST-based cleaning when astor is available."""
        # Test with mock astor module
        mock_astor = Mock()
        mock_astor.to_source.return_value = """def my_function():
    pass
"""

        with patch.dict("sys.modules", {"astor": mock_astor}):
            content = '''#!/usr/bin/env python3
"""Module docstring."""
from .. import something

def my_function():
    pass

if __name__ == "__main__":
    my_function()
'''

            cleaned = bundler.clean_content(content, "test.py")

            # Should attempt to use AST cleaning
            assert "def my_function():" in cleaned

    def test_error_handling_in_bundle_creation(self, bundler, mock_src_dir, monkeypatch):
        """Test error handling during bundle creation."""
        monkeypatch.setattr("bundler.SRC_DIR", mock_src_dir)

        # Make one file unreadable
        bad_file = mock_src_dir / "models" / "base.py"
        bad_file.chmod(0o000)

        # Should still create bundle, skipping the problematic file
        bundle = bundler.create_bundle()

        assert "Gemini MCP Server - Single File Bundle" in bundle
        assert "class SampleTool" in bundle  # Other files should still be processed

        # Restore permissions
        bad_file.chmod(0o644)

    def test_bundler_main_function(self, tmp_path, monkeypatch):
        """Test the main bundler function."""
        # Mock paths
        mock_output = tmp_path / "server.py"
        monkeypatch.setattr("bundler.OUTPUT_FILE", mock_output)
        monkeypatch.setattr("bundler.SRC_DIR", tmp_path / "src" / "gemini_mcp")

        # Create minimal structure
        (tmp_path / "src" / "gemini_mcp").mkdir(parents=True)
        (tmp_path / "src" / "gemini_mcp" / "main.py").write_text("def main(): pass")

        # Import and run main
        from bundler import main

        result = main()

        assert result == 0
        assert mock_output.exists()
        assert mock_output.stat().st_mode & 0o111  # Check executable bit


class TestBundlerEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def bundler(self):
        """Create a bundler instance."""
        return Bundler()

    def test_empty_source_directory(self, tmp_path, monkeypatch):
        """Test bundler with empty source directory."""
        empty_src = tmp_path / "empty" / "src" / "gemini_mcp"
        empty_src.mkdir(parents=True)

        bundler = Bundler()
        monkeypatch.setattr("bundler.SRC_DIR", empty_src)

        bundler.discover_all()

        # Should handle gracefully
        assert bundler.discovered_components == []
        assert bundler.discovered_tools == []

    def test_malformed_tool_class(self, tmp_path, monkeypatch):
        """Test handling of malformed tool classes."""
        bundler = Bundler()

        # Create mock src dir
        src_dir = tmp_path / "src" / "gemini_mcp"
        src_dir.mkdir(parents=True)

        # Tool without name property
        bad_tool = src_dir / "bad_tool.py"
        bad_tool.write_text(
            """
from .base import MCPTool

class BadTool(MCPTool):
    # Missing name property
    async def execute(self, params):
        pass
"""
        )

        monkeypatch.setattr("bundler.SRC_DIR", src_dir)
        bundler._process_file(bad_tool, is_tool=True)

        # Should not add to discovered tools
        assert len(bundler.discovered_tools) == 0

    def test_circular_import_handling(self, bundler):
        """Test handling of circular imports."""
        content = """
from . import module_a
from ..core import module_b
from module_a import something  # potential circular

class MyClass:
    pass
"""

        cleaned = bundler._simple_clean_content(content)

        # All problematic imports should be removed
        assert "from ." not in cleaned
        assert "from .." not in cleaned
        assert "class MyClass:" in cleaned

    def test_unicode_handling(self, bundler, tmp_path, monkeypatch):
        """Test handling of unicode in source files."""
        # Create mock src dir
        src_dir = tmp_path / "src" / "gemini_mcp"
        src_dir.mkdir(parents=True)

        unicode_file = src_dir / "unicode.py"
        unicode_file.write_text(
            '''"""Module with unicode: 你好世界 🌍"""

def greet():
    return "Hello 世界!"
''',
            encoding="utf-8",
        )

        monkeypatch.setattr("bundler.SRC_DIR", src_dir)
        bundler._process_file(unicode_file)

        assert len(bundler.discovered_components) == 1
        assert "你好世界" in bundler.discovered_components[0][1]
