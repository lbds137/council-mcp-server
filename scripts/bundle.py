#!/usr/bin/env python3
"""
Final bundler that creates a working single-file server from modular components.
This follows the structure of the working server.py more closely.
"""

import re
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "gemini_mcp"
OUTPUT_FILE = PROJECT_ROOT / "server.py"

# Component loading order
COMPONENTS = [
    ("json_rpc.py", "JSON-RPC 2.0 server implementation"),
    ("models/base.py", "Base models and data structures"),
    ("models/manager.py", "Dual model manager with fallback"),
    ("models/memory.py", "Memory models"),
    ("services/cache.py", "Response cache service"),
    ("services/memory.py", "Conversation memory service"),
    ("tools/base.py", "Tool base classes"),
    ("core/registry.py", "Tool registry"),
    ("core/orchestrator.py", "Conversation orchestrator"),
    ("tools/ask_gemini.py", "Ask Gemini tool"),
    ("tools/code_review.py", "Code review tool"),
    ("tools/brainstorm.py", "Brainstorm tool"),
    ("tools/test_cases.py", "Test cases tool"),
    ("tools/explain.py", "Explain tool"),
    ("tools/synthesize.py", "Synthesize tool"),
    ("protocols/debate.py", "Debate protocol"),
    ("main.py", "Main server class"),
]


