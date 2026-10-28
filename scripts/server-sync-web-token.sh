#!/bin/sh
# Trusted operator command only. Directory bind observes atomic token replacement.
set -eu
test "$(id -u)" = 0
test -f /etc/debugych/owner-bootstrap.token
install -d -m 755 /etc/debugych/web-auth
install -o 1000 -g 1000 -m 400 /etc/debugych/owner-bootstrap.token /etc/debugych/web-auth/token.new
mv -f /etc/debugych/web-auth/token.new /etc/debugych/web-auth/token
echo 'Web gateway credential refreshed. No key printed.'
