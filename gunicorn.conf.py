# gunicorn.conf.py

# Number of worker processes
workers = 4

# Use gevent worker class for WebSocket support
worker_class = 'geventwebsocket.gunicorn.workers.GeventWebSocketWorker'

# Bind to all available network interfaces on port 8000
bind = '0.0.0.0:5001'

# Timeout for worker processes (in seconds)
timeout = 120

# Maximum number of simultaneous clients
worker_connections = 1000

# Maximum number of requests a worker will process before restarting
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'