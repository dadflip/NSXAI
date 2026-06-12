from __future__ import annotations

import os
import sys
from pathlib import Path
import logging

_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Import the native engines and bundles from the pipeline source of truth
from nsxai.ml.pipeline import make_fastapi_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI Application Entry Point
# ---------------------------------------------------------------------------

output_dir = os.path.join(
    _root, 'nsxai', 'ml', 'outputs', 'task2_multimodel', 'task4'
)
full_bundle_path  = os.path.join(output_dir, 'nsxai_full_bundle.pkl')
task4_bundle_path = os.path.join(output_dir, 'task4_model_bundle.pkl')

bundle_path = os.getenv("ARTIFACTS_FILE",
                        full_bundle_path if os.path.exists(full_bundle_path)
                        else task4_bundle_path)

if not os.path.exists(bundle_path):
    logger.warning(f"MLOps bundle not found at {bundle_path}")

# Construct the FastAPI app using the pipeline's factory
app = make_fastapi_app(bundle_path)

if __name__ == "__main__":
    try:
        import uvicorn
        if app is not None:
            logger.info("Starting MLOps API Server...")
            uvicorn.run(app, host="0.0.0.0", port=8000)
        else:
            logger.error("Failed to initialize FastAPI application. Missing dependencies?")
    except ImportError:
        logger.error("Please install uvicorn to run the API server: pip install uvicorn")
