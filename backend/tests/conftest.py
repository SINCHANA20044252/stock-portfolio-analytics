import os
import tempfile

# Must be set before the app is imported.
_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["RUN_MIGRATIONS"] = "false"       # tests build tables with create_all; migrations have their own check
os.environ["PBKDF2_ITERATIONS"] = "2000"      # fast hashing in tests only
os.environ["MARKET_DATA_PROVIDER"] = "demo"
os.environ["ENV"] = "development"
os.environ.pop("GEMINI_API_KEY", None)

import sys  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
