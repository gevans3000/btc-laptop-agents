import traceback
from tests.test_autonomy_resilience import test_paper_broker_fifo

try:
    test_paper_broker_fifo()
    print("Test PASSED")
except Exception:
    traceback.print_exc()
