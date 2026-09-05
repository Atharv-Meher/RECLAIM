"""
Razorpay API Adapter for RECLAIM.

Integrates with Razorpay test-mode API to generate real payment links
for the `alternate_payment_method` action.

Loads credentials from `.env` or environment variables:
  - RAZORPAY_KEY_ID
  - RAZORPAY_KEY_SECRET

If credentials are not configured or invalid, provides clear diagnostic
feedback and falls back cleanly to simulation.
"""

import os
from pathlib import Path

try:
    import razorpay
    RAZORPAY_SDK_AVAILABLE = True
except ImportError:
    razorpay = None
    RAZORPAY_SDK_AVAILABLE = False


def load_env(env_path: str | None = None) -> dict[str, str]:
    """Parse a simple .env file into a dictionary and set into os.environ."""
    if env_path is None:
        # Default to repo root .env
        env_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        )

    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    env_vars[key] = val
                    if key not in os.environ or not os.environ[key]:
                        os.environ[key] = val
    return env_vars


# Load on import
load_env()


class RazorpayAdapter:
    """
    Adapter for Razorpay test-mode Payment Links API.

    Used when `alternate_payment_method` is executed to generate
    an actual payment link that customers can open and pay.
    """

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
    ):
        load_env()
        self.key_id = key_id or os.environ.get("RAZORPAY_KEY_ID", "")
        self.key_secret = key_secret or os.environ.get("RAZORPAY_KEY_SECRET", "")
        self._client = None

        if self.is_configured() and RAZORPAY_SDK_AVAILABLE:
            try:
                self._client = razorpay.Client(
                    auth=(self.key_id, self.key_secret)
                )
            except Exception as e:
                self._client = None

    def is_configured(self) -> bool:
        """Check if valid, non-placeholder credentials are provided."""
        if not RAZORPAY_SDK_AVAILABLE:
            return False
        if not self.key_id or not self.key_secret:
            return False
        if "YOUR_KEY_ID_HERE" in self.key_id or "YOUR_KEY_SECRET_HERE" in self.key_secret:
            return False
        if not self.key_id.startswith("rzp_"):
            return False
        return True

    def verify_credentials(self) -> tuple[bool, str]:
        """
        Verify credentials by querying Razorpay API.

        Returns (is_valid, message).
        """
        if not RAZORPAY_SDK_AVAILABLE:
            return False, "Razorpay SDK not installed (pip install razorpay)"
        if not self.is_configured():
            return False, "Razorpay credentials not configured in .env (or using placeholder values)"

        try:
            # Query the payment links API with a limit of 1 as a lightweight connectivity test
            res = self._client.payment_link.all({"count": 1})
            return True, "Razorpay API connected successfully (Test Mode)"
        except razorpay.errors.BadRequestError as e:
            return False, f"Razorpay API Bad Request: {e}"
        except razorpay.errors.ServerError as e:
            return False, f"Razorpay Server Error: {e}"
        except Exception as e:
            return False, f"Razorpay API Connection failed: {e}"

    def create_payment_link(
        self,
        case_id: str,
        amount: float,
        description: str | None = None,
        customer_email: str | None = None,
        customer_phone: str | None = None,
        root_cause: str | None = None,
    ) -> dict:
        """
        Create a live Razorpay Payment Link for a case.

        Args:
            case_id: The ID of the case (e.g. PF-0001)
            amount: Transaction amount in INR (will be converted to paise)
            description: Optional custom payment description
            customer_email: Optional recipient email
            customer_phone: Optional recipient phone number
            root_cause: Diagnosed root cause for metadata notes

        Returns:
            Dict containing:
              - id: Payment link ID (e.g. 'plink_xxxxxxxxxx')
              - short_url: The actual payment link URL (e.g. 'https://rzp.io/i/xxxxxx')
              - status: 'created'
              - amount: amount in INR
              - amount_paise: amount in paise
              - currency: 'INR'
        """
        if not self.is_configured():
            raise RuntimeError(
                "Cannot create Razorpay Payment Link: credentials not configured in .env"
            )

        amount_paise = int(round(amount * 100))
        desc = description or f"RECLAIM Recovery for {case_id}"
        email = customer_email or f"{case_id.lower().replace('-', '')}@example.com"
        phone = customer_phone or "+919876543210"

        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": desc,
            "customer": {
                "name": f"Customer {case_id}",
                "email": email,
                "contact": phone,
            },
            "notify": {
                "sms": False,
                "email": False,
            },
            "reminder_enable": True,
            "notes": {
                "case_id": case_id,
                "agent": "RECLAIM",
                "root_cause": root_cause or "recovery",
            },
        }

        response = self._client.payment_link.create(payload)

        return {
            "id": response.get("id"),
            "short_url": response.get("short_url"),
            "status": response.get("status"),
            "amount": amount,
            "amount_paise": amount_paise,
            "currency": "INR",
            "raw_response": response,
        }

    def fetch_payment_link(self, link_id: str) -> dict:
        """Fetch the current status of a payment link by ID."""
        if not self.is_configured():
            raise RuntimeError("Credentials not configured.")
        return self._client.payment_link.fetch(link_id)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print("\n--- Razorpay API Diagnostics ---")
    adapter = RazorpayAdapter()
    print(f"Key ID configured: {'Yes (' + adapter.key_id[:8] + '...)' if adapter.is_configured() else 'No (or placeholder in .env)'}")

    is_valid, msg = adapter.verify_credentials()
    print(f"Connection Status: {msg}")

    if is_valid:
        print("\nCreating test payment link (₹100)...")
        try:
            link = adapter.create_payment_link(
                case_id="TEST-0001",
                amount=100.0,
                description="RECLAIM Test Mode Verification Link",
            )
            print(f"✔ Payment Link Created: {link['short_url']} (ID: {link['id']})")
        except Exception as e:
            print(f"✖ Failed to create link: {e}")
    else:
        print("\n👉 To enable real Razorpay links, add your test keys to the .env file:")
        print("   RAZORPAY_KEY_ID=rzp_test_...")
        print("   RAZORPAY_KEY_SECRET=...")
