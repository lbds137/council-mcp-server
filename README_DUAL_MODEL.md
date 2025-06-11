# Dual-Model Configuration Guide

This guide explains how to use the enhanced dual-model version of the Gemini MCP server.

## Overview

The enhanced server (`server_improved.py`) supports dual-model configuration with automatic fallback:

1. **Primary Model**: Tries the best/experimental model first
2. **Fallback Model**: Automatically switches to stable model if primary fails
3. **Zero Downtime**: Seamless experience even when models change

## Setup Instructions

### 1. Copy Environment Configuration

```bash
cd ~/.claude-mcp-servers/gemini-collab
cp .env.example .env
```

### 2. Edit Configuration

Edit `.env` file with your preferred models:

```bash
# Your API key
GEMINI_API_KEY=your_actual_api_key

# Best Overall Configuration (Recommended)
GEMINI_MODEL_PRIMARY=gemini-2.5-pro-preview-06-05
GEMINI_MODEL_FALLBACK=gemini-1.5-pro
GEMINI_MODEL_TIMEOUT=10000
```

### 3. Test the Improved Server

```bash
# Test directly
python3 server_improved.py

# In another terminal, send a test request
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"server_info","arguments":{}}}' | python3 server_improved.py
```

### 4. Update MCP Registration

Replace the current server with the improved version:

```bash
# Remove old registration
claude mcp remove gemini-collab

# Add improved version with environment variables
claude mcp add --scope user gemini-collab python3 ~/.claude-mcp-servers/gemini-collab/server_improved.py
```

### 5. Load Environment Variables

Make sure your shell loads the environment variables. Add to your `~/.bashrc` or `~/.zshrc`:

```bash
# Gemini MCP Configuration
if [ -f ~/.claude-mcp-servers/gemini-collab/.env ]; then
    export $(cat ~/.claude-mcp-servers/gemini-collab/.env | grep -v '^#' | xargs)
fi
```

## Configuration Options

### Best Overall (Quality + Reliability)
```bash
GEMINI_MODEL_PRIMARY=gemini-2.5-pro-preview-06-05
GEMINI_MODEL_FALLBACK=gemini-1.5-pro
```
- Primary: Cutting-edge reasoning and code understanding
- Fallback: Stable complex reasoning

### Best Performance (Speed + Cost)
```bash
GEMINI_MODEL_PRIMARY=gemini-2.5-flash-preview-05-20
GEMINI_MODEL_FALLBACK=gemini-2.0-flash
```
- Primary: Fast with thinking capabilities
- Fallback: Next-gen speed features

### Most Cost-Effective
```bash
GEMINI_MODEL_PRIMARY=gemini-2.0-flash
GEMINI_MODEL_FALLBACK=gemini-2.0-flash-lite
```
- Primary: Balanced performance
- Fallback: Ultra-efficient

## Features

### Automatic Fallback
- If primary model fails, automatically uses fallback
- If primary times out (default 10s), switches to fallback
- Transparent to Claude - you always get a response

### Model Indicators
When fallback is used, responses include `[Model: model-name]` at the end.

### Enhanced Status
```
mcp__gemini-collab__server_info
```
Shows:
- Primary model status
- Fallback model status
- Timeout configuration

## Monitoring

Check logs to see model usage:
```bash
# Find latest log
ls -la ~/Library/Caches/claude-cli-nodejs/*/mcp-logs-gemini-collab/

# Watch logs in real-time
tail -f ~/Library/Caches/claude-cli-nodejs/*/mcp-logs-gemini-collab/server.log
```

Log entries show:
- Which model was used
- Fallback triggers
- Response times
- Any errors

## Troubleshooting

### Models Not Loading
```bash
# Test models directly
python3 -c "
import google.generativeai as genai
genai.configure(api_key='$GEMINI_API_KEY')
try:
    model = genai.GenerativeModel('gemini-2.5-pro-preview-06-05')
    print('✅ 2.5 Pro Preview available')
except Exception as e:
    print(f'❌ 2.5 Pro Preview error: {e}')
"
```

### Environment Variables Not Loading
```bash
# Check if variables are set
env | grep GEMINI

# Source the .env file manually
export $(cat ~/.claude-mcp-servers/gemini-collab/.env | grep -v '^#' | xargs)
```

### Fallback Always Triggered
- Increase timeout if primary model is just slow
- Check if experimental model is temporarily unavailable
- Verify API quota hasn't been exceeded

## Benefits

1. **Always Get Best Available Response**: Uses cutting-edge models when they work
2. **Never Lose Functionality**: Falls back to stable models automatically
3. **Transparent Operation**: Works seamlessly with Claude
4. **Future-Proof**: As new models release, just update config

## Migration from Original Server

The improved server is fully backward compatible. To migrate:

1. Keep your existing `GEMINI_API_KEY`
2. Add the new model configuration variables
3. Replace `server.py` with `server_improved.py` in MCP registration
4. Enjoy enhanced capabilities!

## Next Steps

1. Test with `server_info` to verify setup
2. Try a code review to see quality improvements
3. Monitor logs to understand model usage patterns
4. Adjust timeout based on your needs