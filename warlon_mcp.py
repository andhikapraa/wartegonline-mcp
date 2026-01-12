"""
Warteg Online MCP Server

An MCP server that exposes the Warteg Online API functionality as tools.
Allows AI assistants to interact with the catering platform for managing
delivery schedules.

Usage:
    Local:  uv run dev
    Playground: uv run playground
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from smithery.decorators import smithery

from warlon_client import WarlonClient, JAKARTA_TZ


class ConfigSchema(BaseModel):
    """Session configuration schema for Smithery."""
    warlon_username: Optional[str] = Field(None, description="Your Warteg Online account username")
    warlon_password: Optional[str] = Field(None, description="Your Warteg Online account password")


# Client cache per session
_clients: dict[int, WarlonClient] = {}


def get_client(ctx: Context) -> WarlonClient:
    """Get or create a WarlonClient for the current session."""
    session_id = id(ctx)

    if session_id not in _clients:
        _clients[session_id] = WarlonClient()

        # Try session config first, then fall back to environment variables
        username = None
        password = None

        config = ctx.session_config
        if config:
            username = getattr(config, 'warlon_username', None)
            password = getattr(config, 'warlon_password', None)

        # Fall back to environment variables
        if not username:
            username = os.environ.get('WARLON_USERNAME')
        if not password:
            password = os.environ.get('WARLON_PASSWORD')

        if username and password:
            _clients[session_id].login(username, password)

    return _clients[session_id]


@smithery.server(config_schema=ConfigSchema)
def create_server() -> FastMCP:
    """Create and return the Warteg Online MCP server."""

    server = FastMCP(name="Warteg Online")

    @server.tool()
    def login(username: str, password: str, ctx: Context) -> str:
        """
        Authenticate with the Warteg Online platform.

        Args:
            username: Your Warteg Online username
            password: Your Warteg Online password

        Returns:
            Success or failure message
        """
        client = get_client(ctx)
        if client.login(username, password):
            return f"Successfully logged in as {username}"
        return "Login failed. Please check your credentials."

    @server.tool()
    def get_package_orders(ctx: Context) -> list[dict]:
        """
        Get all package orders for the authenticated user.

        Returns:
            List of package orders with their IDs and names
        """
        client = get_client(ctx)
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

    @server.tool()
    def get_order_details(order_id: int, ctx: Context) -> dict:
        """
        Get detailed information about a specific package order.

        Args:
            order_id: The ID of the package order

        Returns:
            Detailed information about the order
        """
        client = get_client(ctx)
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

    @server.tool()
    def get_schedule(order_id: int, ctx: Context) -> dict:
        """
        Get the full delivery schedule for an order.

        Args:
            order_id: The ID of the package order

        Returns:
            Formatted schedule showing all deliveries
        """
        client = get_client(ctx)
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

    @server.tool()
    def get_orders_by_date_range(order_id: int, start_date: str, end_date: str, ctx: Context) -> dict:
        """
        Get all deliveries within a specific date range.

        Args:
            order_id: The ID of the package order
            start_date: Start date in YYYY-MM-DD format (inclusive)
            end_date: End date in YYYY-MM-DD format (inclusive)

        Returns:
            List of deliveries within the date range
        """
        client = get_client(ctx)
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

    @server.tool()
    def reschedule_delivery(
        order_id: int,
        group_id: int,
        new_date: str,
        address_id: int,
        order_type: str,
        ctx: Context,
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
        client = get_client(ctx)
        try:
            new_datetime = datetime.strptime(new_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)

            if new_datetime.weekday() == 6:
                return f"Cannot schedule delivery on Sunday ({new_date}). Please choose a different date."

            if order_type not in ["LUNCH", "DINNER"]:
                return "order_type must be either 'LUNCH' or 'DINNER'"

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
        except Exception as e:
            return f"Error: {e}"

    @server.tool()
    def bulk_reschedule(
        order_id: int,
        start_date: str,
        end_date: str,
        target_start_date: str,
        ctx: Context,
        order_types: Optional[str] = None,
    ) -> str:
        """
        Bulk reschedule all deliveries within a date range to new dates.

        Args:
            order_id: The ID of the package order
            start_date: Start of the date range to reschedule (YYYY-MM-DD)
            end_date: End of the date range to reschedule (YYYY-MM-DD)
            target_start_date: The new start date for rescheduled deliveries
            order_types: Optional - "LUNCH", "DINNER", or "LUNCH,DINNER"

        Returns:
            Summary of rescheduling results
        """
        client = get_client(ctx)
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
            target = datetime.strptime(target_start_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)

            if target.weekday() == 6:
                return f"Cannot start rescheduling on Sunday ({target_start_date})."

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

            result = f"Bulk Reschedule Results:\n- Successful: {results['success_count']}\n- Failed: {results['failed_count']}\n"

            if results['rescheduled']:
                result += "\nRescheduled deliveries:\n"
                for group_id, old_date, new_date in results['rescheduled']:
                    result += f"  - ID {group_id}: {old_date} -> {new_date}\n"

            return result
        except ValueError as e:
            return f"Invalid date format. Use YYYY-MM-DD. Error: {e}"
        except Exception as e:
            return f"Error: {e}"

    @server.tool()
    def get_available_addresses(order_id: int, ctx: Context) -> list[dict]:
        """
        Get available delivery addresses for an order.

        Args:
            order_id: The ID of the package order

        Returns:
            List of available addresses with their IDs
        """
        client = get_client(ctx)
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

    @server.tool()
    def get_delivery_summary(order_id: int, ctx: Context) -> dict:
        """
        Get a summary of delivery statistics.

        Args:
            order_id: The ID of the package order

        Returns:
            Summary with total, remaining, completed counts by type
        """
        client = get_client(ctx)
        order = client.get_order_details(order_id)
        groups = client.get_all_order_groups(order_id)
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
            "lunch": {"total": lunch_total, "remaining": lunch_remaining, "completed": lunch_total - lunch_remaining},
            "dinner": {"total": dinner_total, "remaining": dinner_remaining, "completed": dinner_total - dinner_remaining},
            "editable_count": editable,
            "first_delivery": first_date.strftime("%Y-%m-%d") if first_date else None,
            "last_delivery": last_date.strftime("%Y-%m-%d") if last_date else None,
        }

    @server.tool()
    def skip_day(order_id: int, skip_date: str, ctx: Context, order_types: Optional[str] = None) -> dict:
        """
        Skip deliveries on a specific date by moving them to the end of the schedule.

        Args:
            order_id: The ID of the package order
            skip_date: The date to skip (YYYY-MM-DD)
            order_types: Optional - "LUNCH", "DINNER", or "LUNCH,DINNER"

        Returns:
            Summary of skipped deliveries
        """
        client = get_client(ctx)
        skip_dt = datetime.strptime(skip_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)

        groups = client.get_all_order_groups(order_id)
        last_date = max(g.scheduled_date for g in groups)

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
            return {"success": False, "message": f"No editable deliveries found on {skip_date}", "skipped": []}

        skipped = []
        target_date = last_date + timedelta(days=1)
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
                while target_date.weekday() == 6:
                    target_date += timedelta(days=1)

        return {"success": True, "message": f"Skipped {len(skipped)} deliveries from {skip_date}", "skipped": skipped}

    @server.tool()
    def hold_deliveries(order_id: int, hold_start: str, hold_end: str, ctx: Context, order_types: Optional[str] = None) -> dict:
        """
        Hold (pause) deliveries for a date range.

        Args:
            order_id: The ID of the package order
            hold_start: Start of hold period (YYYY-MM-DD)
            hold_end: End of hold period (YYYY-MM-DD)
            order_types: Optional - "LUNCH", "DINNER", or "LUNCH,DINNER"

        Returns:
            Summary of held deliveries
        """
        client = get_client(ctx)
        start = datetime.strptime(hold_start, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
        end = datetime.strptime(hold_end, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
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
        }

    @server.tool()
    def change_address(
        order_id: int,
        new_address_id: int,
        ctx: Context,
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
            date: Single date to change (YYYY-MM-DD)
            start_date: Start of date range (YYYY-MM-DD)
            end_date: End of date range (YYYY-MM-DD)
            order_types: Optional - "LUNCH", "DINNER", or "LUNCH,DINNER"

        Returns:
            Summary of address changes
        """
        client = get_client(ctx)

        if date:
            start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
            end = start
        elif start_date and end_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=JAKARTA_TZ)
        else:
            return {"success": False, "message": "Provide either 'date' or both 'start_date' and 'end_date'", "changed": []}

        types_list = None
        if order_types:
            types_list = [t.strip().upper() for t in order_types.split(",")]

        groups = client.get_orders_by_date_range(order_id, start, end)
        if types_list:
            groups = [g for g in groups if g.order_type in types_list]

        if not groups:
            return {"success": False, "message": "No deliveries found in the specified range", "changed": []}

        changed = []
        for group in groups:
            if not group.is_editable:
                continue

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

        return {"success": len(changed) > 0, "message": f"Changed address for {len(changed)} deliveries", "changed": changed}

    @server.tool()
    def get_available_restrictions(ctx: Context) -> dict:
        """
        Get all available dietary restrictions (pantangan) that can be set.

        Returns:
            List of available restrictions grouped by category
        """
        client = get_client(ctx)
        restrictions = client.get_available_restrictions()

        grouped = {}
        for r in restrictions:
            group_name = r.get("packageRestrictionGroup", {}).get("name", "Other")
            if group_name not in grouped:
                grouped[group_name] = []
            grouped[group_name].append({"id": r.get("id"), "name": r.get("name")})

        return {
            "restrictions_by_group": grouped,
            "all_restrictions": [{"id": r.get("id"), "name": r.get("name")} for r in restrictions],
        }

    @server.tool()
    def get_my_restrictions(ctx: Context) -> dict:
        """
        Get the current user's dietary restrictions (pantangan).

        Returns:
            List of the user's current dietary restrictions
        """
        client = get_client(ctx)
        restrictions = client.get_user_restrictions()

        if not restrictions:
            return {"has_restrictions": False, "message": "No dietary restrictions set", "restrictions": []}

        return {
            "has_restrictions": True,
            "count": len(restrictions),
            "restrictions": [
                {"id": r.get("packageRestriction", {}).get("id"), "name": r.get("packageRestriction", {}).get("name")}
                for r in restrictions
            ],
        }

    @server.tool()
    def update_restrictions(ctx: Context, restriction_ids: Optional[str] = None) -> dict:
        """
        Update the user's dietary restrictions (pantangan).

        Args:
            restriction_ids: Comma-separated list of restriction IDs to set.
                            Use empty string or omit to clear all restrictions.

        Available IDs:
            Protein: 1=No Udang, 2=No Ikan, 3=No Sapi, 13=No Cumi, 15=No Seafood
            Additional: 4=No Kecombrang, 7=No Sayur, 10=No Telur, 12=No Olahan Susu, 14=No Kacang
            Rasa: 5=No Pedas, 11=No Mayo

        Returns:
            Result of the update operation
        """
        client = get_client(ctx)

        ids_list = []
        if restriction_ids and restriction_ids.strip():
            try:
                ids_list = [int(id.strip()) for id in restriction_ids.split(",")]
            except ValueError:
                return {"success": False, "message": "Invalid restriction IDs. Use comma-separated numbers (e.g., '5,11')"}

        result = client.update_restrictions(ids_list)

        if result["success"]:
            updated = [
                {"id": r.get("packageRestriction", {}).get("id"), "name": r.get("packageRestriction", {}).get("name")}
                for r in result["restrictions"]
            ]
            return {
                "success": True,
                "message": result["message"],
                "restrictions_set": len(updated),
                "restrictions": updated if updated else "None (all restrictions cleared)",
            }

        return {"success": False, "message": result["message"]}

    return server


# For local development
def main():
    """Run the MCP server locally."""
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
