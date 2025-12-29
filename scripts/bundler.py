#!/usr/bin/env python3
"""
Bundler that creates a working single-file server from modular components.
Works with the modular architecture to combine all components into a single deployable file.
"""

import ast
import logging
import re
import sys
import textwrap
from pathlib import Path
from typing import Dict, Optional

# Configure logging only if running as main script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "council"
OUTPUT_FILE = PROJECT_ROOT / "server.py"


class Bundler:
    """Creates a bundled server.py using dynamic discovery for the modular architecture."""

    def __init__(self):
        self.output_lines = []
        self.discovered_components = []  # List of (rel_path, docstring) tuples
        self.discovered_tools = []  # List of tool info dicts

    def discover_all(self) -> None:
        """Discovers all components and tools in a single pass."""
        # Define the order for core components. This order is critical to ensure
        # base classes and core modules are defined before they are used by other components.
        ordered_paths = [
            "json_rpc.py",  # Core JSON-RPC implementation
            "providers/base.py",  # Provider base classes (new in v4)
            "providers/openrouter.py",  # OpenRouter implementation (new in v4)
            "discovery/model_cache.py",  # Model caching (new in v4)
            "discovery/model_filter.py",  # Model filtering (new in v4)
            "manager.py",  # New OpenRouter-based ModelManager (v4)
            "models/base.py",  # Legacy models base (for backwards compat)
            "models/manager.py",  # Legacy DualModelManager (for backwards compat)
            "models/memory.py",  # Memory models
            "services/cache.py",  # Cache service
            "services/memory.py",  # Memory service
            "tools/base.py",  # Tool base class must come before tool implementations
            "core/registry.py",  # Registry needs tool base
            "core/orchestrator.py",  # Orchestrator uses registry
            "protocols/debate.py",  # Protocols come last
            "main.py",  # Main server class (not server.py!)
        ]

        # Process ordered components first
        for rel_path in ordered_paths:
            file_path = SRC_DIR / rel_path
            if file_path.exists():
                self._process_file(file_path, is_tool=False)
            else:
                # Skip warning for optional legacy files
                if rel_path not in ["models/base.py", "models/manager.py", "models/memory.py"]:
                    logger.warning(f"Core component not found: {file_path}")

        # Then discover and process tools
        tools_dir = SRC_DIR / "tools"
        if tools_dir.exists():
            for tool_file in sorted(tools_dir.glob("*.py")):
                if tool_file.name not in ["__init__.py", "base.py"]:
                    self._process_file(tool_file, is_tool=True)
        else:
            logger.error(f"Tools directory not found: {tools_dir}")

    def _process_file(self, file_path: Path, is_tool: bool = False) -> None:
        """Parses a single file to extract components and tool information."""
        rel_path = file_path.relative_to(SRC_DIR).as_posix()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
                tree = ast.parse(source, filename=str(file_path))

                # Get component info (docstring)
                docstring = ast.get_docstring(tree) or "No description available"
                self.discovered_components.append((rel_path, docstring.strip()))

                # If it's a tool file, look for tool classes
                if is_tool:
                    self._extract_tools_from_ast(tree, file_path)

        except SyntaxError as e:
            logger.error(f"Syntax error in {file_path}: {e}")
            self.discovered_components.append((rel_path, "Component file (syntax error)"))
        except OSError as e:
            logger.error(f"Failed to read {file_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing {file_path}: {e}")

    def _extract_tools_from_ast(self, tree: ast.AST, file_path: Path) -> None:
        """Extract tool classes from an AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if self._is_tool_class(node):
                    tool_info = self._extract_tool_info(node, file_path)
                    if tool_info:
                        self.discovered_tools.append(tool_info)
                        logger.info(
                            f"Discovered tool: {tool_info['class_name']} ({tool_info['tool_name']})"
                        )

    def _is_tool_class(self, node: ast.ClassDef) -> bool:
        """Check if a class definition is a tool class."""
        # Check direct base classes
        base_names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                # Handle cases like module.BaseTool
                base_names.append(base.attr)

        return any(base in ["BaseTool", "MCPTool"] for base in base_names)

    def _extract_tool_info(self, node: ast.ClassDef, file_path: Path) -> Optional[Dict[str, str]]:
        """Extract tool information from a class definition."""
        tool_name = None

        # Look for the name property
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "name":
                # Check if it's a property
                has_property_decorator = any(
                    isinstance(d, ast.Name) and d.id == "property" for d in item.decorator_list
                )

                if has_property_decorator:
                    # Find the return statement
                    for stmt in item.body:
                        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant):
                            tool_name = stmt.value.value
                            break

        if tool_name:
            return {"class_name": node.name, "tool_name": tool_name, "file_name": file_path.stem}
        else:
            logger.warning(f"Tool class {node.name} in {file_path} has no name property")
            return None

    def generate_imports(self) -> str:
        """Generate the import section for the bundled file."""
        imports = textwrap.dedent(
            """
            #!/usr/bin/env python3
            # flake8: noqa
            \"\"\"
            Council MCP Server - Single File Bundle
            MCP server that enables Claude to collaborate with multiple AI models via OpenRouter.
            This version combines all modular components into a single deployable file.
            Generated by bundler.
            \"\"\"

            import asyncio
            import collections
            import hashlib
            import importlib
            import inspect
            import json
            import logging
            import os
            import sys
            import time
            from abc import ABC, abstractmethod
            from collections import OrderedDict, deque
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
            from dataclasses import dataclass, field
            from datetime import datetime
            from enum import Enum
            from pathlib import Path
            from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

            # OpenRouter uses OpenAI-compatible API
            try:
                from openai import OpenAI
            except ImportError:
                OpenAI = None

            # Keep google SDK as optional fallback
            try:
                import google.generativeai as genai
                from google.api_core import exceptions as google_exceptions
            except ImportError:
                genai = None
                google_exceptions = None

            # HTTP client for model discovery
            try:
                import httpx
            except ImportError:
                httpx = None

            try:
                from dotenv import load_dotenv
            except ImportError:
                load_dotenv = None

            # Create logger without configuring (main() will configure)
            logger = logging.getLogger("council-mcp")

            __version__ = "4.0.0"

            # Global model manager instance (will be set by server)
            model_manager = None

            # Create council namespace for bundled mode
            class _Council:
                _server_instance = None
            council = _Council()
        """
        ).strip()

        return imports

    def generate_tool_registry_override(self) -> str:
        """Generate code to override ToolRegistry for bundled operation."""
        tool_class_names = [tool["class_name"] for tool in self.discovered_tools]
        tool_list = ",\n        ".join(tool_class_names)

        override_code = textwrap.dedent(
            f"""
