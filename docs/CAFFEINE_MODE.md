# Caffeine Mode

## Overview

Caffeine mode is a feature designed to prevent servers (particularly those on hosting platforms like PythonAnywhere that have idle timeouts) from sleeping by periodically self-pinging. This ensures that the application remains responsive and available even when there are no external requests.

## How It Works

When enabled, caffeine mode runs as a background task that sends an HTTP GET request to the `/api/caffeine` endpoint every 10 minutes. This endpoint simply responds with a status message indicating that the server is awake and active.

## Configuration

### Enabling Caffeine Mode

Caffeine mode is disabled by default. To enable it, set the following environment variable:

```bash
CAFFEINE_MODE=true
```

Accepted values for enabling:
- `true`
- `1`
- `on`
- `yes`

Any other value (including `false`, `0`, `off`, or `no`) will disable caffeine mode.

### Customizing the Ping Target

By default, caffeine mode will ping:
- `http://localhost:8000/api/caffeine` when running locally
- `https://{domain}/api/caffeine` when running on an external domain

You can customize this behavior with the following environment variables:

#### CAFFEINE_DOMAIN

Specifies the domain or IP address to ping. This is useful if your application is running on a custom domain or specific IP.

```bash
CAFFEINE_DOMAIN=myapp.example.com
CAFFEINE_DOMAIN=192.168.1.100
CAFFEINE_DOMAIN=http://localhost
CAFFEINE_DOMAIN=https://staging.myapp.com
```

If you include the protocol (http:// or https://) in the domain, that protocol will be used. Otherwise, https:// will be assumed for external domains.

#### PORT

Specifies the port number to use when pinging localhost. This is primarily useful for local development or when running on non-standard ports.

```bash
PORT=8080
```

## API Endpoints

### /api/caffeine

**Endpoint:** `GET /api/caffeine`

**Description:** Simple endpoint that returns a status indicating the server is awake.

**Response:**
```json
{
  "status": "awake",
  "message": "Server is awake and active"
}
```

### /api/caffeine-status

**Endpoint:** `GET /api/caffeine-status`

**Description:** Returns the current status of caffeine mode (whether it's enabled or disabled).

**Response:**
```json
{
  "enabled": true,
  "message": "Caffeine mode is active"
}
```

## Logging

Caffeine mode activity is logged to `state/caffeine_mode.log`. The log file contains entries for:
- Startup and shutdown events
- Each ping attempt (success or failure)
- Error messages for failed pings

Example log entries:
```
2024-02-09 16:40:00,123 - INFO - Starting caffeine mode - pinging every 10 minutes
2024-02-09 16:50:00,456 - INFO - Starting caffeine ping
2024-02-09 16:50:00,457 - INFO - Pinging URL: https://myapp.example.com/api/caffeine
2024-02-09 16:50:00,567 - INFO - Caffeine ping successful: Server is awake and active (took 0.11 seconds)
```

## Implementation Details

Caffeine mode is implemented in `app/caffeine_mode.py` and includes:

- A background task that runs every 10 minutes
- Ping functionality with error handling
- Logging configuration
- Environment variable handling

The feature is integrated with the FastAPI application's startup and shutdown events.

## Use Cases

Caffeine mode is particularly useful for:
- Applications deployed on platforms with idle timeouts (like PythonAnywhere)
- Ensuring scheduled tasks (e.g., email dispatch) run reliably
- Maintaining application availability during periods of low traffic

## Testing

The caffeine mode functionality is tested in `tests/test_caffeine_mode.py`. Tests cover:
- Successful ping scenarios
- Custom port and domain configurations
- Ping failures
- Enabled/disabled state behavior

## Monitoring

You can check the current status of caffeine mode by:
1. Visiting the `/api/caffeine-status` endpoint
2. Checking the application logs in `state/caffeine_mode.log`
3. Observing the server's response time during idle periods

## Limitations

- Caffeine mode adds a small overhead with periodic HTTP requests
- It only prevents server sleep if the server is accessible from the internet
- It does not guarantee 100% uptime, but significantly reduces the risk of idle timeouts

## Troubleshooting

### Caffeine Mode Not Working

1. Check if the environment variable is set correctly:
   ```bash
   echo $CAFFEINE_MODE
   ```

2. Verify the log file for errors:
   ```bash
   cat state/caffeine_mode.log
   ```

3. Check if the `/api/caffeine` endpoint is accessible:
   ```bash
   curl -X GET http://localhost:8000/api/caffeine
   ```

### Ping Failures

Common reasons for ping failures include:
- Incorrect domain or port configuration
- Firewall or network restrictions
- Server unavailability
- DNS resolution issues

Check the log file for specific error messages and verify your network configuration.