
import pytest
import sys
from pathlib import Path

# Ensure scripts module is available
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

try:
    from scripts import error_fingerprinter
except ImportError:
    # If scripts not importable as module, try adding to path directly and import
    sys.path.append(str(PROJECT_ROOT / "scripts"))
    import error_fingerprinter

def pytest_exception_interact(node, call, report):
    """
    Hook to capture exceptions and suggest fixes from the Knowledge Base.
    """
    if report.failed:
        # Get exception info
        excinfo = call.excinfo
        if not excinfo:
            return

        # Format error text similarly to how we might see it in logs
        # We include the exception type and message
        error_text = f"{excinfo.typename}: {excinfo.value}"
        # Optionally include some traceback if needed by fingerprinter? 
        # The fingerprinter strips line numbers anyway, so the message is most important.
        # But let's give it the last few lines of traceback to be safe if that's what it expects.
        # However, looking at fingerprinter.py usage, it expects "error_text".
        
        # Check against Knowledge Base
        match = error_fingerprinter.lookup(error_text)
        
        print("\n\n" + "="*80)
        print(" [LEARNING DEBUGGER] DIAGNOSTIC REPORT")
        print("="*80)
        
        if match:
            # Check if there is a real solution
            solution = match.get("solution", "")
            if solution and solution not in ["NEEDS_DIAGNOSIS", "Pending Diagnosis", ""]:
                print(f" MATCHED KNOWN ERROR: {match.get('fingerprint')}")
                print(f" SUGGESTED FIX: {solution}")
                if match.get("root_cause"):
                    print(f" ROOT CAUSE: {match.get('root_cause')}")
            else:
                 print(f" KNOWN ISSUE (Fingerprint: {match.get('fingerprint')})")
                 print(" Status: Pending Diagnosis")
        else:
            # New error - capture it for diagnosis
            print(" NEW ERROR DETECTED - Capturing for analysis...")
            try:
                # Capture with "NEEDS_DIAGNOSIS" so it shows up in pending reports
                error_fingerprinter.capture(error_text, "NEEDS_DIAGNOSIS")
                print(f" ✓ Error captured to Knowledge Base (queued for diagnosis)")
            except Exception as e:
                print(f" ⚠ Failed to capture error: {e}")
                
        print("="*80 + "\n")
