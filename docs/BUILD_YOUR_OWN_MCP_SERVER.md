# Building Your Own MCP Server for Claude Code

This guide will walk you through creating a custom MCP (Model Context Protocol) server that integrates with Claude Code, allowing you to extend Claude's capabilities with external tools, APIs, or even other AI models.

## What is MCP?

MCP (Model Context Protocol) is a protocol that allows Claude to communicate with external servers to access tools and capabilities beyond its built-in features. Think of it as a plugin system for Claude.

## Prerequisites

- Python 3.8 or higher
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)
- Basic understanding of JSON-RPC protocol

## ⚠️ IMPORTANT: MCP Configuration Scopes

Before building your MCP server, understand Claude Code's configuration hierarchy to avoid common issues:

### Configuration Scope Types

Claude Code supports three configuration scopes (in order of priority):

1. **Project Scope** (`.vscode/mcp.json`) - Highest priority, overrides everything
2. **Local Scope** (`claude mcp add` default) - Works only in current directory
3. **User Scope** (`claude mcp add --scope user`) - Global configuration

### Common Pitfall: Local vs Global Configuration

**❌ WRONG (Local scope - only works in current directory):**
```bash
claude mcp add my-server python3 /path/to/server.py
```

**✅ CORRECT (User scope - works globally):**
```bash
claude mcp add --scope user my-server python3 /path/to/server.py
```

### Recommended Setup for Global Access

1. **Always use `--scope user`** for global MCP servers
2. **Store servers in permanent location**: `~/.claude-mcp-servers/`
3. **Avoid project-local configs** unless specifically needed
4. **Remove conflicting `.vscode/mcp.json`** files

### Quick Fix for Broken MCP Access

If your MCP only works in one directory:

```bash
# Check current configuration
claude mcp list

# Remove local config
claude mcp remove your-server

# Re-add with user scope
claude mcp add --scope user your-server python3 /path/to/server.py

# Remove any project-local configs
rm .vscode/mcp.json  # if exists
```

## Basic MCP Server Structure

### 1. Create Your Project Directory

```bash
mkdir my-mcp-server
cd my-mcp-server
```

### 2. Basic Server Template

Create a file named `server.py`:

```python
#!/usr/bin/env python3
"""
Basic MCP Server Template
"""

import json
import sys
import os
from typing import Dict, Any, Optional

# Ensure unbuffered output for proper communication
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)

def send_response(response: Dict[str, Any]):
    """Send a JSON-RPC response"""
    print(json.dumps(response), flush=True)

def handle_initialize(request_id: Any) -> Dict[str, Any]:
    """Handle initialization request"""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "my-mcp-server",
                "version": "1.0.0"
            }
        }
    }

def handle_tools_list(request_id: Any) -> Dict[str, Any]:
    """List available tools"""
    tools = [
        {
            "name": "hello_world",
            "description": "A simple hello world tool",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name to greet"
                    }
                },
                "required": ["name"]
            }
        }
    ]

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": tools
        }
    }

def handle_tool_call(request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tool execution"""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    try:
        if tool_name == "hello_world":
            name = arguments.get("name", "World")
            result = f"Hello, {name}! This is a response from your MCP server."
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": result
                    }
                ]
            }
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }

def main():
    """Main server loop"""
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            method = request.get("method")
            request_id = request.get("id")
            params = request.get("params", {})

            if method == "initialize":
                response = handle_initialize(request_id)
            elif method == "tools/list":
                response = handle_tools_list(request_id)
            elif method == "tools/call":
                response = handle_tool_call(request_id, params)
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            send_response(response)

        except json.JSONDecodeError:
            continue
        except EOFError:
            break
        except Exception as e:
            if 'request_id' in locals():
                send_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                })

if __name__ == "__main__":
    main()
```

### 3. Make It Executable

```bash
chmod +x server.py
```

### 4. Add to Claude Code

```bash
claude mcp add my-server python3 /path/to/your/server.py
```

## Understanding the MCP Protocol

### Required Methods

Your MCP server must handle these JSON-RPC methods:

1. **`initialize`** - Called when Claude connects to your server
   - Must return protocol version and capabilities

2. **`tools/list`** - Lists all available tools
   - Returns array of tool definitions with schemas

3. **`tools/call`** - Executes a specific tool
   - Receives tool name and arguments
   - Returns results that Claude can use

### Message Format

All communication uses JSON-RPC 2.0 over standard input/output:

**Request from Claude:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "hello_world",
    "arguments": {"name": "Claude"}
  }
}
```

**Response from your server:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Hello, Claude!"
      }
    ]
  }
}
```

## Advanced Example: Weather API Server

Here's a more practical example that fetches weather data:

