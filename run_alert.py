"""Entry point:  python run_alert.py [--dry-run | --test-telegram]"""
import sys

from gold_alerts.runner import main

sys.exit(main())
