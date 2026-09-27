# Production Architecture

Public ingress/load balancer -> frontend and API. Private PostgreSQL/Redis/object store/Keycloak as appropriate. Worker and scheduler private. Separate security groups/network policies. No direct public ports for databases.
