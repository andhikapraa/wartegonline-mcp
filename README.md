# Warteg Online MCP Server

Manage your Warteg Online meal deliveries using AI assistants like Claude. Simply talk to Claude in natural language to view, reschedule, or manage your daily meal subscriptions.

## About Warteg Online

Warteg Online provides healthy, home-style Indonesian meals delivered to your door. With 500+ rotating menu options prepared by former 5-star hotel chefs, it's perfect for busy professionals who want nutritious, restaurant-quality meals without the hassle of cooking.

**Service Areas:** Jakarta, Depok, Tangerang, Bekasi

- **Website:** [warloncatering.com](https://warloncatering.com)
- **Instagram:** [@wartegonline.idn](https://www.instagram.com/wartegonline.idn/)
- **Customer Dashboard:** [customer.warloncatering.com](https://customer.warloncatering.com/)

## What is This?

This is a special tool that lets AI assistants (like Claude) manage your Warteg Online deliveries for you. Instead of logging into the dashboard and clicking around, you can simply chat with Claude and say things like:

- "Show me my delivery schedule for this week"
- "Skip tomorrow's lunch, I have a meeting"
- "Hold all my deliveries from January 20-25 while I'm traveling"
- "Change my dinner delivery address to my office"
- "What's the summary of my remaining deliveries?"

The AI understands your request and handles everything automatically.

## What Can It Do?

| Task | What You Can Say |
|------|------------------|
| **View Schedule** | "Show my deliveries" or "What's coming this week?" |
| **Skip a Day** | "Skip Monday's delivery" |
| **Hold Deliveries** | "Pause my meals from Jan 10 to Jan 15" |
| **Reschedule** | "Move Friday's lunch to next Monday" |
| **Change Address** | "Deliver to my office address tomorrow" |
| **Check Summary** | "How many deliveries do I have left?" |
| **View Restrictions** | "What are my food restrictions?" |
| **Update Restrictions** | "I'm allergic to seafood" or "Remove spicy food from my meals" |

## Getting Started

### Prerequisites

You'll need:
1. A Warteg Online subscription (sign up at [warloncatering.com](https://warloncatering.com))
2. Your account username and password
3. Claude Desktop app installed on your computer

### Installation

#### Option 1: Via Smithery (Easiest)

Open your terminal and run:

```bash
npx -y @smithery/cli install @anthropics/warlon-mcp --client claude
```

#### Option 2: Manual Setup

1. **Download the tool:**
   ```bash
   git clone https://github.com/anthropics/warlon-mcp.git
   cd warlon-mcp
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Configure Claude Desktop:**

   Open Claude Desktop settings and add this MCP server configuration:

   **On Mac:** Edit `~/.config/claude/claude_desktop_config.json`

   **On Windows:** Edit `%APPDATA%\Claude\claude_desktop_config.json`

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

   Replace `/path/to/warlon-mcp` with the actual folder location, and enter your Warteg Online login credentials.

4. **Restart Claude Desktop**

### First Time Use

After setup, open Claude Desktop and try saying:

> "Login to Warteg Online and show me my delivery schedule"

Claude will connect to your account and display your upcoming meals.

## Common Questions

**Is this official?**
Yes, this tool is designed to work with the official Warteg Online platform.

**Is my password safe?**
Your credentials are stored locally on your computer and are only used to authenticate with Warteg Online's servers. They are never shared with anyone else.

**Can I still use the website/app?**
Absolutely! This tool is just another way to manage your deliveries. You can still use [customer.warloncatering.com](https://customer.warloncatering.com/) anytime.

**What if something goes wrong?**
The tool will inform Claude if an action can't be completed. For any issues with your actual subscription, contact Warteg Online directly through their [Instagram](https://www.instagram.com/wartegonline.idn/) or website.

## For Developers

### Technical Details

This is an MCP (Model Context Protocol) server that provides 15 tools for delivery management:

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
- `get_available_restrictions` - List all dietary restriction options
- `get_my_restrictions` - View current dietary restrictions
- `update_restrictions` - Set dietary restrictions (pantangan)

**Features:**
- Jakarta timezone (UTC+7) support
- Sunday delivery validation (no deliveries on Sundays)

### Development

```bash
# Install dev dependencies
uv sync

# Run locally in stdio mode
uv run warlon_mcp.py

# Run in HTTP mode (for testing remote deployment)
uv run warlon_mcp.py --http
```

## Support

- **Warteg Online Support:** Contact via [Instagram](https://www.instagram.com/wartegonline.idn/) or [website](https://warloncatering.com)
- **Technical Issues:** Open an issue on the GitHub repository

## License

MIT
