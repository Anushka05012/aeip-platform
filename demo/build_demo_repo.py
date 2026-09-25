"""Build and publish "PayFlow", a demo repository that exercises every AEIP feature.

    python demo/build_demo_repo.py build   <folder>               # local git repo, verified step by step
    python demo/build_demo_repo.py publish <folder> <repo-name>   # push to GitHub + open pull requests

The history is scripted so the CI outcomes are known in advance:

  main  c1  initial service                         CI green
        c2  full refunds                            CI green
        c3  retry transient gateway errors          CI green
        c4  refactor payment flow                   CI RED: KeyError raised in service.py  -> related
        c5  fix idempotency lookup                  CI green
        c6  point deploy at new registry            CI RED: registry DNS failure after a config
                                                    change -> related (misconfiguration)
        c7  revert registry                         CI green
        c8  webhook signature check                 CI green
        c9  order discounts                         CI green
        c10 runbook update (docs only)              CI green
        c11 gateway sandbox smoke test              CI green
        c12 runbook on-call notes (docs only)       CI RED: simulated sandbox outage -> unrelated
        c13 README link (docs only)                 CI green
  PR  feature/partial-refunds   (open)              CI RED: ValueError raised in refunds.py -> related, linked to PR
  PR  fix/token-expiry          (merged)            CI green
  PR  feature/currency-format   (open)              CI green

Every commit is tested locally during `build`; the script stops if an outcome differs
from the plan. `publish` needs GITHUB_TOKEN with permission to create repositories,
push contents and workflows, and open/merge pull requests.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path


def d(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


# --------------------------------------------------------------------------- files
BASE = {
    "README.md": d("""
        # PayFlow

        PayFlow is a small payments service: it charges customers through a payment gateway,
        exactly once per idempotency key, and supports refunds, order totals and short-lived
        API tokens for the operations dashboard.

        This repository is a demonstration project for **AEIP (AI Engineering Intelligence
        Platform)**. Its history deliberately contains CI failures of different kinds so AEIP's
        failure analysis, risk scoring and repository Q&A can be shown on real GitHub data.

        ## Layout

        - `src/payflow/service.py` – payment processing with idempotency and retries
        - `src/payflow/gateway.py` – in-memory payment gateway
        - `src/payflow/refunds.py` – refunds against existing charges
        - `src/payflow/orders.py` – order totals
        - `src/payflow/auth.py` – dashboard API tokens
        - `scripts/deploy.py` – deployment step used by CI
        - `docs/` – runbook and architecture notes

        ## Development

        ```bash
        pip install -r requirements-dev.txt
        pytest
        ```
        """),
    "docs/architecture.md": d("""
        # Architecture

        Requests arrive at `PaymentService.process_payment(amount, idempotency_key)`.
        The service keeps a map of processed idempotency keys to charge IDs so a retried
        HTTP request never charges a customer twice. New keys are charged through the
        gateway; transient `GatewayError`s are retried up to `MAX_ATTEMPTS` times.

        Refunds (`refunds.py`) look up the original charge and refund against it.
        Order totals (`orders.py`) are computed in paise to avoid floating-point errors.
        Dashboard API tokens (`auth.py`) are HMAC-signed and expire after `TTL_SECONDS`.

        CI (`.github/workflows/ci.yml`) runs the test suite on every push and pull request,
        then deploys `main` to staging with `scripts/deploy.py`.
        """),
    "docs/runbook.md": d("""
        # Payments runbook

        ## Before deploying payment changes

        1. Run the full test suite, especially `tests/test_service.py`.
        2. Verify idempotency: the same idempotency key must never create two charges.
        3. Check retry behaviour against a gateway that times out.

        ## Deployment

        CI deploys every green commit on `main` to staging. The target container registry
        is configured in `deploy/config.json`. A registry DNS or network failure fails the
        deploy step even though the code is fine; re-run the job once the registry is reachable.

        ## Incidents

        - Duplicate charges: check the idempotency lookup in `PaymentService.process_payment`.
        - Refund errors: check remaining-balance calculation in `refunds.py`.
        """),
    ".gitignore": "__pycache__/\n.pytest_cache/\n*.pyc\n.venv/\n",
    "pyproject.toml": d("""
        [project]
        name = "payflow"
        version = "0.1.0"
        requires-python = ">=3.10"

        [tool.pytest.ini_options]
        pythonpath = ["src"]
        testpaths = ["tests"]
        """),
    "requirements-dev.txt": "pytest>=8.0\npytest-github-actions-annotate-failures>=0.2\n",
    ".github/workflows/ci.yml": d("""
        name: CI/CD

        on:
          push:
            branches: [main]
          pull_request:

        jobs:
          test:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - uses: actions/setup-python@v5
                with:
                  python-version: "3.12"
              - name: Install dependencies
                run: pip install -r requirements-dev.txt
              - name: Run tests
                run: pytest -q

          deploy:
            if: github.event_name == 'push'
            needs: test
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - uses: actions/setup-python@v5
                with:
                  python-version: "3.12"
              - name: Deploy to staging
                run: python scripts/deploy.py
        """),
    "deploy/config.json": '{\n  "environment": "staging",\n  "registry": null\n}\n',
    "scripts/deploy.py": d('''
        """Deployment step for the PayFlow CI pipeline (simulated push to a container registry)."""

        import json
        import os
        import sys
        import urllib.error
        import urllib.parse
        import urllib.request
        from pathlib import Path

        config = json.loads(Path("deploy/config.json").read_text())
        sha = os.getenv("GITHUB_SHA", "local")[:7]
        registry = config.get("registry")

        if registry:
            host = urllib.parse.urlparse(registry).hostname
            print(f"Pushing image payflow:{sha} to {registry}")
            try:
                urllib.request.urlopen(registry, timeout=10)
            except (urllib.error.URLError, OSError) as exc:
                print(f"::error title=Deploy failed::Could not resolve host {host} while pushing image payflow:{sha} ({exc})")
                sys.exit(1)

        print(f"Deployed payflow:{sha} to {config['environment']}")
        '''),
    "src/payflow/__init__.py": '"""PayFlow: a small payments service."""\n',
    "src/payflow/gateway.py": d('''
        """In-memory payment gateway used by the service and tests."""


        class GatewayError(Exception):
            """A transient gateway failure that is safe to retry."""


        class FakeGateway:
            def __init__(self, fail_times: int = 0):
                self.charges: list[dict] = []
                self.refunds: list[dict] = []
                self._fail_times = fail_times

            def charge(self, amount: int, reference: str) -> str:
                if self._fail_times > 0:
                    self._fail_times -= 1
                    raise GatewayError("gateway timeout")
                charge_id = f"ch_{len(self.charges) + 1}"
                self.charges.append({"id": charge_id, "amount": amount, "reference": reference})
                return charge_id

            def refund(self, charge_id: str, amount: int) -> str:
                refund_id = f"re_{len(self.refunds) + 1}"
                self.refunds.append({"id": refund_id, "charge_id": charge_id, "amount": amount})
                return refund_id

            def get_charge(self, charge_id: str) -> dict:
                return next(charge for charge in self.charges if charge["id"] == charge_id)
        '''),
    "src/payflow/service.py": d('''
        """Charges customers exactly once per idempotency key."""

        from .gateway import FakeGateway


        class PaymentService:
            def __init__(self, gateway: FakeGateway):
                self.gateway = gateway
                self._processed: dict[str, str] = {}

            def process_payment(self, amount: int, idempotency_key: str) -> str:
                if amount <= 0:
                    raise ValueError("amount must be positive")
                if idempotency_key in self._processed:
                    return self._processed[idempotency_key]
                charge_id = self.gateway.charge(amount, idempotency_key)
                self._processed[idempotency_key] = charge_id
                return charge_id
        '''),
    "src/payflow/orders.py": d('''
        """Order totals, in paise."""


        def order_total(items: list[dict]) -> int:
            return sum(item["price"] * item["quantity"] for item in items)
        '''),
    "src/payflow/auth.py": d('''
        """Short-lived, HMAC-signed API tokens for the operations dashboard."""

        import hashlib
        import hmac
        import time

        SIGNING_KEY = b"payflow-demo-signing-key"
        TTL_SECONDS = 900


        def _sign(user: str, issued: int) -> str:
            return hmac.new(SIGNING_KEY, f"{user}:{issued}".encode(), hashlib.sha256).hexdigest()[:16]


        def issue_token(user: str, now: float | None = None) -> str:
            issued = int(time.time() if now is None else now)
            return f"{user}:{issued}:{_sign(user, issued)}"


        def validate_token(token: str, now: float | None = None) -> bool:
            try:
                user, issued, signature = token.split(":")
            except ValueError:
                return False
            if not hmac.compare_digest(signature, _sign(user, int(issued))):
                return False
            current = time.time() if now is None else now
            # Grace period for clock skew between dashboard and API servers.
            return current - int(issued) < TTL_SECONDS + 60
        '''),
    "tests/test_service.py": d('''
        import pytest

        from payflow.gateway import FakeGateway
        from payflow.service import PaymentService


        def test_charges_customer_once():
            gateway = FakeGateway()
            service = PaymentService(gateway)
            assert service.process_payment(50_000, "order-1") == "ch_1"
            assert len(gateway.charges) == 1


        def test_duplicate_request_is_idempotent():
            gateway = FakeGateway()
            service = PaymentService(gateway)
            first = service.process_payment(50_000, "order-1")
            second = service.process_payment(50_000, "order-1")
            assert first == second
            assert len(gateway.charges) == 1


        def test_rejects_non_positive_amount():
            with pytest.raises(ValueError):
                PaymentService(FakeGateway()).process_payment(0, "order-2")
        '''),
    "tests/test_orders.py": d('''
        from payflow.orders import order_total


        def test_order_total_sums_items():
            items = [{"price": 25_000, "quantity": 2}, {"price": 9_900, "quantity": 1}]
            assert order_total(items) == 59_900
        '''),
    "tests/test_auth.py": d('''
        from payflow.auth import TTL_SECONDS, issue_token, validate_token


        def test_fresh_token_is_valid():
            token = issue_token("ops", now=1_000)
            assert validate_token(token, now=1_010)


        def test_tampered_token_is_rejected():
            user, issued, signature = issue_token("ops", now=1_000).split(":")
            assert not validate_token(f"admin:{issued}:{signature}", now=1_010)


        def test_token_is_invalid_long_after_expiry():
            token = issue_token("ops", now=1_000)
            assert not validate_token(token, now=1_000 + TTL_SECONDS + 3_600)
        '''),
}

SERVICE_RETRY = d('''
    """Charges customers exactly once per idempotency key."""

    from .gateway import FakeGateway, GatewayError

    MAX_ATTEMPTS = 3


    class PaymentService:
        def __init__(self, gateway: FakeGateway):
            self.gateway = gateway
            self._processed: dict[str, str] = {}

        def process_payment(self, amount: int, idempotency_key: str) -> str:
            if amount <= 0:
                raise ValueError("amount must be positive")
            if idempotency_key in self._processed:
                return self._processed[idempotency_key]
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    charge_id = self.gateway.charge(amount, idempotency_key)
                    break
                except GatewayError:
                    if attempt == MAX_ATTEMPTS:
                        raise
            self._processed[idempotency_key] = charge_id
            return charge_id
    ''')

SERVICE_REFACTORED = d('''
    """Charges customers exactly once per idempotency key."""

    from .gateway import FakeGateway, GatewayError

    MAX_ATTEMPTS = 3


    class PaymentService:
        def __init__(self, gateway: FakeGateway):
            self.gateway = gateway
            self._processed: dict[str, str] = {}

        def process_payment(self, amount: int, idempotency_key: str) -> str:
            if amount <= 0:
                raise ValueError("amount must be positive")
            previous = self._processed[{KEY_LOOKUP}]
            if previous:
                return previous
            charge_id = self._charge_with_retry(amount, idempotency_key)
            self._processed[idempotency_key] = charge_id
            return charge_id

        def _charge_with_retry(self, amount: int, reference: str) -> str:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    return self.gateway.charge(amount, reference)
                except GatewayError:
                    if attempt == MAX_ATTEMPTS:
                        raise
            raise AssertionError("unreachable")
    ''')

TESTS_SERVICE_RETRY = BASE["tests/test_service.py"] + d('''


    def test_retries_transient_gateway_errors():
        gateway = FakeGateway(fail_times=2)
        assert PaymentService(gateway).process_payment(10_000, "order-3") == "ch_1"


    def test_gives_up_after_max_attempts():
        from payflow.gateway import GatewayError

        with pytest.raises(GatewayError):
            PaymentService(FakeGateway(fail_times=5)).process_payment(10_000, "order-4")
    ''')

REFUNDS_FULL = d('''
    """Refunds against existing charges."""

    from .gateway import FakeGateway


    def refund_payment(gateway: FakeGateway, charge_id: str) -> str:
        charge = gateway.get_charge(charge_id)
        return gateway.refund(charge_id, charge["amount"])
    ''')

TESTS_REFUNDS = d('''
    from payflow.gateway import FakeGateway
    from payflow.refunds import refund_payment
    from payflow.service import PaymentService


    def test_full_refund_returns_whole_amount():
        gateway = FakeGateway()
        charge_id = PaymentService(gateway).process_payment(30_000, "order-9")
        refund_payment(gateway, charge_id)
        assert gateway.refunds[0]["amount"] == 30_000
    ''')

REFUNDS_PARTIAL_BUGGY = d('''
    """Refunds against existing charges, including partial refunds."""

    from .gateway import FakeGateway


    def refund_payment(gateway: FakeGateway, charge_id: str, amount: int | None = None) -> str:
        charge = gateway.get_charge(charge_id)
        refunded = sum(item["amount"] for item in gateway.refunds if item["charge_id"] == charge_id)
        amount = charge["amount"] - refunded if amount is None else amount
        remaining = charge["amount"] - refunded
        if amount >= remaining:
            raise ValueError(f"refund of {amount} exceeds remaining balance {remaining}")
        return gateway.refund(charge_id, amount)
    ''')

TESTS_REFUNDS_PARTIAL = TESTS_REFUNDS + d('''


    def test_partial_refunds_until_balance_is_used():
        gateway = FakeGateway()
        charge_id = PaymentService(gateway).process_payment(30_000, "order-10")
        refund_payment(gateway, charge_id, 10_000)
        refund_payment(gateway, charge_id)
        assert [item["amount"] for item in gateway.refunds] == [10_000, 20_000]
    ''')

WEBHOOKS = d('''
    """Verify signatures on payment-gateway callbacks."""

    import hashlib
    import hmac


    def verify_callback(body: bytes, signature: str, signing_key: bytes) -> bool:
        expected = "sha256=" + hmac.new(signing_key, body, hashlib.sha256).hexdigest()
        return len(expected) == len(signature) and hmac.compare_digest(expected, signature)
    ''')

TESTS_WEBHOOKS = d('''
    import hashlib
    import hmac

    from payflow.webhooks import verify_callback

    KEY = b"callback-key"
    BODY = b'{"event": "charge.succeeded"}'


    def test_valid_signature_is_accepted():
        signature = "sha256=" + hmac.new(KEY, BODY, hashlib.sha256).hexdigest()
        assert verify_callback(BODY, signature, KEY)


    def test_forged_short_signature_is_rejected():
        assert not verify_callback(BODY, "sha256=abc", KEY)
    ''')

ORDERS_DISCOUNT = BASE["src/payflow/orders.py"] + d('''


    DISCOUNT_CODES = {"WELCOME10": 10, "FESTIVE20": 20}


    def apply_discount(total: int, code: str | None) -> int:
        percent = DISCOUNT_CODES.get((code or "").upper(), 0)
        return total - total * percent // 100
    ''')

TESTS_ORDERS_DISCOUNT = BASE["tests/test_orders.py"] + d('''


    def test_discount_code_is_applied():
        from payflow.orders import apply_discount

        assert apply_discount(10_000, "welcome10") == 9_000
        assert apply_discount(10_000, "unknown") == 10_000
    ''')

ORDERS_CURRENCY = ORDERS_DISCOUNT + d('''


    def format_amount(paise: int, currency: str = "INR") -> str:
        symbol = {"INR": "₹", "USD": "$"}.get(currency, currency + " ")
        return f"{symbol}{paise // 100:,}.{paise % 100:02d}"
    ''')

TESTS_ORDERS_CURRENCY = TESTS_ORDERS_DISCOUNT + d('''


    def test_amounts_are_formatted_with_currency():
        from payflow.orders import format_amount

        assert format_amount(123_456) == "₹1,234.56"
        assert format_amount(500, "USD") == "$5.00"
    ''')

AUTH_FIXED = BASE["src/payflow/auth.py"].replace(
    "    # Grace period for clock skew between dashboard and API servers.\n"
    "    return current - int(issued) < TTL_SECONDS + 60\n",
    "    return current - int(issued) < TTL_SECONDS\n")

TESTS_AUTH_FIXED = BASE["tests/test_auth.py"] + d('''


    def test_token_is_rejected_just_after_expiry():
        token = issue_token("ops", now=1_000)
        assert not validate_token(token, now=1_000 + TTL_SECONDS + 30)
    ''')

SANDBOX_TEST = d('''
    """Smoke test against the payment gateway's shared sandbox.

    The sandbox is shared with other teams and has occasional outages. For the AEIP demo,
    CI run #__RUN__ simulates one of those outages; every other run passes. The commit
    that triggers that run changes documentation only, so the failure is not caused by it.
    """

    import os


    class SandboxUnavailable(ConnectionError):
        pass


    def ping_sandbox() -> str:
        if os.getenv("GITHUB_RUN_NUMBER") == "__RUN__":
            raise SandboxUnavailable("connect to sandbox.gateway.payflow.example:443 timed out after 30s (ETIMEDOUT)")
        return "pong"


    def test_gateway_sandbox_is_reachable():
        assert ping_sandbox() == "pong"
    ''')

RUNBOOK_V2 = BASE["docs/runbook.md"] + d("""

    ## Refund policy

    Partial refunds are allowed until the charge's remaining balance reaches zero.
    Always refund against the original charge ID, never create a new charge.
    """)

RUNBOOK_V3 = RUNBOOK_V2 + d("""

    ## On-call

    Payments on-call rotates weekly. Gateway sandbox outages are posted in #payments-sandbox;
    re-run CI once the sandbox is back instead of changing code.
    """)

README_V2 = BASE["README.md"].replace(
    "## Development",
    "Operational procedures live in [docs/runbook.md](docs/runbook.md).\n\n## Development")

# --------------------------------------------------------------------------- history
# Each step: message, files to write, expected (tests_pass, deploy_pass or None when not deployed).
MAIN = [
    ("feat: initial PayFlow payments service", BASE, (True, True)),
    ("feat: add full refunds", {"src/payflow/refunds.py": REFUNDS_FULL, "tests/test_refunds.py": TESTS_REFUNDS}, (True, True)),
    ("feat: retry transient gateway errors", {"src/payflow/service.py": SERVICE_RETRY, "tests/test_service.py": TESTS_SERVICE_RETRY}, (True, True)),
    ("refactor: extract retry loop from payment flow",
     {"src/payflow/service.py": SERVICE_REFACTORED.replace("{KEY_LOOKUP}", "idempotency_key")}, (False, None)),
    ("fix: use .get for idempotency lookup on new keys",
     {"src/payflow/service.py": SERVICE_REFACTORED.replace("self._processed[{KEY_LOOKUP}]", "self._processed.get(idempotency_key)")},
     (True, True)),
    ("chore: deploy to the new container registry",
     {"deploy/config.json": '{\n  "environment": "staging",\n  "registry": "https://registry.payflow-internal.invalid/v2/"\n}\n'},
     (True, False)),
    ("chore: revert registry until DNS propagates", {"deploy/config.json": BASE["deploy/config.json"]}, (True, True)),
    ("feat: verify gateway callback signatures", {"src/payflow/webhooks.py": WEBHOOKS, "tests/test_webhooks.py": TESTS_WEBHOOKS}, (True, True)),
    ("feat: discount codes on order totals", {"src/payflow/orders.py": ORDERS_DISCOUNT, "tests/test_orders.py": TESTS_ORDERS_DISCOUNT}, (True, True)),
    ("docs: add refund policy to the runbook", {"docs/runbook.md": RUNBOOK_V2}, (True, True)),
    ("test: add gateway sandbox smoke test", {"tests/test_gateway_sandbox.py": SANDBOX_TEST.replace("__RUN__", "12")}, (True, True)),
    ("docs: add on-call notes to the runbook", {"docs/runbook.md": RUNBOOK_V3}, (False, None)),  # sandbox outage (run 12)
    ("docs: link the runbook from the README", {"README.md": README_V2}, (True, True)),
]

BRANCHES = [
    {"branch": "feature/partial-refunds", "title": "Support partial refunds",
     "body": "Allows refunding part of a charge, with the remaining balance tracked per charge.",
     "message": "feat: support partial refunds",
     "files": {"src/payflow/refunds.py": REFUNDS_PARTIAL_BUGGY, "tests/test_refunds.py": TESTS_REFUNDS_PARTIAL},
     "tests_pass": False, "merge": False},
    {"branch": "fix/token-expiry", "title": "Reject dashboard tokens right after expiry",
     "body": "Removes the 60-second grace period that let expired tokens through.",
     "message": "fix: reject tokens immediately after expiry",
     "files": {"src/payflow/auth.py": AUTH_FIXED, "tests/test_auth.py": TESTS_AUTH_FIXED},
     "tests_pass": True, "merge": True},
    {"branch": "feature/currency-format", "title": "Format amounts with currency symbols",
     "body": "Adds `format_amount` for receipts and the dashboard.",
     "message": "feat: format amounts with currency symbols",
     "files": {"src/payflow/orders.py": ORDERS_CURRENCY, "tests/test_orders.py": TESTS_ORDERS_CURRENCY},
     "tests_pass": True, "merge": False},
]


# --------------------------------------------------------------------------- helpers
def git(folder: Path, *args: str, env: dict | None = None, capture: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=folder, text=True, capture_output=capture,
                            env={**os.environ, **(env or {})})
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{result.stderr}")
    return (result.stdout or "").strip()


def write(folder: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


def run_tests(folder: Path, run_number: str = "0") -> bool:
    # GITHUB_RUN_NUMBER mirrors CI: on a fresh repo, the n-th push to main is CI run n.
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=folder,
                            capture_output=True, text=True, env={**os.environ, "GITHUB_RUN_NUMBER": run_number})
    shutil.rmtree(folder / "src" / "payflow" / "__pycache__", ignore_errors=True)
    shutil.rmtree(folder / "tests" / "__pycache__", ignore_errors=True)
    return result.returncode == 0


def run_deploy(folder: Path) -> bool:
    return subprocess.run([sys.executable, "scripts/deploy.py"], cwd=folder, capture_output=True).returncode == 0


def check(label: str, actual: bool, expected: bool, what: str) -> None:
    status = "pass" if actual else "FAIL"
    marker = "ok " if actual == expected else "!! "
    print(f"   {marker}{what}: {status} (planned {'pass' if expected else 'FAIL'})")
    if actual != expected:
        raise SystemExit(f"'{label}': {what} did not behave as planned; aborting.")


# --------------------------------------------------------------------------- build
def build(folder: Path) -> None:
    if folder.exists() and any(folder.iterdir()):
        raise SystemExit(f"{folder} is not empty; choose a new folder.")
    folder.mkdir(parents=True, exist_ok=True)
    git(folder, "init", "-q", "-b", "main")
    for index, (message, files, (tests_ok, deploy_ok)) in enumerate(MAIN, start=1):
        write(folder, files)
        print(f"c{index:<2} {message}")
        check(message, run_tests(folder, str(index)), tests_ok, "tests")
        if deploy_ok is not None:
            check(message, run_deploy(folder), deploy_ok, "deploy")
        git(folder, "add", "-A")
        git(folder, "commit", "-q", "-m", message)
    tip = git(folder, "rev-parse", "HEAD")
    for spec in BRANCHES:
        git(folder, "checkout", "-q", "-b", spec["branch"], tip)
        write(folder, spec["files"])
        print(f"{spec['branch']}: {spec['message']}")
        check(spec["message"], run_tests(folder), spec["tests_pass"], "tests")
        git(folder, "add", "-A")
        git(folder, "commit", "-q", "-m", spec["message"])
        git(folder, "checkout", "-q", "main")
    print(f"\nBuilt {len(MAIN)} commits on main and {len(BRANCHES)} branches in {folder}")


# --------------------------------------------------------------------------- publish
def api(method: str, path: str, token: str, body: dict | None = None):
    request = urllib.request.Request(
        f"https://api.github.com{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "aeip-demo", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GitHub {method} {path} failed: HTTP {exc.code} {exc.read().decode()[:300]}")


def repo_state(owner: str, name: str, token: str) -> str:
    """'missing', 'empty' (created on github.com without a README) or 'has-commits'."""
    request = urllib.request.Request(f"https://api.github.com/repos/{owner}/{name}/commits?per_page=1",
                                     headers={"Authorization": f"Bearer {token}", "User-Agent": "aeip-demo"})
    try:
        with urllib.request.urlopen(request, timeout=60):
            return "has-commits"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "missing"
        if exc.code == 409:  # "Git Repository is empty"
            return "empty"
        raise SystemExit(f"Could not inspect {owner}/{name}: HTTP {exc.code}")


def publish(folder: Path, name: str) -> None:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN (repo + workflow permissions) before publishing.")
    owner = api("GET", "/user", token)["login"]
    if repo_state(owner, name, token) == "missing":
        api("POST", "/user/repos", token, {"name": name, "private": False, "auto_init": False,
                                           "description": "PayFlow – demo repository for AEIP (AI Engineering Intelligence Platform)"})
        print(f"Created https://github.com/{owner}/{name}")
    elif repo_state(owner, name, token) == "empty":
        print(f"Using existing empty repository https://github.com/{owner}/{name}")
    else:
        raise SystemExit(f"{owner}/{name} already has commits; use a new or empty repository so the history starts clean.")

    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    push_env = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}"}  # token never written to .git/config
    remote = f"https://github.com/{owner}/{name}.git"
    commits = git(folder, "rev-list", "--reverse", "main").split()
    for index, sha in enumerate(commits, start=1):
        # One push per commit so GitHub Actions runs CI for each step of the story.
        git(folder, "push", "-q", remote, f"{sha}:refs/heads/main", env=push_env)
        print(f"pushed c{index} {git(folder, 'log', '-1', '--format=%s', sha)}")
        time.sleep(8)
    for spec in BRANCHES:
        git(folder, "push", "-q", remote, f"{spec['branch']}:refs/heads/{spec['branch']}", env=push_env)
        pr = api("POST", f"/repos/{owner}/{name}/pulls", token,
                 {"title": spec["title"], "head": spec["branch"], "base": "main", "body": spec["body"]})
        print(f"opened PR #{pr['number']} {spec['title']}")
        if spec["merge"]:
            time.sleep(20)  # let the PR's CI run start before merging
            api("PUT", f"/repos/{owner}/{name}/pulls/{pr['number']}/merge", token,
                {"merge_method": "merge", "commit_title": f"Merge pull request #{pr['number']}: {spec['title']}"})
            print(f"merged PR #{pr['number']}")
    print(f"\nDone. Wait ~5 minutes for GitHub Actions to finish, then analyse {owner}/{name} in AEIP.")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "build":
        build(Path(sys.argv[2]).resolve())
    elif len(sys.argv) >= 4 and sys.argv[1] == "publish":
        publish(Path(sys.argv[2]).resolve(), sys.argv[3])
    else:
        raise SystemExit(__doc__)
