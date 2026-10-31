#!/bin/sh
set -eu
case "${RENEWED_LINEAGE:-}" in
 /etc/letsencrypt/live/debugych-server-20261028|/etc/letsencrypt/live/debugych-sslip-20261030|/etc/letsencrypt/live/debugych-ip-20261031)
    /usr/sbin/nginx -t
    /usr/bin/systemctl reload nginx
 ;;
esac
