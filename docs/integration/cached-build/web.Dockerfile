FROM debugych-redesign2-web:local
COPY html /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