# ========== Tool Registry Override for Bundled Operation ==========

# Store the bundled tool classes globally
BUNDLED_TOOL_CLASSES = [
    {tool_list}
]

# Override the ToolRegistry's discover_tools method for bundled operation
def _bundled_discover_tools(self, tools_path: Optional[Path] = None) -> None:
    \"\"\"Discover and register all tools - bundled version.\"\"\"
    # Clear any existing tools to ensure clean state
    self._tools.clear()
    self._tool_classes.clear()

    logger.info("Registering bundled tools")

    for tool_class in BUNDLED_TOOL_CLASSES:
        try:
            tool_instance = tool_class()
            tool_name = tool_instance.name  # Use property access

            self._tools[tool_name] = tool_instance
            self._tool_classes[tool_name] = tool_class
            logger.info(f"Registered tool: {{tool_name}}")

        except Exception as e:
            logger.error(f"Failed to register tool {{tool_class.__name__}}: {{e}}")

    logger.info(f"Registered {{len(self._tools)}} tools in bundled mode")

# Function to apply the override - will be called from main()
def _apply_tool_registry_override():
    \"\"\"Apply the bundled tool registry override.\"\"\"
    ToolRegistry.discover_tools = _bundled_discover_tools
        """
        ).strip()

        return override_code

    def clean_content(self, content: str, rel_path: str) -> str:
        """Clean module content for bundling using AST parsing."""
        try:
            # Parse the content to ensure it's valid Python
            tree = ast.parse(content)

            # For main.py, we need special handling
            if rel_path == "main.py":
                # Remove the if __name__ == "__main__" block since we'll add our own
                class MainBlockRemover(ast.NodeTransformer):
                    def visit_If(self, node):
                        # Check if this is a __name__ == "__main__" check
                        if (
                            isinstance(node.test, ast.Compare)
                            and isinstance(node.test.left, ast.Name)
                            and node.test.left.id == "__name__"
                            and len(node.test.comparators) == 1
                            and isinstance(node.test.comparators[0], ast.Constant)
                            and node.test.comparators[0].value == "__main__"
                        ):
                            return None  # Remove this node
                        return self.generic_visit(node)

                tree = MainBlockRemover().visit(tree)

            # Convert back to source
            import astor

            cleaned = astor.to_source(tree)

            # Remove imports that won't work in bundled version
            lines = cleaned.split("\n")
            filtered_lines = []

            for line in lines:
                # Skip relative imports
                if line.strip().startswith("from .") or line.strip().startswith("from .."):
                    continue
                # Skip imports from our own package
                if "from council" in line or "from src.council" in line:
                    continue
                if "import council" in line or "import src.council" in line:
                    continue
                # Skip old gemini_mcp imports
                if "from gemini_mcp" in line or "from src.gemini_mcp" in line:
                    continue
                if "import gemini_mcp" in line or "import src.gemini_mcp" in line:
                    continue

                filtered_lines.append(line)

            return "\n".join(filtered_lines)

        except Exception as e:
            logger.warning(
                f"Failed to use AST cleaning for {rel_path}, falling back to text processing: {e}"
            )
            # Fallback to simple text processing
            return self._simple_clean_content(content)

    def _fix_tool_imports(self, content: str, is_tool: bool) -> str:
        """Fix tool imports for bundled operation."""
        if not is_tool:
            return content

        # Look for the model manager access block and replace it
        lines = content.split("\n")
        new_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Check if this is the start of the model manager access block
            if "# Get model manager from server instance" in line:
                # Skip lines until we find the generate_content call
                new_lines.append("            # Access global model manager in bundled version")
                new_lines.append("            global model_manager")
                new_lines.append("")

                # Skip ahead until we find the response_text line
                while (
                    i < len(lines)
                    and "response_text, model_used = model_manager.generate_content" not in lines[i]
                ):
                    i += 1
                # Now include the generate_content line
                if i < len(lines):
                    new_lines.append(lines[i])
            else:
                new_lines.append(line)
            i += 1

        content = "\n".join(new_lines)

        # Also handle any remaining import attempts
        content = content.replace(
            "from .. import model_manager",
            "# Model manager will be accessed as global in bundled version",
        )
        content = content.replace(
            "from .. import _server_instance",
            "# Server instance access not needed in bundled version",
        )

        return content

    def _fix_orchestrator_for_bundled(self, content: str) -> str:
        """Fix orchestrator to work with bundled tools."""
        if "class ConversationOrchestrator" not in content:
            return content

        # Replace the execute_tool method to handle bundled tools
        new_execute_tool = '''
    async def execute_tool(
        self, tool_name: str, parameters: Dict[str, Any], request_id: Optional[str] = None
    ) -> ToolOutput:
        """Execute a single tool with proper context injection."""

        # Check cache first
        cache_key = self.cache.create_key(tool_name, parameters)
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for {tool_name}")
            return cached_result

        # Get the tool
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            return ToolOutput(
                success=False, error=f"Unknown tool: {tool_name}"
            )

        # For bundled operation, set global model manager
        global model_manager
        model_manager = self.model_manager

        # Execute the tool
        try:
            output = await tool.execute(parameters)
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            output = ToolOutput(success=False, error=str(e))

        # Cache successful results
        if output.success:
            self.cache.set(cache_key, output)

        # Store in execution history
        self.execution_history.append(output)

        return output'''

        # Find and replace the execute_tool method
        pattern = r"(async def execute_tool\(.*?\) -> ToolOutput:.*?)(return output)"
        replacement = new_execute_tool.strip()

        content = re.sub(pattern, replacement, content, flags=re.DOTALL)

        return content

    def _simple_clean_content(self, content: str):
        """Simple text-based content cleaning as fallback."""
        lines = content.split("\n")
        cleaned_lines = []

        # Track if we're at the beginning of the file
        seen_code = False
        in_module_docstring = False
        docstring_delimiter = None

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip shebang
            if i == 0 and line.startswith("#!"):
                continue

            # Handle module-level docstrings
            if not seen_code and not in_module_docstring:
                # Check if this starts a docstring
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_delimiter = '"""' if stripped.startswith('"""') else "'''"
                    # Check if it's a single-line docstring
                    if stripped.count(docstring_delimiter) >= 2:
                        # Single line module docstring - skip it
                        continue
                    else:
                        # Multi-line docstring starts
                        in_module_docstring = True
                        continue
                elif stripped and not stripped.startswith("#"):
                    # This is the first real code
                    seen_code = True

            # If we're in a module docstring, skip until the end
            if in_module_docstring:
                if docstring_delimiter in line:
                    in_module_docstring = False
                    docstring_delimiter = None
                continue

            # Skip imports
            if stripped.startswith("from .") or stripped.startswith("from .."):
                continue
            if "from council" in line or "from src.council" in line:
                continue
            if stripped.startswith("import council") or stripped.startswith("import src.council"):
                continue
            # Skip old gemini_mcp imports
            if "from gemini_mcp" in line or "from src.gemini_mcp" in line:
                continue
            if stripped.startswith("import gemini_mcp") or stripped.startswith(
                "import src.gemini_mcp"
            ):
                continue

            # Skip duplicate logger and module-level imports that would conflict
            if "logger = logging.getLogger" in line:
                continue
            if line == "import json" or line == "import logging" or line == "import sys":
                if seen_code:  # Only skip if we've already seen these imports
                    continue

            # Skip if __name__ == "__main__" blocks to avoid duplicate execution
            if 'if __name__ == "__main__"' in line:
                # Skip this block entirely
                continue
            if line.strip() == "main()" and i > 0 and "if __name__" in lines[i - 1]:
                continue

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    def create_bundle(self) -> str:
        """Create the complete bundled server."""
        logger.info("Starting bundle creation...")

        # Try to import astor for better AST handling
        try:
            import astor

            logger.info("Using AST-based cleaning (astor available)")
        except ImportError:
            logger.warning("astor not available, using text-based cleaning")

        # Discover all components and tools
        self.discover_all()
        logger.info(
            f"Discovered {len(self.discovered_components)} components and {len(self.discovered_tools)} tools"
        )

        # Start building the output
        output_parts = []

        # Add imports
        output_parts.append(self.generate_imports())
        output_parts.append("")

        # Process each component
        for rel_path, description in self.discovered_components:
            file_path = SRC_DIR / rel_path
            if not file_path.exists():
                logger.warning(f"Component file not found: {file_path}")
                continue

            logger.info(f"Processing {rel_path}...")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Clean the content
                cleaned_content = self.clean_content(content, rel_path)

                # Fix tool imports if needed
                is_tool = rel_path.startswith("tools/") and rel_path != "tools/base.py"
                cleaned_content = self._fix_tool_imports(cleaned_content, is_tool)

                # Fix orchestrator if needed
                if "orchestrator.py" in rel_path:
                    cleaned_content = self._fix_orchestrator_for_bundled(cleaned_content)

                if not cleaned_content.strip():
                    continue

                # Add section header (but make it safe)
                # Escape any special characters in description
                safe_description = description.replace("\n", " ").replace("\r", "")
                if len(safe_description) > 80:
                    safe_description = safe_description[:77] + "..."

                output_parts.append("")
                output_parts.append(f"# {'='*10} {safe_description} {'='*10}")
                output_parts.append("")

                output_parts.append(cleaned_content)

            except Exception as e:
                logger.error(f"Failed to process {rel_path}: {e}")

        # Add the tool registry override
        output_parts.append("")
        output_parts.append(self.generate_tool_registry_override())

        # Add main execution
        output_parts.append("")
        output_parts.append(self._generate_main_section())

        return "\n".join(output_parts)

    def _generate_main_section(self) -> str:
        """Generate the main execution section."""
        return textwrap.dedent(
            """
