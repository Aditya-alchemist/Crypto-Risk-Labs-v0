#!/usr/bin/env python
"""Simple backend startup script with proper working directory setup."""
import os
import sys

if __name__ == "__main__":
    # Set working directory BEFORE any imports
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print(f"Working directory: {os.getcwd()}")
    print(f"data directory exists: {os.path.exists('data')}")
    print(f"data/crl.db exists: {os.path.exists('data/crl.db')}")
    
    # AFTER setting working directory, import main
    try:
        from main import app
        import uvicorn
        
        print("[OK] Successfully imported main.app")
        PORT = 8000
        print(f"Starting Uvicorn server on http://0.0.0.0:{PORT}")
        sys.stdout.flush()
        sys.stderr.flush()
        
        try:
            uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False, log_level="info")
        except KeyboardInterrupt:
            print("Shutting down...")
        except Exception as startup_err:
            print(f"[ERROR] Error during uvicorn.run(): {startup_err}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"✗ Error importing main.app: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
