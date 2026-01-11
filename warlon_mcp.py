"""
Warlon Catering MCP Server

An MCP server that exposes the Warlon Catering API functionality as tools.
Allows AI assistants to interact with the catering platform for managing
delivery schedules.

Configuration:
    Set environment variables:
    - WARLON_USERNAME: Your Warlon username
    - WARLON_PASSWORD: Your Warlon password

Usage:
    Local:  uv run warlon_mcp.py
    Remote: uv run warlon_mcp.py --http (for Smithery deployment)
"""

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

from warlon_client import WarlonClient, OrderGroup, PackageOrder, JAKARTA_TZ


@dataclass
class AppContext:
    """Application context holding the Warlon client instance."""
    client: WarlonClient
    auto_logged_in: bool = False


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with optional auto-login."""
    client = WarlonClient()
    auto_logged_in = False

    # Auto-login if credentials are provided via environment variables
    username = os.environ.get("WARLON_USERNAME")
    password = os.environ.get("WARLON_PASSWORD")

    if username and password:
        if client.login(username, password):
            auto_logged_in = True

    yield AppContext(client=client, auto_logged_in=auto_logged_in)


mcp = FastMCP(
    "Warlon Catering",
    lifespan=app_lifespan,
)


def get_client() -> WarlonClient:
    """Get the WarlonClient from the current context."""
    ctx = mcp.get_context()
    return ctx.request_context.lifespan_context.client


@mcp.tool()
def login(username: str, password: str) -> str:
    """
    Authenticate with the Warlon Catering platform.

    Args:
        username: Your Warlon username
        password: Your Warlon password

    Returns:
        Success or failure message
    """
    client = get_client()
    if client.login(username, password):
        return f"Successfully logged in as {username}"
    return "Login failed. Please check your credentials."


@mcp.tool()
def get_package_orders() -> list[dict]:
    """
    Get all package orders for the authenticated user.

    Returns:
        List of package orders with their IDs and names
    """
    client = get_client()
    orders = client.get_package_orders()
    if not orders:
        return []

    return [
        {
            "order_id": order.get("id") or order.get("userPackageOrderId"),
            "package_name": order.get("packageName", "Unknown"),
        }
        for order in orders
    ]


@mcp.tool()
def get_order_details(order_id: int) -> dict:
    """
    Get detailed information about a specific package order.

    Args:
        order_id: The ID of the package order

    Returns:
        Detailed information about the order including package name,
        total days, and delivery counts
    """
    client = get_client()
    order = client.get_order_details(order_id)
    return {
        "order_id": order.id,
        "package_name": order.package_name,
        "description": order.package_description,
        "total_days": order.total_days,
        "lunch_deliveries": order.lunch_amount,
        "dinner_deliveries": order.dinner_amount,
        "available_addresses": len(order.addresses),
    }


@mcp.tool()
def get_schedule(order_id: int) -> dict:
    """
    Get the full delivery schedule for an order.

    Args:
        order_id: The ID of the package order

    Returns:
        Formatted schedule showing all deliveries with dates, types, and status
    """
    client = get_client()
    order = client.get_order_details(order_id)
    groups = client.get_all_order_groups(order_id)

    schedule = []
    for group in sorted(groups, key=lambda g: (g.scheduled_date, g.order_type)):
        schedule.append({
            "date": group.scheduled_date.strftime("%Y-%m-%d"),
            "day": group.scheduled_date.strftime("%A"),
            "type": group.order_type,
            "group_id": group.id,
            "status": group.status,
            "editable": group.is_editable,
        })

    return {
        "package_name": order.package_name,
        "description": order.package_description,
        "total_days": order.total_days,
        "lunch_count": order.lunch_amount,
        "dinner_count": order.dinner_amount,
        "schedule": schedule,
    }


@mcp.tool()
def get_orders_by_date_range(
    order_id: int,
    start_date: str,
    end_date: str
) -> dict:
    """
    Get all deliveries within a specific date range.

    Args:
        order_id: The ID of the package order
        start_date: Start date in YYYY-MM-DD format (inclusive)
        end_date: End date in YYYY-MM-DD format (inclusive)

    Returns:
        List of deliveries within the date range
    """
    client = get_client()
    # Parse dates as Jakarta timezone for correct local date handling
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)

    orders = client.get_orders_by_date_range(order_id, start, end)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "count": len(orders),
        "deliveries": [
            {
                "date": order.scheduled_date.strftime("%Y-%m-%d"),
                "day": order.scheduled_date.strftime("%A"),
                "type": order.order_type,
                "group_id": order.id,
                "editable": order.is_editable,
            }
            for order in orders
        ],
    }


@mcp.tool()
def reschedule_delivery(
    order_id: int,
    group_id: int,
    new_date: str,
    address_id: int,
    order_type: str,
) -> str:
    """
    Reschedule a single delivery to a new date.

    Args:
        order_id: The ID of the package order
        group_id: The ID of the order group (delivery) to reschedule
        new_date: The new delivery date in YYYY-MM-DD format
        address_id: The address ID for delivery
        order_type: Either "LUNCH" or "DINNER"

    Returns:
        Success or failure message
    """
    client = get_client()
    try:
        # Parse date as Jakarta timezone for correct local date handling
        new_datetime = datetime.strptime(new_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)

        # Validate: Sundays are not allowed
        if new_datetime.weekday() == 6:  # Sunday
            return f"Cannot schedule delivery on Sunday ({new_date}). Please choose a different date."

        if order_type not in ["LUNCH", "DINNER"]:
            return "order_type must be either 'LUNCH' or 'DINNER'"

        # Find the group to get schedule_id
        groups = client.get_all_order_groups(order_id)
        target_group = None
        for g in groups:
            if g.id == group_id:
                target_group = g
                break

        if not target_group:
            return f"Group {group_id} not found in order {order_id}"

        success = client.reschedule_order(
            group_id=group_id,
            new_date=new_datetime,
            address_id=address_id,
            order_type=order_type,
            package_order_id=order_id,
            schedule_id=target_group.schedule_id,
        )

        if success:
            return f"Successfully rescheduled delivery {group_id} to {new_date}"
        return f"Failed to reschedule delivery {group_id}"
    except ValueError as e:
        return f"Invalid date format. Use YYYY-MM-DD. Error: {e}"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def bulk_reschedule(
    order_id: int,
    start_date: str,
    end_date: str,
    target_start_date: str,
    order_types: Optional[str] = None,
) -> str:
    """
    Bulk reschedule all deliveries within a date range to new dates.

    This is useful when you need to "hold" deliveries for a period
    (e.g., when traveling) and want to shift them all to after you return.

    Args:
        order_id: The ID of the package order
        start_date: Start of the date range to reschedule (YYYY-MM-DD, inclusive)
        end_date: End of the date range to reschedule (YYYY-MM-DD, inclusive)
        target_start_date: The new start date for rescheduled deliveries (YYYY-MM-DD)
        order_types: Optional comma-separated types to reschedule ("LUNCH", "DINNER", or "LUNCH,DINNER").
                    If not specified, reschedules both lunch and dinner.

    Returns:
        Summary of rescheduling results
    """
    client = get_client()
    try:
        # Parse dates as Jakarta timezone for correct local date handling
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
        target = datetime.strptime(target_start_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)

        # Warn if target starts on Sunday (will auto-skip to Monday)
        if target.weekday() == 6:  # Sunday
            return f"Cannot start rescheduling on Sunday ({target_start_date}). Sundays are not available for delivery."

        types_list = None
        if order_types:
            types_list = [t.strip().upper() for t in order_types.split(",")]
            for t in types_list:
                if t not in ["LUNCH", "DINNER"]:
                    return f"Invalid order type: {t}. Must be 'LUNCH' or 'DINNER'"

        results = client.bulk_reschedule(
            order_id=order_id,
            start_date=start,
            end_date=end,
            target_start_date=target,
            order_types=types_list,
        )

        result = f"""Bulk Reschedule Results:
