# Job-Specific Environment Variables

This document explains how to configure job-specific environment variables in the daily-manna-email system.

## Overview

The system now supports job-specific environment variables that allow you to customize the environment for each job independently. This is useful when different jobs need different configurations, API keys, or other environment-specific settings.

## Configuration

### JSON Configuration Format

Job-specific environment variables are configured in the `config/dispatch_rules.json` file using the `env` field:

```json
{
  "name": "job-name",
  "time": "06:00",
  "days": ["daily"],
  "commands": [["bash", "scripts/job_script.sh"]],
  "env": {
    "VARIABLE_NAME": "value",
    "ANOTHER_VAR": "another_value"
  }
}
```

### Environment Variable Precedence

Environment variables are resolved in the following order:

1. **System Environment**: Variables from the system environment (`os.environ`)
2. **Global .env File**: Variables from the `.env` file in the project root
3. **Job-Specific Variables**: Variables defined in the job's `env` field (highest precedence)

Job-specific variables override both system and global variables with the same name.

## Examples

### Basic Job with Environment Variables

```json
{
  "name": "daily-send",
  "time": "06:00",
  "days": ["daily"],
  "commands": [["bash", "scripts/run_daily_stateful_ezoe.sh"]],
  "env": {
    "EMAIL_FROM": "daily@example.com",
    "DEBUG_MODE": "1",
    "LOG_LEVEL": "INFO"
  }
}
```

### Multiple Jobs with Different Configurations

```json
[
  {
    "name": "production-job",
    "time": "09:00",
    "days": ["daily"],
    "commands": [["python", "scripts/process_data.py"]],
    "env": {
      "ENVIRONMENT": "production",
      "API_KEY": "prod-key-123",
      "TIMEOUT": "600"
    }
  },
  {
    "name": "staging-job",
    "time": "09:30",
    "days": ["daily"],
    "commands": [["python", "scripts/process_data.py"]],
    "env": {
      "ENVIRONMENT": "staging",
      "API_KEY": "staging-key-456",
      "TIMEOUT": "300"
    }
  }
]
```

### Job Using Global Variables Only

```json
{
  "name": "legacy-job",
  "time": "10:00",
  "days": ["daily"],
  "commands": [["bash", "scripts/legacy_script.sh"]]
  // No env field - will use global .env variables only
}
```

## Global .env File

Create a `.env` file in the project root for shared environment variables:

```
# Global environment variables
DATABASE_URL=postgresql://user:pass@localhost:5432/db
REDIS_URL=redis://localhost:6379/0
SHARED_API_KEY=shared-key-789
```

## Use Cases

### 1. Different API Keys per Job

```json
{
  "name": "weather-job",
  "env": {
    "API_KEY": "weather-service-key"
  }
},
{
  "name": "news-job", 
  "env": {
    "API_KEY": "news-service-key"
  }
}
```

### 2. Environment-Specific Configuration

```json
{
  "name": "staging-deploy",
  "env": {
    "ENVIRONMENT": "staging",
    "DEPLOY_TARGET": "staging-server.example.com"
  }
},
{
  "name": "production-deploy",
  "env": {
    "ENVIRONMENT": "production", 
    "DEPLOY_TARGET": "prod-server.example.com"
  }
}
```

### 3. Debug and Logging Configuration

```json
{
  "name": "debug-job",
  "env": {
    "DEBUG_MODE": "1",
    "LOG_LEVEL": "DEBUG",
    "VERBOSE_OUTPUT": "true"
  }
}
```

## Backward Compatibility

Existing configurations without the `env` field continue to work unchanged. They will use the global environment variables from the `.env` file and system environment.

## Logging

The system logs which environment variables are being used for each job execution:

```
INFO:Job test-job using environment variables: ['GLOBAL_VAR', 'JOB_SPECIFIC_VAR']
```

This helps with debugging and verifying that the correct variables are being applied.

## Security Considerations

- Environment variables are logged as keys only (not values) for security
- Sensitive information should still be handled carefully
- Consider using encrypted secrets for highly sensitive data
- The `.env` file should not be committed to version control

## Migration Guide

### From Global-Only to Job-Specific

1. **Identify jobs that need different configurations**
2. **Add `env` fields to those jobs in `config/dispatch_rules.json`**
3. **Move job-specific variables from `.env` to job configurations**
4. **Keep shared variables in `.env`**

### Example Migration

**Before:**
```json
{
  "name": "job1",
  "env": {
    "SHARED_VAR": "value1",
    "JOB1_VAR": "job1_value"
  }
},
{
  "name": "job2", 
  "env": {
    "SHARED_VAR": "value1",
    "JOB2_VAR": "job2_value"
  }
}
```

**After:**
```json
// .env file
SHARED_VAR=value1

// config/dispatch_rules.json
{
  "name": "job1",
  "env": {
    "JOB1_VAR": "job1_value"
  }
},
{
  "name": "job2",
  "env": {
    "JOB2_VAR": "job2_value"
  }
}
```

## Troubleshooting

### Job Not Using Expected Variables

1. **Check the job configuration** - Verify the `env` field is correctly formatted
2. **Check global .env file** - Ensure shared variables are properly defined
3. **Check logs** - Look for environment variable logging in the job execution logs
4. **Verify precedence** - Remember job-specific variables override global ones

### Variables Not Found

1. **Check variable names** - Ensure no typos in variable names
2. **Check JSON syntax** - Ensure the `env` field is valid JSON
3. **Check file paths** - Ensure `.env` file is in the correct location

## Best Practices

1. **Use descriptive variable names** - Make it clear what each variable is for
2. **Group related variables** - Use consistent naming for related configurations
3. **Document your variables** - Add comments in `.env` for complex configurations
4. **Use environment-specific values** - Different jobs should have appropriate values for their context
5. **Keep secrets secure** - Don't commit sensitive information to version control
6. **Test thoroughly** - Verify that jobs work correctly with their specific configurations

## Advanced Usage

### Conditional Variables

While the system doesn't support conditional logic directly, you can achieve similar results by:

1. **Using different job names** for different conditions
2. **Passing parameters via command arguments** instead of environment variables
3. **Using configuration files** that reference environment variables

### Template Variables

For complex configurations, consider using template variables in your scripts that reference environment variables:

```bash
#!/bin/bash
# script.sh
echo "Running in $ENVIRONMENT environment"
echo "Using API endpoint: $API_ENDPOINT"
```

```json
{
  "name": "templated-job",
  "env": {
    "ENVIRONMENT": "production",
    "API_ENDPOINT": "https://api.example.com/v1"
  }
}