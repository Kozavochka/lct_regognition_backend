# nginx/Dockerfile
FROM nginx:1.27-alpine

COPY default.conf /etc/nginx/conf.d/default.conf

# Директории для монтирования статических/медиа
RUN mkdir -p /var/www/static /var/www/media && \
    chown -R nginx:nginx /var/www
