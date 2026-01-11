"""
Warlon Catering API Client

A Python class to interact with the Warlon self-service catering platform.
Supports authentication, fetching orders, and rescheduling deliveries.

Usage:
    from warlon_client import WarlonClient

    client = WarlonClient()
    client.login("username", "password")

    # Get all orders
    orders = client.get_package_orders()

    # Get specific order details
    order = client.get_order_details(order_id)

    # Reschedule a delivery
    client.reschedule_order(group_id, new_date, address_id, order_type, notes)

    # Bulk reschedule multiple days
    client.bulk_reschedule(order_id, start_date, end_date, days_to_shift)
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from zoneinfo import ZoneInfo

# Jakarta timezone (UTC+7)
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")


@dataclass
class OrderGroup:
    """Represents a single order (Lunch or Dinner) for a specific day"""
    id: int
    schedule_id: int
    scheduled_date: datetime
    order_type: str  # "LUNCH" or "DINNER"
    status: str
    address_id: int
    address: Optional[str]
    notes: List[str]

    @property
    def is_editable(self) -> bool:
        return self.status == "SCHEDULED"


@dataclass
class PackageOrder:
    """Represents a customer's package order with all schedules"""
    id: int
    user_id: int
    package_id: int
    package_name: str
    package_description: str
    total_days: int
    lunch_amount: int
    dinner_amount: int
    schedules: List[Dict]
    addresses: List[Dict]


