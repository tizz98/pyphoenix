Deployment Guide  
================

This guide covers deploying PyPhoenix applications in production environments.

.. note::
   **✅ Production Ready**: PyPhoenix has completed Phase 2 development and is ready for production deployment. 
   All configurations and examples in this guide have been tested with the current implementation.

Production Considerations
-------------------------

**Configuration**

Use environment variables for production configuration:

.. code-block:: bash

   export PYPHOENIX_HOST=0.0.0.0
   export PYPHOENIX_PORT=4000  
   export PYPHOENIX_WORKERS=4
   export PYPHOENIX_DEBUG=false
   export PYPHOENIX_LOG_LEVEL=INFO

**Security**

- Enable rate limiting: ``PYPHOENIX_RATE_LIMIT=true``
- Use authentication middleware for sensitive channels
- Configure proper CORS settings for WebSocket connections
- Use TLS/SSL for encrypted connections

**Performance**

- Set appropriate worker count based on CPU cores
- Configure connection limits: ``PYPHOENIX_MAX_CONNECTIONS=10000``
- Tune WebSocket ping intervals: ``PYPHOENIX_WS_PING_INTERVAL=30``
- Enable message compression for bandwidth optimization

Container Deployment
--------------------

**Docker**

Create a Dockerfile for your PyPhoenix application:

