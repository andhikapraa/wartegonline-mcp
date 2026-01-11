# Warlon Catering MCP Server

An MCP (Model Context Protocol) server for managing delivery schedules on the Warlon Catering self-service platform.

## Features

- **12 Tools** for complete delivery management:
  - `login` - Authenticate with Warlon
  - `get_package_orders` - List all orders
  - `get_order_details` - Get package info
  - `get_schedule` - View full delivery schedule
  - `get_orders_by_date_range` - Filter deliveries by date
  - `get_available_addresses` - List delivery addresses
  - `get_delivery_summary` - Stats and counts
  - `reschedule_delivery` - Move single delivery
  - `skip_day` - Skip a date (move to end)
  - `hold_deliveries` - Pause for date range
  - `bulk_reschedule` - Move multiple deliveries
  - `change_address` - Update delivery address

- **Timezone Support** - Handles Jakarta timezone (UTC+7) correctly
- **Sunday Validation** - Prevents scheduling on Sundays

## Installation

### Via Smithery (Recommended)

```bash
npx -y @smithery/cli install @your-username/warlon-mcp --client claude
```

### Local Installation

```bash
# Clone the repository
git clone https://github.com/your-username/warlon-mcp.git
cd warlon-mcp

# Install dependencies
uv sync

# Run the server
uv run warlon_mcp.py
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `WARLON_USERNAME` | Your Warlon account username |
| `WARLON_PASSWORD` | Your Warlon account password |

### Claude Desktop Configuration

Add to your Claude Desktop config (`~/.config/claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "warlon": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/warlon-mcp", "warlon_mcp.py"],
      "env": {
        "WARLON_USERNAME": "your_username",
        "WARLON_PASSWORD": "your_password"
      }
    }
  }
}
```

## Usage Examples

Once connected, you can ask Claude:

- "Show my delivery schedule"
- "Skip tomorrow's delivery"
- "Hold deliveries from Jan 20 to Jan 25"
- "Move my lunch on Friday to Monday"
- "What's my delivery summary?"

## Development

```bash
# Install dev dependencies
uv sync

# Run locally in stdio mode
uv run warlon_mcp.py

# Run in HTTP mode (for testing remote deployment)
uv run warlon_mcp.py --http
```

## License

MIT
