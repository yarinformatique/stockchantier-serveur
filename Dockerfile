FROM python:3.11-slim

WORKDIR /app

# Copie des fichiers du serveur
COPY saas_server.py /app/
COPY superadmin_portal.html /app/
COPY requirements.txt /app/

# Port par défaut (dynamique en production)
ENV PORT=9000
EXPOSE 9000

CMD ["python", "saas_server.py"]