class FinalBundler:
    """Creates a working bundled server.py following existing structure."""

    def __init__(self):
        self.output_lines = []

    def read_file(self, path: Path) -> str:
        """Read a file's content."""
        if not path.exists():
            print(f"Warning: {path} not found")
            return ""
        return path.read_text()

    def extract_class_or_function(self, content: str, name: str) -> str:
        """Extract a specific class or function from content."""
        lines = content.split("\n")
        result = []
        capturing = False
        indent_level = 0

        for line in lines:
            if f"class {name}" in line or f"def {name}" in line:
                capturing = True
                indent_level = len(line) - len(line.lstrip())
                result.append(line)
            elif capturing:
                current_indent = (
                    len(line) - len(line.lstrip()) if line.strip() else indent_level + 1
                )
                if line.strip() and current_indent <= indent_level:
                    # End of class/function
                    break
                result.append(line)

        return "\n".join(result)

    def clean_imports(self, content: str) -> str:
        """Remove relative imports and module imports."""
        # Remove relative imports
        content = re.sub(r"from \.[.\w]* import .*\n", "", content)
        # Remove module imports
        content = re.sub(r"from gemini_mcp[.\w]* import .*\n", "", content)
        content = re.sub(r"from src\.gemini_mcp[.\w]* import .*\n", "", content)
        # Remove duplicate logger definitions
        content = re.sub(r"logger = logging\.getLogger\(__name__\)\n", "", content)
        return content

    def extract_content_without_imports(self, content: str) -> str:
        """Extract content without imports and module docstrings."""
        lines = content.split("\n")
        result = []
        past_imports = False
        skip_docstring = True
        in_docstring = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip shebang
            if i == 0 and stripped.startswith("#!"):
                continue

            # Skip module docstring
            if skip_docstring and i < 10:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    if stripped.endswith('"""') or stripped.endswith("'''"):
                        if len(stripped) > 6:  # Single line docstring
                            skip_docstring = False
                            continue
                    in_docstring = True
                    continue
                if in_docstring:
                    if stripped.endswith('"""') or stripped.endswith("'''"):
                        in_docstring = False
                        skip_docstring = False
                    continue

            # Skip imports
            if not past_imports and (
                stripped.startswith("import ") or stripped.startswith("from ")
            ):
                continue

            # Skip try/except for dotenv
            if "from dotenv import load_dotenv" in line:
                continue

            # Skip logging configuration
            if "logging.basicConfig" in line:
                continue

            # We're past imports
            if stripped and not stripped.startswith("#"):
                past_imports = True

            if past_imports:
                result.append(line)

        return "\n".join(result).strip()

    def process_tools(self, tool_content: str, tool_name: str) -> str:
        """Process tool content to work with global model_manager."""
        # Tools already use model_manager directly in execute method
        # Just need to clean imports
        return self.clean_imports(tool_content)

    def create_tool_methods(self) -> List[str]:
        """Create the tool method implementations for the server class."""
        return [
            "",
            "    def _ask_gemini(self, arguments: Dict[str, Any]) -> str:",
            '        """Ask Gemini a general question."""',
            '        question = arguments.get("question", "")',
            '        context = arguments.get("context", "")',
            "        ",
            "        if not question:",
            '            return "❌ Question is required"',
            "        ",
            '        prompt = f"Context: {context}\\n\\n" if context else ""',
            '        prompt += f"Question: {question}"',
            "        ",
            "        try:",
            "            response_text, model_used = self.model_manager.generate_content(prompt)",
            '            result = f"🤖 Gemini\'s Response:\\n\\n{response_text}"',
            "            if model_used != self.model_manager.primary_model_name:",
            '                result += f"\\n\\n[Model: {model_used}]"',
            "            return result",
            "        except Exception as e:",
            '            logger.error(f"Gemini API error: {e}")',
            '            return f"❌ Error: {str(e)}"',
            "",
            "    def _code_review(self, arguments: Dict[str, Any]) -> str:",
            '        """Code review implementation."""',
            '        code = arguments.get("code")',
            "        if not code:",
            '            return "❌ Code is required for review"',
            "        ",
            '        language = arguments.get("language", "javascript")',
            '        focus = arguments.get("focus", "general")',
            "        ",
            "        focus_instructions = {",
            '            "security": "Pay special attention to security vulnerabilities.",',
            '            "performance": "Focus on performance optimizations.",',
            '            "readability": "Emphasize code clarity and maintainability.",',
            '            "general": "Provide a comprehensive review."',
            "        }",
            "        ",
            '        prompt = f"""Please review the following {language} code:',
            "",
            "```{language}",
            "{code}",
            "```",
            "",
            '{focus_instructions.get(focus, focus_instructions["general"])}',
            "",
            'Provide specific feedback and suggestions."""',
            "        ",
            "        try:",
            "            response_text, model_used = self.model_manager.generate_content(prompt)",
            '            result = f"🔍 Code Review:\\n\\n{response_text}"',
            "            if model_used != self.model_manager.primary_model_name:",
            '                result += f"\\n\\n[Model: {model_used}]"',
            "            return result",
            "        except Exception as e:",
            '            return f"❌ Error: {str(e)}"',
            "",
            "    def _brainstorm(self, arguments: Dict[str, Any]) -> str:",
            '        """Brainstorm implementation."""',
            '        topic = arguments.get("topic")',
            "        if not topic:",
            '            return "❌ Topic is required for brainstorming"',
            "        ",
            '        constraints = arguments.get("constraints", "")',
            '        constraints_text = f"\\nConstraints: {constraints}" if constraints else ""',
            "        ",
            '        prompt = f"""Let\'s brainstorm ideas about: {topic}{constraints_text}',
            "",
            "Please provide:",
            "1. Creative and innovative ideas",
            "2. Different perspectives",
            "3. Potential challenges and solutions",
            '4. Actionable next steps"""',
            "        ",
            "        try:",
            "            response_text, model_used = self.model_manager.generate_content(prompt)",
            '            result = f"💡 Brainstorming Results:\\n\\n{response_text}"',
            "            if model_used != self.model_manager.primary_model_name:",
            '                result += f"\\n\\n[Model: {model_used}]"',
            "            return result",
            "        except Exception as e:",
            '            return f"❌ Error: {str(e)}"',
            "",
            "    def _suggest_test_cases(self, arguments: Dict[str, Any]) -> str:",
            '        """Test cases implementation."""',
            '        code_or_feature = arguments.get("code_or_feature")',
            "        if not code_or_feature:",
            '            return "❌ Code or feature description is required"',
            "        ",
            '        test_type = arguments.get("test_type", "all")',
            "        ",
            '        prompt = f"""Please suggest test cases for the following:',
            "",
            "{code_or_feature}",
            "",
            "Focus on {test_type} tests. For each test case, provide:",
            "1. Test name/description",
            "2. Input/setup required",
            "3. Expected behavior/output",
            '4. Why this test is important"""',
            "        ",
            "        try:",
            "            response_text, model_used = self.model_manager.generate_content(prompt)",
            '            result = f"🧪 Test Cases:\\n\\n{response_text}"',
            "            if model_used != self.model_manager.primary_model_name:",
            '                result += f"\\n\\n[Model: {model_used}]"',
            "            return result",
            "        except Exception as e:",
            '            return f"❌ Error: {str(e)}"',
            "",
            "    def _explain(self, arguments: Dict[str, Any]) -> str:",
            '        """Explain implementation."""',
            '        topic = arguments.get("topic")',
            "        if not topic:",
            '            return "❌ Topic is required for explanation"',
            "        ",
            '        level = arguments.get("level", "intermediate")',
            "        ",
            "        level_instructions = {",
            '            "beginner": "Explain in simple terms for someone new to programming.",',
            '            "intermediate": "Explain for someone with programming experience.",',
            '            "expert": "Provide an in-depth technical explanation."',
            "        }",
            "        ",
            '        prompt = f"""Please explain the following:',
            "",
            "{topic}",
            "",
            '{level_instructions.get(level, level_instructions["intermediate"])}',
            "",
            'Structure your explanation clearly with examples if applicable."""',
            "        ",
            "        try:",
            "            response_text, model_used = self.model_manager.generate_content(prompt)",
            '            result = f"📚 Explanation:\\n\\n{response_text}"',
            "            if model_used != self.model_manager.primary_model_name:",
            '                result += f"\\n\\n[Model: {model_used}]"',
            "            return result",
            "        except Exception as e:",
            '            return f"❌ Error: {str(e)}"',
            "",
            "    def _synthesize(self, arguments: Dict[str, Any]) -> str:",
            '        """Synthesize perspectives implementation."""',
            '        topic = arguments.get("topic")',
            "        if not topic:",
            '            return "❌ Topic is required for synthesis"',
            "        ",
            '        perspectives = arguments.get("perspectives", [])',
            "        if not perspectives:",
            '            return "❌ At least one perspective is required"',
            "        ",
            '        perspectives_text = "\\n\\n".join([',
            "            f\"**{p.get('source', f'Perspective {i+1}')}:**\\n{p['content']}\"",
            "            for i, p in enumerate(perspectives)",
            "        ])",
            "        ",
            '        prompt = f"""Please synthesize the following perspectives on: {topic}',
            "",
            "{perspectives_text}",
            "",
            "Provide a balanced synthesis that:",
            "1. Identifies common themes",
            "2. Highlights key differences",
            '3. Proposes a unified understanding"""',
            "        ",
            "        try:",
            "            response_text, model_used = self.model_manager.generate_content(prompt)",
            '            result = f"🔄 Synthesis:\\n\\n{response_text}"',
            "            if model_used != self.model_manager.primary_model_name:",
            '                result += f"\\n\\n[Model: {model_used}]"',
            "            return result",
            "        except Exception as e:",
            '            return f"❌ Error: {str(e)}"',
        ]

    def create_bundle(self) -> str:
        """Create the complete bundled server."""
        # Start with header and imports
        self.output_lines = [
            "#!/usr/bin/env python3",
            '"""',
            "Gemini MCP Server v3.0.0 - Single File Bundle",
            "A Model Context Protocol server that enables Claude to collaborate "
            "with Google's Gemini AI models.",
            "This version combines all modular components into a single deployable file.",
            '"""',
            "",
            "import asyncio",
            "import collections",
            "import hashlib",
            "import importlib",
            "import inspect",
            "import json",
            "import logging",
            "import os",
            "import sys",
            "import time",
            "from abc import ABC, abstractmethod",
            "from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError",
            "from datetime import datetime",
            "from pathlib import Path",
            "from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type",
            "from dataclasses import dataclass, field",
            "from collections import OrderedDict, deque",
            "",
            "import google.generativeai as genai",
            "from google.api_core import exceptions as google_exceptions",
            "",
            "try:",
            "    from dotenv import load_dotenv",
            "except ImportError:",
            "    load_dotenv = None",
            "",
            "# Configure logging",
            "logging.basicConfig(",
            "    level=logging.INFO,",
            '    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",',
            "    stream=sys.stderr,",
            ")",
            'logger = logging.getLogger("gemini-mcp-v3")',
            "",
            '__version__ = "3.0.0"',
            "",
            "# Global model manager instance (will be set by server)",
            "model_manager = None",
            "",
        ]

        # Process each component
        for component_path, description in COMPONENTS:
            file_path = SRC_DIR / component_path
            if not file_path.exists():
                print(f"Skipping {component_path} (not found)")
                continue

            print(f"Processing {component_path}...")
            content = self.read_file(file_path)

            # Extract content without imports
            clean_content = self.extract_content_without_imports(content)
            clean_content = self.clean_imports(clean_content)

            # Skip empty content
            if not clean_content or clean_content.isspace():
                continue

            # Special handling for core/registry.py - fix discovery for bundled version
            if component_path == "core/registry.py":
                # Add a bundled version of discover_tools that registers tools directly
                clean_content = clean_content.replace(
                    "class ToolRegistry:",
                    '''class ToolRegistry:
    """Registry for discovering and managing tools.
    Modified for bundled version to register tools directly."""

    @classmethod
    def _get_bundled_tools(cls):
        """Get all tool classes defined in this bundled file."""
        # This will be populated later
        return []''',
                )

                # Override discover_tools for bundled version
                clean_content = clean_content.replace(
                    "def discover_tools(self, tools_path: Optional[Path] = None) -> None:",
                    '''def discover_tools(self, tools_path: Optional[Path] = None) -> None:
        """Discover and register all tools - bundled version."""
        # In bundled version, register tools directly
        logger.info("Discovering tools in bundled server")

        # Get all tool classes from the global scope
        for tool_class in self._get_bundled_tools():
            try:
                self._register_tool_class(tool_class)
            except Exception as e:
                logger.error(f"Failed to register {tool_class.__name__}: {e}")

        logger.info(f"Registered {len(self._tools)} tools in bundled mode")
        return  # Skip the rest of the original method

    def discover_tools_original(self, tools_path: Optional[Path] = None) -> None:''',
                )

                # Fix _register_tool_class to work with property-based tools
                clean_content = clean_content.replace(
                    '''def _register_tool_class(self, tool_class: Type[BaseTool]) -> None:
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
            logger.error(f"Failed to register tool {tool_class.__name__}: {e}")''',
                    '''def _register_tool_class(self, tool_class: Type[BaseTool]) -> None:
        """Register a tool class."""
        try:
            # Instantiate the tool to get its metadata
            tool_instance = tool_class()
            # In bundled version, use property-based access
            tool_name = tool_instance.name

            if tool_name in self._tools:
                logger.warning(f"Tool {tool_name} already registered, skipping")
                return

            self._tools[tool_name] = tool_instance
            self._tool_classes[tool_name] = tool_class
            logger.info(f"Registered tool: {tool_name}")

        except Exception as e:
            logger.error(f"Failed to register tool {tool_class.__name__}: {e}")''',
                )

            # Special handling for main.py
            if component_path == "main.py":
                # Extract just the server class
                server_class = self.extract_class_or_function(clean_content, "GeminiMCPServerV3")
                if server_class:
                    # Fix __file__ reference for bundled version
                    server_class = server_class.replace(
                        "mcp_dir = os.path.dirname(os.path.abspath(__file__))",
                        "mcp_dir = os.path.dirname(os.path.abspath(sys.argv[0]))",
                    )

                    # Insert tool methods before the run method
                    lines = server_class.split("\n")
                    new_lines = []
                    for i, line in enumerate(lines):
                        new_lines.append(line)
                        # Add tool methods before run method
                        if "    def run(self):" in line:
                            new_lines = new_lines[:-1]  # Remove the run line temporarily
                            new_lines.extend(self.create_tool_methods())
                            new_lines.append("")
                            new_lines.append(line)  # Add run line back
                    clean_content = "\n".join(new_lines)

                    # Fix the handle_tool_call method
                    clean_content = clean_content.replace(
                        '''        try:
            # Execute through orchestrator (convert async to sync)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                output = loop.run_until_complete(
                    self.orchestrator.execute_tool(
                        tool_name=tool_name, parameters=arguments, request_id=request_id
                    )
                )
            finally:
                loop.close()

            if output.success:
                result = output.result
            else:
                result = f"❌ Error: {output.error or 'Unknown error'}"

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            result = f"❌ Error executing tool: {str(e)}"''',
                        '''        # Execute tool directly
        # Set global model manager for tools
        global model_manager
        model_manager = self.model_manager

        if tool_name == "ask_gemini":
            result = self._ask_gemini(arguments)
        elif tool_name == "gemini_code_review":
            result = self._code_review(arguments)
        elif tool_name == "gemini_brainstorm":
            result = self._brainstorm(arguments)
        elif tool_name == "gemini_test_cases":
            result = self._suggest_test_cases(arguments)
        elif tool_name == "gemini_explain":
            result = self._explain(arguments)
        elif tool_name == "synthesize_perspectives":
            result = self._synthesize(arguments)
        else:
            result = f"❌ Unknown tool: {tool_name}"''',
                    )

            # Add section
            self.output_lines.extend(
                [
                    "",
                    f'# {"="*10} {description} {"="*10}',
                    "",
                    clean_content,
                ]
            )

        # Add simplified ToolOutput for compatibility
        self.output_lines.extend(
            [
                "",
                "# ========== Tool Output (Simplified for Bundled Version) ==========",
                "",
                "class ToolOutput:",
                '    """Standard output format for tool execution."""',
                "    def __init__(self, success: bool, result: Optional[str] = None, "
                "error: Optional[str] = None):",
                "        self.success = success",
                "        self.result = result",
                "        self.error = error",
                "        self.metadata: Dict[str, Any] = {}",
                "",
            ]
        )

        # Add code to populate bundled tools list
        self.output_lines.extend(
            [
                "",
                "# ========== Register Bundled Tools ==========",
                "",
                "# Update the ToolRegistry to know about bundled tools",
                "ToolRegistry._get_bundled_tools = classmethod(lambda cls: [",
                "    AskGeminiTool,",
                "    CodeReviewTool,",
                "    BrainstormTool,",
                "    TestCasesTool,",
                "    ExplainTool,",
                "    SynthesizeTool,",
                "])",
                "",
            ]
        )

        # Add main function
        self.output_lines.extend(
            [
                "",
                "# ========== Main Execution ==========",
                "",
                "def main():",
                '    """Main entry point."""',
                "    try:",
                "        server = GeminiMCPServerV3()",
                "        server.run()",
                "    except KeyboardInterrupt:",
                '        logger.info("Server stopped by user")',
                "    except Exception as e:",
                '        logger.error(f"Server error: {e}")',
                "        sys.exit(1)",
                "",
                "",
                'if __name__ == "__main__":',
                "    main()",
            ]
        )

        return "\n".join(self.output_lines)


def main():
    """Main bundling function."""
    print("Creating final bundle from modular components...")
    print(f"Source: {SRC_DIR}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    bundler = FinalBundler()

    try:
        # Create bundle
        bundle_content = bundler.create_bundle()

        # Write output
        OUTPUT_FILE.write_text(bundle_content)
        OUTPUT_FILE.chmod(0o755)

        print(f"\n✓ Bundle created: {OUTPUT_FILE}")
        print(f"  Size: {len(bundle_content):,} bytes")
        print(f"  Lines: {bundle_content.count(chr(10)):,}")

        # Test compilation
        try:
            compile(bundle_content, str(OUTPUT_FILE), "exec")
            print("✓ Bundle compiles successfully")
        except SyntaxError as e:
            print(f"✗ Syntax error: {e}")
            return 1

        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
