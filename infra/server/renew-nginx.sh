#!/bin/sh
set -eu
if [ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/debugych-server-20261028 ]; then
    /usr/sbin/nginx -t
    /usr/bin/systemctl reload nginx
fi
