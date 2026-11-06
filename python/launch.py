"""Entry point for standalone desktop bundles."""
import sys

if __name__ == '__main__':
    if '--bundle-smoke-test' in sys.argv:
        from cytose.bundle_smoke import run
        raise SystemExit(run())
    from cytose.app import main
    raise SystemExit(main())