```python
#!/usr/bin/env python3
import json
import sys
import os
import requests
from typing import Dict, Any

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)

# Your API key (store securely in production)
WEATHER_API_KEY = "your-api-key-here"

def get_weather(city: str) -> str:
    """Fetch weather data from API"""
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": WEATHER_API_KEY,
            "units": "metric"
        }
        response = requests.get(url, params=params)
        data = response.json()

        if response.status_code == 200:
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"]
            return f"Weather in {city}: {temp}°C, {desc}"
        else:
            return f"Error: {data.get('message', 'Unknown error')}"
    except Exception as e:
        return f"Error fetching weather: {str(e)}"

# ... (include the same boilerplate as before)

def handle_tools_list(request_id: Any) -> Dict[str, Any]:
    tools = [
        {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name"
                    }
                },
                "required": ["city"]
            }
        }
    ]
    # ... rest of implementation
```

## Best Practices

### 1. Error Handling
Always wrap tool execution in try-except blocks and return proper JSON-RPC errors:

```python
try:
    # Your tool logic
    result = do_something()
except Exception as e:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32603,
            "message": str(e)
        }
    }
```

### 2. Input Validation
Validate all inputs from the arguments:

```python
def validate_arguments(arguments: Dict[str, Any], required: List[str]):
    for field in required:
        if field not in arguments:
            raise ValueError(f"Missing required field: {field}")
```

### 3. Logging
Use stderr for logging to avoid interfering with JSON-RPC:

```python
import logging
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
```

### 4. Dependencies
Create a `requirements.txt` file:

```
requests>=2.28.0
# Add other dependencies
```

Install with: `pip install -r requirements.txt`

## Testing Your MCP Server

### 1. Manual Testing
Test individual methods:

```bash
# Test initialize
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 server.py

# Test tools/list
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | python3 server.py

# Test tool call
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"hello_world","arguments":{"name":"Test"}}}' | python3 server.py
```

### 2. Integration Testing
After adding to Claude Code:

```bash
# List all MCP servers
claude mcp list

# In a Claude Code session, your tools will appear as:
# mcp__<server-name>__<tool-name>
```

## Debugging Tips

1. **Check configuration scope first**:
   ```bash
   # Check what's configured
   claude mcp list

   # Check if you're in a directory with local config
   ls .vscode/mcp.json

   # Test in different directories
   cd ~ && claude mcp list
   ```

2. **Check logs**:
   ```bash
   ls ~/Library/Caches/claude-cli-nodejs/*/mcp-logs-<server-name>/
   ```

3. **Run with debug mode**:
   ```bash
   claude --debug
   ```

4. **Common issues**:
   - **MCP only works in one directory**: Wrong scope, use `--scope user`
   - **MCP not found**: Check if `.vscode/mcp.json` exists and conflicts
   - Import errors: Ensure all dependencies are installed
   - Connection closed: Check for syntax errors or crashes
   - Tools not appearing: Verify tools/list returns valid schema

5. **Configuration conflicts**:
   ```bash
   # Remove project-local config
   rm .vscode/mcp.json

   # Remove local scope config
   claude mcp remove server-name

   # Re-add with user scope
   claude mcp add --scope user server-name python3 /path/to/server.py
   ```

## Advanced Features

### 1. Stateful Conversations
Store conversation context:

```python
class MCPServer:
    def __init__(self):
        self.conversation_history = []

    def add_to_history(self, role: str, content: str):
        self.conversation_history.append({
            "role": role,
            "content": content
        })
```

### 2. File Handling
Return different content types:

```python
# Text content
{
    "type": "text",
    "text": "Your response"
}

# Image content (base64)
{
    "type": "image",
    "data": base64_encoded_image,
    "mimeType": "image/png"
}
```

### 3. Async Operations
For long-running tasks, consider implementing progress updates or background processing.

## Safe Installation & Deployment

### Recommended Directory Structure

Store your MCP servers in a permanent location:

```bash
~/.claude-mcp-servers/
├── your-server-name/
│   ├── server.py
│   ├── requirements.txt
│   ├── setup.py
│   └── README.md
└── backup.sh
```

### Create an Auto-Setup Script

Create `setup.py` for easy installation:

```python
#!/usr/bin/env python3
"""Setup script for MCP server"""
import subprocess
import sys
import os

def check_python_version():
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required")
        sys.exit(1)

def install_dependencies():
    print("📦 Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def add_to_claude():
    server_path = os.path.join(os.path.dirname(__file__), "server.py")
    print(f"🔧 Adding to Claude MCP with global scope...")
    # IMPORTANT: Use --scope user for global access!
    subprocess.run(["claude", "mcp", "add", "--scope", "user", "your-server", "python3", server_path])

if __name__ == "__main__":
    check_python_version()
    install_dependencies()
    add_to_claude()
    print("✅ Setup complete!")
```

### Version Management

Add version tracking to your server:

