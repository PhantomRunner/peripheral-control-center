"""Non-root, loopback-only entry point for the combined production image."""

import os

import uvicorn


def main() -> None:
    if os.geteuid() == 0:
        raise SystemExit('Run PCC as a non-root user (PCC_UID/PCC_GID).')
    try:
        port = int(os.environ.get('PCC_PORT', '8080'))
        if not 1024 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit('PCC_PORT must be an integer from 1024 to 65535.') from None
    os.umask(0o077)
    uvicorn.run('pcc.main:app', host='127.0.0.1', port=port, workers=1,
                proxy_headers=False, access_log=False)


if __name__ == '__main__':
    main()