- Successful: {results['success_count']}
- Failed: {results['failed_count']}

"""

        if results['rescheduled']:
            result += "Rescheduled deliveries:\n"
            for group_id, old_date, new_date in results['rescheduled']:
                result += f"  - ID {group_id}: {old_date} -> {new_date}\n"

        if results['failed']:
            result += "\nFailed deliveries:\n"
            for group_id, error in results['failed']:
                result += f"  - ID {group_id}: {error}\n"

        return result
    except ValueError as e:
        return f"Invalid date format. Use YYYY-MM-DD. Error: {e}"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_available_addresses(order_id: int) -> list[dict]:
    """
    Get available delivery addresses for an order.

    Args:
        order_id: The ID of the package order

    Returns:
        List of available addresses with their IDs
    """
    client = get_client()
    addresses = client.get_available_addresses(order_id)

    if not addresses:
        return []

    return [
        {
            "address_id": addr.get("id"),
            "label": addr.get("label", ""),
            "address": addr.get("address", "Unknown"),
        }
        for addr in addresses
    ]


@mcp.tool()
def get_delivery_summary(order_id: int) -> dict:
    """
    Get a summary of delivery statistics.

    Args:
        order_id: The ID of the package order

    Returns:
        Summary with total, remaining, completed counts by type
    """
    client = get_client()
    order = client.get_order_details(order_id)
    groups = client.get_all_order_groups(order_id)
    # Use Jakarta timezone for correct local date comparison
    today = datetime.now(JAKARTA_TZ).replace(hour=0, minute=0, second=0, microsecond=0)

    lunch_total = sum(1 for g in groups if g.order_type == "LUNCH")
    dinner_total = sum(1 for g in groups if g.order_type == "DINNER")
    lunch_remaining = sum(1 for g in groups if g.order_type == "LUNCH" and g.scheduled_date >= today)
    dinner_remaining = sum(1 for g in groups if g.order_type == "DINNER" and g.scheduled_date >= today)
    editable = sum(1 for g in groups if g.is_editable)

    dates = [g.scheduled_date for g in groups]
    first_date = min(dates) if dates else None
    last_date = max(dates) if dates else None

    return {
        "package_name": order.package_name,
        "total_deliveries": len(groups),
        "lunch": {
            "total": lunch_total,
            "remaining": lunch_remaining,
            "completed": lunch_total - lunch_remaining,
        },
        "dinner": {
            "total": dinner_total,
            "remaining": dinner_remaining,
            "completed": dinner_total - dinner_remaining,
        },
        "editable_count": editable,
        "first_delivery": first_date.strftime("%Y-%m-%d") if first_date else None,
        "last_delivery": last_date.strftime("%Y-%m-%d") if last_date else None,
    }


@mcp.tool()
def skip_day(
    order_id: int,
    skip_date: str,
    order_types: Optional[str] = None,
) -> dict:
    """
    Skip deliveries on a specific date by moving them to the end of the schedule.

    Args:
        order_id: The ID of the package order
        skip_date: The date to skip (YYYY-MM-DD)
        order_types: Optional - "LUNCH", "DINNER", or "LUNCH,DINNER" (default: both)

    Returns:
        Summary of skipped deliveries
    """
    client = get_client()
    # Parse date as Jakarta timezone for correct local date handling
    skip_dt = datetime.strptime(skip_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)

    # Get all groups to find the last date
    groups = client.get_all_order_groups(order_id)
    last_date = max(g.scheduled_date for g in groups)

    # Filter groups for the skip date
    types_list = None
    if order_types:
        types_list = [t.strip().upper() for t in order_types.split(",")]

    to_skip = [
        g for g in groups
        if g.scheduled_date.date() == skip_dt.date()
        and g.is_editable
        and (types_list is None or g.order_type in types_list)
    ]

    if not to_skip:
        return {
            "success": False,
            "message": f"No editable deliveries found on {skip_date}",
            "skipped": [],
        }

    # Move each to the day after the last scheduled date (skip Sundays)
    skipped = []
    target_date = last_date + timedelta(days=1)
    # Skip Sunday
    while target_date.weekday() == 6:
        target_date += timedelta(days=1)

    for group in to_skip:
        success = client.reschedule_order(
            group_id=group.id,
            new_date=target_date,
            address_id=group.address_id,
            order_type=group.order_type,
            package_order_id=order_id,
            schedule_id=group.schedule_id,
        )
        if success:
            skipped.append({
                "group_id": group.id,
                "type": group.order_type,
                "from_date": skip_date,
                "to_date": target_date.strftime("%Y-%m-%d"),
            })
            target_date += timedelta(days=1)
            # Skip Sunday for next delivery
            while target_date.weekday() == 6:
                target_date += timedelta(days=1)

    return {
        "success": True,
        "message": f"Skipped {len(skipped)} deliveries from {skip_date}",
        "skipped": skipped,
    }


@mcp.tool()
def hold_deliveries(
    order_id: int,
    hold_start: str,
    hold_end: str,
    order_types: Optional[str] = None,
) -> dict:
    """
    Hold (pause) deliveries for a date range. All deliveries in the range
    will be moved to continue after the hold period ends.

    Args:
        order_id: The ID of the package order
        hold_start: Start of hold period (YYYY-MM-DD, inclusive)
        hold_end: End of hold period (YYYY-MM-DD, inclusive)
        order_types: Optional - "LUNCH", "DINNER", or "LUNCH,DINNER" (default: both)

    Returns:
        Summary of held deliveries
    """
    client = get_client()
    # Parse dates as Jakarta timezone for correct local date handling
    start = datetime.strptime(hold_start, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
    end = datetime.strptime(hold_end, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)

    # Resume date is the day after hold ends
    resume_date = end + timedelta(days=1)

    types_list = None
    if order_types:
        types_list = [t.strip().upper() for t in order_types.split(",")]

    results = client.bulk_reschedule(
        order_id=order_id,
        start_date=start,
        end_date=end,
        target_start_date=resume_date,
        order_types=types_list,
    )

    return {
        "success": results['success_count'] > 0,
        "hold_period": f"{hold_start} to {hold_end}",
        "resume_date": resume_date.strftime("%Y-%m-%d"),
        "deliveries_held": results['success_count'],
        "failed": results['failed_count'],
        "details": [
            {
                "group_id": gid,
                "from": old,
                "to": new,
            }
            for gid, old, new in results['rescheduled']
        ],
    }


@mcp.tool()
def change_address(
    order_id: int,
    new_address_id: int,
    date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    order_types: Optional[str] = None,
) -> dict:
    """
    Change delivery address for specific deliveries.

    Args:
        order_id: The ID of the package order
        new_address_id: The new address ID to use
        date: Single date to change (YYYY-MM-DD) - use this OR start_date/end_date
        start_date: Start of date range (YYYY-MM-DD)
        end_date: End of date range (YYYY-MM-DD)
        order_types: Optional - "LUNCH", "DINNER", or "LUNCH,DINNER" (default: both)

    Returns:
        Summary of address changes
    """
    client = get_client()

    # Determine date range - parse as Jakarta timezone for correct local date handling
    if date:
        start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
        end = start
    elif start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
    else:
        return {
            "success": False,
            "message": "Provide either 'date' or both 'start_date' and 'end_date'",
            "changed": [],
        }

    types_list = None
    if order_types:
        types_list = [t.strip().upper() for t in order_types.split(",")]

    # Get deliveries in range
    groups = client.get_orders_by_date_range(order_id, start, end)

    if types_list:
        groups = [g for g in groups if g.order_type in types_list]

    if not groups:
        return {
            "success": False,
            "message": "No deliveries found in the specified range",
            "changed": [],
        }

    changed = []
    for group in groups:
        if not group.is_editable:
            continue

        # Reschedule to same date but with new address
        success = client.reschedule_order(
            group_id=group.id,
            new_date=group.scheduled_date,
            address_id=new_address_id,
            order_type=group.order_type,
            package_order_id=order_id,
            schedule_id=group.schedule_id,
        )
        if success:
            changed.append({
                "group_id": group.id,
                "date": group.scheduled_date.strftime("%Y-%m-%d"),
                "type": group.order_type,
                "new_address_id": new_address_id,
            })

    return {
        "success": len(changed) > 0,
        "message": f"Changed address for {len(changed)} deliveries",
        "changed": changed,
    }


def main():
    """Run the MCP server."""
    # Check if running in HTTP mode (for Smithery deployment)
    if "--http" in sys.argv or os.environ.get("MCP_HTTP_MODE"):
        import uvicorn
        from starlette.middleware.cors import CORSMiddleware

        # Get the Starlette app for HTTP transport
        app = mcp.streamable_http_app()

        # Add CORS middleware for browser-based clients
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["mcp-session-id", "mcp-protocol-version"],
            max_age=86400,
        )

        # Get port from environment (Smithery sets PORT)
        port = int(os.environ.get("PORT", 8081))
        print(f"Starting Warlon MCP Server in HTTP mode on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    else:
        # Default: run in stdio mode for local use
        mcp.run()


if __name__ == "__main__":
    main()
