# Apache serves the static UI and executes the small PHP proxy.
FROM php:8.3-apache

# Keep the frontend image independent from the Python agent image.
COPY index.php api.php utils.js /var/www/html/
COPY style.css /var/www/html/

EXPOSE 80