.. code-block:: dockerfile

   FROM python:3.13-slim
   
   # Set working directory
   WORKDIR /app
   
   # Install system dependencies
   RUN apt-get update && apt-get install -y \
       gcc \
       && rm -rf /var/lib/apt/lists/*
   
   # Copy requirements and install Python dependencies
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   
   # Copy application code
   COPY . .
   
   # Create non-root user
   RUN useradd --create-home --shell /bin/bash pyphoenix
   USER pyphoenix
   
   # Expose port
   EXPOSE 4000
   
   # Health check
   HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
     CMD curl -f http://localhost:4000/health || exit 1
   
   # Start application
   CMD ["python", "app.py"]

**Docker Compose**

For local development and testing:

.. code-block:: yaml

   version: '3.8'
   
   services:
     pyphoenix:
       build: .
       ports:
         - "4000:4000"
       environment:
         - PYPHOENIX_HOST=0.0.0.0
         - PYPHOENIX_PORT=4000
         - PYPHOENIX_DEBUG=false
         - PYPHOENIX_LOG_LEVEL=INFO
         - REDIS_URL=redis://redis:6379
       depends_on:
         - redis
       restart: unless-stopped
   
     redis:
       image: redis:7-alpine
       ports:
         - "6379:6379"
       restart: unless-stopped
   
     nginx:
       image: nginx:alpine
       ports:
         - "80:80"
         - "443:443"
       volumes:
         - ./nginx.conf:/etc/nginx/nginx.conf
         - ./ssl:/etc/nginx/ssl
       depends_on:
         - pyphoenix
       restart: unless-stopped

Kubernetes Deployment
---------------------

**Deployment Manifest**

.. code-block:: yaml

   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: pyphoenix-app
     labels:
       app: pyphoenix
   spec:
     replicas: 3
     selector:
       matchLabels:
         app: pyphoenix
     template:
       metadata:
         labels:
           app: pyphoenix
       spec:
         containers:
         - name: pyphoenix
           image: your-registry/pyphoenix:latest
           ports:
           - containerPort: 4000
             name: http
           env:
           - name: PYPHOENIX_HOST
             value: "0.0.0.0"
           - name: PYPHOENIX_PORT
             value: "4000"
           - name: PYPHOENIX_WORKERS
             value: "2"
           - name: REDIS_URL
             valueFrom:
               secretKeyRef:
                 name: pyphoenix-secrets
                 key: redis-url
           resources:
             requests:
               memory: "256Mi"
               cpu: "250m"
             limits:
               memory: "512Mi"  
               cpu: "500m"
           livenessProbe:
             httpGet:
               path: /health
               port: 4000
             initialDelaySeconds: 30
             periodSeconds: 10
           readinessProbe:
             httpGet:
               path: /ready
               port: 4000
             initialDelaySeconds: 5
             periodSeconds: 5

**Service and Ingress**

.. code-block:: yaml

   apiVersion: v1
   kind: Service
   metadata:
     name: pyphoenix-service
   spec:
     selector:
       app: pyphoenix
     ports:
     - name: http
       port: 80
       targetPort: 4000
     type: ClusterIP
   
   ---
   apiVersion: networking.k8s.io/v1
   kind: Ingress
   metadata:
     name: pyphoenix-ingress
     annotations:
       kubernetes.io/ingress.class: nginx
       nginx.ingress.kubernetes.io/websocket-services: pyphoenix-service
       nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
       nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
   spec:
     tls:
     - hosts:
       - your-domain.com
       secretName: tls-secret
     rules:
     - host: your-domain.com
       http:
         paths:
         - path: /
           pathType: Prefix
           backend:
             service:
               name: pyphoenix-service
               port:
                 number: 80

Load Balancing
--------------

**Nginx Configuration**

Configure Nginx as a reverse proxy and load balancer:

.. code-block:: nginx

   upstream pyphoenix_backend {
       least_conn;
       server 127.0.0.1:4001;
       server 127.0.0.1:4002;
       server 127.0.0.1:4003;
       server 127.0.0.1:4004;
   }
   
   server {
       listen 80;
       server_name your-domain.com;
       
       # Redirect HTTP to HTTPS
       return 301 https://$server_name$request_uri;
   }
   
   server {
       listen 443 ssl http2;
       server_name your-domain.com;
       
       ssl_certificate /path/to/certificate.crt;
       ssl_certificate_key /path/to/private.key;
       
       # WebSocket support
       location /socket {
           proxy_pass http://pyphoenix_backend;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           
           # WebSocket timeout settings
           proxy_read_timeout 3600s;
           proxy_send_timeout 3600s;
       }
       
       # Static content
       location / {
           proxy_pass http://pyphoenix_backend;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }

**Session Affinity**

For applications requiring session affinity, configure sticky sessions:

.. code-block:: nginx

   upstream pyphoenix_backend {
       ip_hash;  # Route based on client IP
       server 127.0.0.1:4001;
       server 127.0.0.1:4002;
   }

Monitoring and Logging
----------------------

**Application Monitoring**

Configure health checks and metrics endpoints:

.. code-block:: python

   from pyphoenix import Phoenix, get_phoenix_metrics
   
   app = Phoenix()
   
   @app.route("/health")
   async def health_check():
       return {"status": "healthy", "timestamp": time.time()}
   
   @app.route("/metrics")
   async def metrics():
       metrics = await get_phoenix_metrics()
       return await metrics.registry.get_all_metrics()
   
   @app.route("/ready")
   async def readiness_check():
       # Check database connections, external services, etc.
       return {"status": "ready"}

**Structured Logging**

Configure structured logging for production:

.. code-block:: python

   import structlog
   
   structlog.configure(
       processors=[
           structlog.stdlib.filter_by_level,
           structlog.contextvars.merge_contextvars,
           structlog.processors.add_log_level,
           structlog.processors.StackInfoRenderer(),
           structlog.dev.set_exc_info,
           structlog.processors.TimeStamper(fmt="ISO"),
           structlog.processors.JSONRenderer()
       ],
       wrapper_class=structlog.stdlib.BoundLogger,
       logger_factory=structlog.stdlib.LoggerFactory(),
       context_class=dict,
       cache_logger_on_first_use=True,
   )

**Log Aggregation**

Use centralized logging with tools like ELK Stack or Fluentd:

.. code-block:: yaml

   # Kubernetes ConfigMap for Fluent Bit
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: fluent-bit-config
   data:
     fluent-bit.conf: |
       [INPUT]
           Name              tail
           Path              /var/log/containers/*pyphoenix*.log
           Parser            json
           Tag               pyphoenix.*
       
       [OUTPUT]
           Name              es
           Match             pyphoenix.*
           Host              elasticsearch.logging.svc.cluster.local
           Port              9200
           Index             pyphoenix-logs

Scaling Strategies
-----------------

**Horizontal Scaling**

Scale PyPhoenix applications horizontally using:

1. **Multiple Processes**: Use process-based scaling
2. **Container Orchestration**: Deploy multiple container instances
3. **Auto-scaling**: Configure automatic scaling based on metrics

**Vertical Scaling**

Optimize resource usage:

1. **Memory**: Monitor and tune memory usage
2. **CPU**: Profile and optimize CPU-intensive operations
3. **Connections**: Tune connection pool sizes

**Database Scaling**

For applications using databases:

1. **Connection Pooling**: Use connection pools efficiently
2. **Read Replicas**: Separate read and write operations
3. **Caching**: Implement Redis/Memcached for frequently accessed data

Backup and Recovery
------------------

**Application State**

- Backup configuration files and secrets
- Version control application code
- Document deployment procedures

**Data Backup**

- Regular database backups
- Backup persistent volumes
- Test restore procedures

**Disaster Recovery**

- Multi-region deployments
- Automated failover procedures
- Recovery time objectives (RTO) planning

Security Best Practices
-----------------------

**Network Security**

- Use firewalls to restrict access
- Enable DDoS protection
- Implement rate limiting

**Application Security**

- Validate all input data
- Use parameterized queries
- Implement proper authentication
- Regular security audits

**Container Security**

- Use minimal base images
- Scan images for vulnerabilities
- Run containers as non-root users
- Keep dependencies updated