# ========== Main Execution ==========

if __name__ == "__main__":
    # Apply the tool registry override before running
    _apply_tool_registry_override()

    # Call the main function from the bundled code
    main()
        """
        ).strip()


def main():
    """Main bundling function."""
    logger.info("Bundler for Council MCP Server")
    logger.info(f"Source: {SRC_DIR}")
    logger.info(f"Output: {OUTPUT_FILE}")

    bundler = Bundler()

    try:
        # Create bundle
        bundle_content = bundler.create_bundle()

        # Write output
        OUTPUT_FILE.write_text(bundle_content, encoding="utf-8")
        OUTPUT_FILE.chmod(0o755)

        logger.info(f"✓ Bundle created: {OUTPUT_FILE}")
        logger.info(f"  Size: {len(bundle_content):,} bytes")
        logger.info(f"  Lines: {bundle_content.count(chr(10)):,}")

        # Test compilation
        try:
            compile(bundle_content, str(OUTPUT_FILE), "exec")
            logger.info("✓ Bundle compiles successfully")
        except SyntaxError as e:
            logger.error(f"✗ Syntax error in generated bundle: {e}")
            logger.error(f"  Line {e.lineno}: {e.text}")
            return 1

    except Exception as e:
        logger.error(f"Failed to create bundle: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