class WarlonClient:
    """
    Client for interacting with the Warlon Catering self-service API.

    This client allows you to:
    - Authenticate with username/password
    - Fetch package orders and their details
    - Reschedule individual deliveries
    - Bulk reschedule multiple deliveries at once
    """

    BASE_URL = "https://customer.warloncatering.com"

    def __init__(self):
        self.session = requests.Session()
        # Use browser-like headers to avoid Cloudflare blocking
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/login",
        })
        self._user_data: Optional[Dict] = None
        self._is_authenticated = False

    def login(self, username: str, password: str) -> bool:
        """
        Authenticate with the Warlon API.

        Args:
            username: Your Warlon username
            password: Your Warlon password

        Returns:
            True if login was successful, False otherwise
        """
        # First, visit the login page to get any required cookies
        try:
            self.session.get(f"{self.BASE_URL}/login")
        except requests.RequestException:
            pass  # Continue even if this fails

        url = f"{self.BASE_URL}/api/auth/login"
        payload = {
            "username": username,
            "password": password
        }

        try:
            response = self.session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()

            # Handle different response structures
            message = data.get("message", "").lower()
            if "login successful" in message or "success" in message:
                self._user_data = data.get("data") or {}
                self._is_authenticated = True
                name = self._user_data.get('name', username) if self._user_data else username
                print(f"Successfully logged in as: {name}")
                return True
            elif "data" in data and data["data"]:
                self._user_data = data["data"]
                self._is_authenticated = True
                print(f"Successfully logged in as: {self._user_data.get('name', username)}")
                return True

            print(f"Unexpected login response: {data}")
            return False

        except requests.RequestException as e:
            print(f"Login failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response text: {e.response.text[:500] if e.response.text else 'No text'}")
            return False

    def check_auth(self) -> bool:
        """Check if the current session is authenticated."""
        url = f"{self.BASE_URL}/api/auth/check"
        try:
            response = self.session.get(url)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_package_orders(self) -> List[Dict]:
        """
        Get all package orders for the authenticated user.

        Returns:
            List of package orders
        """
        if not self._is_authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f"{self.BASE_URL}/api/customer-package-orders"
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()

        # Handle nested response structure: {"data": {"data": [...], "total": N}}
        result = data.get("data", {})
        if isinstance(result, dict):
            return result.get("data", [])
        return result if isinstance(result, list) else []

    def get_order_details(self, order_id: int) -> PackageOrder:
        """
        Get detailed information about a specific package order.

        Args:
            order_id: The ID of the package order

        Returns:
            PackageOrder object with all details
        """
        if not self._is_authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f"{self.BASE_URL}/api/customer-package-orders/{order_id}"
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()

        order_data = data.get("data", {})

        return PackageOrder(
            id=order_data["id"],
            user_id=order_data["userId"],
            package_id=order_data["packageId"],
            package_name=order_data["packageName"],
            package_description=order_data.get("packageDescription", ""),
            total_days=order_data["totalDays"],
            lunch_amount=order_data["lunchAmount"],
            dinner_amount=order_data["dinnerAmount"],
            schedules=order_data.get("userPackageOrderSchedules", []),
            addresses=order_data.get("user", {}).get("addresses", [])
        )

    def get_all_order_groups(self, order_id: int) -> List[OrderGroup]:
        """
        Get all individual order groups (Lunch/Dinner items) for a package order.

        Args:
            order_id: The ID of the package order

        Returns:
            List of OrderGroup objects
        """
        order = self.get_order_details(order_id)
        groups = []

        for schedule in order.schedules:
            # Parse UTC date and convert to Jakarta timezone for correct date handling
            utc_date = datetime.fromisoformat(
                schedule["scheduledDate"].replace("Z", "+00:00")
            )
            scheduled_date = utc_date.astimezone(JAKARTA_TZ)

            for group in schedule.get("userPackageOrderGroups", []):
                notes = []
                for detail in group.get("userPackageOrderDetails", []):
                    if detail.get("note"):
                        notes.append(detail["note"])

                # Handle both customerAddressId and customerAddress.id
                customer_address = group.get("customerAddress", {})
                address_id = group.get("customerAddressId") or customer_address.get("id")
                address_str = customer_address.get("address") if customer_address else group.get("address")

                groups.append(OrderGroup(
                    id=group["id"],
                    schedule_id=schedule["id"],
                    scheduled_date=scheduled_date,
                    order_type=group["type"],
                    status=group["status"],
                    address_id=address_id,
                    address=address_str,
                    notes=notes
                ))

        return groups

    def reschedule_order(
        self,
        group_id: int,
        new_date: datetime,
        address_id: int,
        order_type: str,
        package_order_id: int,
        schedule_id: int,
        notes: Optional[List[str]] = None,
        delivery_time: Optional[str] = None,
    ) -> bool:
        """
        Reschedule a single order to a new date.

        Args:
            group_id: The ID of the order group to reschedule
            new_date: The new delivery date
            address_id: The address ID for delivery
            order_type: "LUNCH" or "DINNER"
            package_order_id: The ID of the package order
            schedule_id: The ID of the schedule
            notes: Optional list of notes for each item
            delivery_time: Optional delivery time (e.g., "12:00 - 13:00")

        Returns:
            True if successful, False otherwise
        """
        if not self._is_authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f"{self.BASE_URL}/api/customer-package-orders/edit-order"

        # Format date as ISO string (the API expects this format)
        date_str = new_date.strftime("%Y-%m-%d")

        # Default delivery times based on meal type
        if delivery_time is None:
            delivery_time = "12:00 - 13:00" if order_type == "LUNCH" else "18:00 - 19:00"

        payload = {
            "packageOrderId": str(package_order_id),
            "orderGroupId": f"{schedule_id}-{group_id}",
            "scheduledDate": date_str,
            "customerAddressId": address_id,
            "mealType": order_type,
            "notes": notes or [],
            "cutlery": False,
            "deliveryTime": delivery_time,
            "historyNote": ""
        }

        try:
            response = self.session.put(url, json=payload)
            response.raise_for_status()
            print(f"Successfully rescheduled order {group_id} to {date_str}")
            return True
        except requests.RequestException as e:
            print(f"Failed to reschedule order {group_id}: {e}")
            return False

    def bulk_reschedule(
        self,
        order_id: int,
        start_date: datetime,
        end_date: datetime,
        target_start_date: datetime,
        order_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Bulk reschedule all orders within a date range to new dates.

        This is useful when you need to "hold" deliveries for a period of time
        (e.g., when traveling) and want to shift them all to after you return.

        Args:
            order_id: The ID of the package order
            start_date: Start of the date range to reschedule (inclusive)
            end_date: End of the date range to reschedule (inclusive)
            target_start_date: The new start date for rescheduled orders
            order_types: Optional list of types to reschedule ("LUNCH", "DINNER", or both)
                        If None, reschedules both lunch and dinner

        Returns:
            Dictionary with results:
            {
                "success_count": int,
                "failed_count": int,
                "rescheduled": List of (group_id, old_date, new_date),
                "failed": List of (group_id, error_message)
            }
        """
        if order_types is None:
            order_types = ["LUNCH", "DINNER"]

        results = {
            "success_count": 0,
            "failed_count": 0,
            "rescheduled": [],
            "failed": []
        }

        # Get all order groups
        groups = self.get_all_order_groups(order_id)

        # Filter groups within date range
        groups_to_reschedule = []
        for group in groups:
            group_date = group.scheduled_date.date()
            if (start_date.date() <= group_date <= end_date.date() and
                group.order_type in order_types and
                group.is_editable):
                groups_to_reschedule.append(group)

        # Sort by date
        groups_to_reschedule.sort(key=lambda g: (g.scheduled_date, g.order_type))

        print(f"Found {len(groups_to_reschedule)} orders to reschedule")

        # Calculate new dates - maintain the same pattern (skip Sundays)
        current_target = target_start_date
        day_mapping = {}  # old_date -> new_date

        for group in groups_to_reschedule:
            old_date = group.scheduled_date.date()

            if old_date not in day_mapping:
                # Skip Sundays for target date
                while current_target.weekday() == 6:  # Sunday
                    current_target += timedelta(days=1)

                day_mapping[old_date] = current_target
                current_target += timedelta(days=1)

            new_date = day_mapping[old_date]

            # Create datetime with same time as original
            new_datetime = datetime.combine(new_date, group.scheduled_date.time())

            success = self.reschedule_order(
                group_id=group.id,
                new_date=new_datetime,
                address_id=group.address_id,
                order_type=group.order_type,
                package_order_id=order_id,
                schedule_id=group.schedule_id,
                notes=group.notes if group.notes else None
            )

            if success:
                results["success_count"] += 1
                results["rescheduled"].append((group.id, old_date, new_date))
            else:
                results["failed_count"] += 1
                results["failed"].append((group.id, "Reschedule failed"))

        return results

    def get_orders_by_date_range(
        self,
        order_id: int,
        start_date: datetime,
        end_date: datetime
    ) -> List[OrderGroup]:
        """
        Get all orders within a specific date range.

        Args:
            order_id: The ID of the package order
            start_date: Start of the date range (inclusive)
            end_date: End of the date range (inclusive)

        Returns:
            List of OrderGroup objects within the date range
        """
        groups = self.get_all_order_groups(order_id)

        filtered = []
        for group in groups:
            group_date = group.scheduled_date.date()
            if start_date.date() <= group_date <= end_date.date():
                filtered.append(group)

        return sorted(filtered, key=lambda g: (g.scheduled_date, g.order_type))

    def print_schedule(self, order_id: int):
        """
        Print a formatted schedule of all orders.

        Args:
            order_id: The ID of the package order
        """
        order = self.get_order_details(order_id)
        groups = self.get_all_order_groups(order_id)

        print(f"\n{'='*60}")
        print(f"Package: {order.package_name}")
        print(f"Description: {order.package_description}")
        print(f"Total Days: {order.total_days}")
        print(f"{'='*60}\n")

        current_date = None
        for group in sorted(groups, key=lambda g: (g.scheduled_date, g.order_type)):
            group_date = group.scheduled_date.date()

            if current_date != group_date:
                current_date = group_date
                day_name = group_date.strftime("%A")
                print(f"\n{group_date.strftime('%Y-%m-%d')} ({day_name})")
                print("-" * 40)

            status_icon = "✓" if group.status == "SCHEDULED" else "✗"
            editable = "[Editable]" if group.is_editable else "[Locked]"
            print(f"  {status_icon} {group.order_type:<8} ID:{group.id} {editable}")

    def get_available_addresses(self, order_id: int) -> List[Dict]:
        """
        Get available delivery addresses for an order.

        Args:
            order_id: The ID of the package order

        Returns:
            List of address dictionaries
        """
        order = self.get_order_details(order_id)
        return order.addresses

    def get_available_restrictions(self) -> List[Dict]:
        """
        Get all available dietary restrictions (pantangan).

        Returns:
            List of restriction dictionaries with id, name, and group
        """
        if not self._is_authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f"{self.BASE_URL}/api/package-restrictions/available"
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()

        return data.get("data", [])

    def get_user_restrictions(self) -> List[Dict]:
        """
        Get the current user's dietary restrictions.

        Returns:
            List of the user's current restrictions
        """
        if not self._is_authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

        # The user's restrictions are returned in the user data from various endpoints
        # We can get them by making a request that returns user data
        url = f"{self.BASE_URL}/api/customer-package-orders"
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()

        # Extract user restrictions from the response
        result = data.get("data", {})
        if isinstance(result, dict):
            orders = result.get("data", [])
            if orders and len(orders) > 0:
                user = orders[0].get("user", {})
                return user.get("userPackageRestrictions", [])
        return []

    def update_restrictions(self, restriction_ids: List[int]) -> Dict:
        """
        Update the user's dietary restrictions.

        Args:
            restriction_ids: List of restriction IDs to set.
                           Empty list removes all restrictions.

        Returns:
            Dictionary with success status and updated restrictions
        """
        if not self._is_authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f"{self.BASE_URL}/api/users/restrictions-update"
        payload = {"restrictionIds": restriction_ids}

        try:
            response = self.session.put(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "message": data.get("message", "Restrictions updated"),
                "restrictions": data.get("data", [])
            }
        except requests.RequestException as e:
            return {
                "success": False,
                "message": f"Failed to update restrictions: {e}",
                "restrictions": []
            }


def main():
    """Example usage of the WarlonClient."""
    import os

    # Initialize client
    client = WarlonClient()

    # Get credentials from environment variables
    username = os.environ.get("WARLON_USERNAME")
    password = os.environ.get("WARLON_PASSWORD")

    if not username or not password:
        print("Error: Please set WARLON_USERNAME and WARLON_PASSWORD environment variables")
        print("Example:")
        print("  export WARLON_USERNAME='your_username'")
        print("  export WARLON_PASSWORD='your_password'")
        return

    # Login
    if not client.login(username, password):
        print("Login failed!")
        return

    # Get all orders
    orders = client.get_package_orders()
    print(f"\nFound {len(orders)} package order(s)")

    if orders:
        # Get first order details - handle both list and dict responses
        if isinstance(orders, list):
            first_order = orders[0]
        elif isinstance(orders, dict):
            first_order = list(orders.values())[0] if orders else None
        else:
            first_order = None

        if not first_order:
            print("No orders found")
            return

        order_id = first_order.get("id") or first_order.get("userPackageOrderId")
        print(f"\nFetching details for order ID: {order_id}")

        # Print schedule
        client.print_schedule(order_id)


if __name__ == "__main__":
    main()
