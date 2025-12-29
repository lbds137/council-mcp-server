# Troubleshooting Guide

## Model Usage Discrepancy

### Problem
Google AI Console shows invocations to `gemini-2.0-flash-exp` instead of the models specified in `.env` file.

### Root Cause
The hardcoded default in `src/gemini_mcp/models/manager.py` was set to `gemini-2.0-flash-exp`, while the `.env` file and documentation specified `gemini-2.5-pro-preview-06-05` as the primary model.

When the `.env` file fails to load properly (e.g., during initial setup or if the file is in the wrong location), the code falls back to the hardcoded default.

### Solution
1. **Fixed**: Updated the default in `manager.py` to match documented defaults:
   ```python
   self.primary_model_name = os.getenv("GEMINI_MODEL_PRIMARY", "gemini-2.5-pro-preview-06-05")
   ```

2. **Ensure .env is loaded**: The server looks for `.env` in these locations:
   - First: `~/.claude-mcp-servers/council/.env` (MCP installation directory)
   - Fallback: Current working directory

3. **Verify configuration**: Use the `server_info` tool to check which models are actually loaded:
   ```
   mcp__council__server_info
   ```

### Prevention
- Always check the server_info output after deployment to confirm correct model configuration
- Keep hardcoded defaults in sync with documentation
- Consider adding validation to warn when falling back to default values

## Common Issues

### API Key Not Found
**Symptoms**: "No GEMINI_API_KEY found in environment" error

**Solutions**:
1. Ensure `.env` file exists in the correct location
2. Check file permissions: `chmod 644 ~/.claude-mcp-servers/council/.env`
3. Verify the key format in `.env`: `OPENROUTER_API_KEY="your-key-here"`
4. Restart Claude Desktop after updating `.env`

### Model Initialization Failures
**Symptoms**: "Failed to initialize primary/fallback model" errors

**Common Causes**:
1. Invalid model name (typo or deprecated model)
2. API key lacks permissions for the specified model
3. Model is not available in your region

**Solutions**:
1. Verify model names match Google's current offerings
2. Check API key permissions in Google AI Studio
3. Use `server_info` to see which models successfully initialized

### Timeout Issues
**Symptoms**: Primary model times out, always falls back to secondary

**Solutions**:
1. Increase timeout in `.env`:
   ```
   GEMINI_MODEL_TIMEOUT=600000  # 10 minutes for complex reasoning
   ```
2. Consider if the primary model (thinking model) needs more time
3. Check if requests are too complex for the timeout window

### Rate Limiting
**Symptoms**: Both models fail with 429 errors

**Current Limitation**: The code treats rate limits as failures and attempts failover, which can cascade the problem.

**Workarounds**:
1. Reduce request frequency
2. Implement request queuing in your application
3. Monitor usage in Google AI Console

### Debugging Steps

1. **Enable debug logging**:
   ```bash
   echo "COUNCIL_DEBUG=1" >> ~/.claude-mcp-servers/council/.env
   ```

2. **Check logs**:
   ```bash
   tail -f ~/.claude-mcp-servers/council/logs/council-mcp-server.log
   ```

3. **Verify environment**:
   - Run `server_info` to check configuration
   - Look for model initialization messages in logs
   - Confirm which model is responding to requests

4. **Test with simple request**:
   ```
   mcp__council__ask
   # Question: "What model are you?"
   ```
   The response footer shows which model actually responded.