```python
__version__ = "1.0.0"
__updated__ = "2025-06-11"

# In your tools list, add:
{
    "name": "server_info",
    "description": "Get server version and status",
    "inputSchema": {"type": "object", "properties": {}}
}

# In tool handler:
if tool_name == "server_info":
    return f"Server v{__version__} (updated {__updated__})"
```

### Dependency Checking

Add automatic dependency checking:

```python
def check_dependencies():
    """Check if all required packages are installed"""
    required = ["requests", "other-package"]
    missing = []

    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        return f"Missing packages: {', '.join(missing)}"
    return "All dependencies installed!"
```

### Automatic Updates

Create an update mechanism for your server:

```python
# In your server.py
def check_for_updates():
    """Check if updates are available"""
    try:
        import requests
        response = requests.get("https://api.github.com/repos/YOUR_REPO/releases/latest")
        latest_version = response.json()["tag_name"]
        if latest_version > __version__:
            return f"Update available: {latest_version}"
        return "Server is up to date"
    except:
        return "Could not check for updates"

# Add update tool to your tools list
{
    "name": "update_server",
    "description": "Update the MCP server to latest version",
    "inputSchema": {"type": "object", "properties": {}}
}
```

### Environment Variables

Support environment variables for configuration:

```python
import os

# API keys and sensitive data
API_KEY = os.environ.get("YOUR_API_KEY", "default-key-if-any")

# Configuration
DEBUG = os.environ.get("MCP_DEBUG", "false").lower() == "true"
LOG_LEVEL = os.environ.get("MCP_LOG_LEVEL", "ERROR")
```

## Publishing Your MCP Server

1. **Package your server**:
   ```bash
   my-mcp-server/
   ├── server.py
   ├── requirements.txt
   ├── setup.py
   ├── README.md
   └── LICENSE
   ```

2. **Create one-line installer**:
   ```bash
   # In your README:
   curl -sSL https://your-repo/install.sh | bash
   ```

3. **Share on GitHub** with clear documentation

## Example Use Cases

1. **Database Query Tool**: Allow Claude to query your database
2. **API Integration**: Connect to any REST API
3. **System Monitoring**: Check system stats, logs, etc.
4. **Custom AI Models**: Integrate other AI models (like we did with Gemini)
5. **Development Tools**: Linters, formatters, test runners
6. **Communication Tools**: Send emails, Slack messages, etc.

## Security Considerations

1. **API Keys**: Never hardcode sensitive keys
   ```python
   API_KEY = os.environ.get("MY_API_KEY")
   ```

2. **Input Sanitization**: Always validate and sanitize inputs

3. **Access Control**: Limit what your MCP server can access

4. **Rate Limiting**: Implement rate limits for API calls

## Real-World Example: Claude-Gemini Collaboration MCP

Here's a complete working example that enables Claude Code to collaborate with Google's Gemini AI:

### Quick Installation

```bash
# 1. Create permanent directory
mkdir -p ~/.claude-mcp-servers/gemini-collab

# 2. Install Gemini SDK
pip install google-generativeai

# 3. Download server (simplified version)
curl -o ~/.claude-mcp-servers/gemini-collab/server.py https://your-repo/server.py

# 4. Add to Claude with USER SCOPE (crucial!)
claude mcp add --scope user gemini-collab python3 ~/.claude-mcp-servers/gemini-collab/server.py

# 5. Test from any directory
claude
/mcp  # Should show gemini-collab connected
```

### Available Tools

Once installed, you'll have these tools globally:
- `mcp__gemini-collab__ask_gemini` - Ask Gemini questions
- `mcp__gemini-collab__gemini_code_review` - Code reviews
- `mcp__gemini-collab__gemini_brainstorm` - Collaborative brainstorming

### Usage Example

```bash
# In any directory, start Claude Code:
claude

# Use Gemini for code review:
mcp__gemini-collab__gemini_code_review
  code: "function authenticate(user) { return user.password === 'admin'; }"
  focus: "security"

# Gemini's response appears directly in Claude's context!
```

### Key Learnings from This Setup

1. **Always use `--scope user`** for global access
2. **Store in `~/.claude-mcp-servers/`** for permanence
3. **Remove conflicting local configs** like `.vscode/mcp.json`
4. **Test in multiple directories** to verify global access
5. **Environment variables** for API keys when possible

## Conclusion

MCP servers extend Claude Code's capabilities infinitely. You can integrate any API, tool, or service by following this protocol. The key points for success:

1. **Use proper configuration scope** (`--scope user` for global)
2. **Handle errors gracefully** with try-except blocks
3. **Provide clear tool descriptions** so Claude knows how to use them
4. **Test thoroughly** in multiple directories
5. **Store servers permanently** in `~/.claude-mcp-servers/`

**Remember**: Configuration scope is the #1 source of MCP issues. When in doubt, use `--scope user`!

Happy building! 🚀
