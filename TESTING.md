# Discord Bot Testing & Deployment Guide

This document provides comprehensive instructions for testing and deploying the Discord bot using the new automated testing framework.

## Table of Contents

- [Overview](#overview)
- [Environment Variables for Staging](#environment-variables-for-staging)
- [Local Testing](#local-testing)
- [CI/CD Pipeline](#cicd-pipeline)
- [Railway Staging Setup](#railway-staging-setup)
- [Deployment Process](#deployment-process)
- [Troubleshooting](#troubleshooting)

## Overview

We've implemented a comprehensive testing strategy with multiple layers:

- **Unit Tests**: Database operations, command parsing, AI response filtering
- **Integration Tests**: Full command workflows, database state verification
- **Functional Tests**: Bot initialization, API integration mocking
- **Security Tests**: Code analysis, vulnerability scanning
- **Smoke Tests**: Basic functionality verification

## Environment Variables for Staging

### Required Changes for Develop Branch

The following environment variables need to be configured differently for your staging environment:

#### Core Bot Configuration

```env
# Use a separate test bot token
DISCORD_TOKEN=your_staging_bot_token_here

# Use separate staging database
DATABASE_URL=your_staging_postgresql_url

# API Keys (can reuse production keys with quotas)
GOOGLE_API_KEY=your_google_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
YOUTUBE_API_KEY=your_youtube_api_key
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret
```

#### Discord Channel IDs (Create Test Channels)

```env
# Create separate channels in your test server
GUILD_ID=your_test_server_id
VIOLATION_CHANNEL_ID=your_test_violations_channel
MOD_ALERT_CHANNEL_ID=your_test_mod_alerts_channel
TWITCH_HISTORY_CHANNEL_ID=your_test_twitch_history_channel
YOUTUBE_HISTORY_CHANNEL_ID=your_test_youtube_history_channel
RECOMMEND_CHANNEL_ID=your_test_recommendations_channel
```

### Setting Up Test Discord Server

1. Create a new Discord server for testing
2. Create the following channels:
   - `#test-violations` (for strike testing)
   - `#test-mod-alerts` (for mod notifications)
   - `#test-recommendations` (for game recommendations)
   - `#test-twitch-history` (for Twitch updates)
   - `#test-youtube-history` (for YouTube updates)
3. Invite your staging bot to this server
4. Get the channel IDs and update your environment variables

## Local Testing

### Prerequisites

1. **Python 3.11+** installed
2. **PostgreSQL** (optional, tests will use mocks if unavailable)
3. **Virtual environment** recommended

### Quick Start

```bash
# Make the test script executable
chmod +x run_tests.sh

# Run all tests
./run_tests.sh

# Run specific test suites
./run_tests.sh --database    # Database tests only
./run_tests.sh --commands    # Command tests only
./run_tests.sh --ai          # AI integration tests only

# Run with coverage and linting
./run_tests.sh --coverage --lint --security

# Run smoke test to verify bot startup
./run_tests.sh --smoke
```

### Manual Testing Setup

```bash
# Install test dependencies
pip install -r tests/requirements-test.txt

# Set up test environment
export TEST_MODE=true
export DISCORD_TOKEN="test_token"
export DATABASE_URL="postgresql://test:test@localhost/test_db"

# Run tests with pytest
python -m pytest tests/ -v
python -m pytest tests/test_database.py -v
python -m pytest tests/test_commands.py -v
python -m pytest tests/test_ai_integration.py -v
```

### Test Configuration

The `test_config.py` file provides utilities for:

- Environment variable management
- Mock service responses
- Database connection handling
- CI/CD environment detection

## CI/CD Pipeline

### GitHub Actions Workflow

The `.github/workflows/develop-tests.yml` file defines a comprehensive CI/CD pipeline that runs on:

- **Push to develop branch**
- **Pull requests to develop branch**

#### Pipeline Stages

1. **Test Stage**
   - Sets up Python 3.11 and PostgreSQL
   - Installs dependencies
   - Runs database, command, and AI integration tests
   - Generates coverage reports
   - Runs smoke test for basic functionality

2. **Lint Stage**
   - Code formatting with Black
   - Import sorting with isort
   - Linting with flake8
   - Type checking with mypy

3. **Security Stage**
   - Security analysis with Bandit
   - Vulnerability scanning with Safety

4. **Deployment Readiness**
   - Validates Railway configuration
   - Checks required files
   - Verifies environment variables template

### Required GitHub Secrets

Add these secrets to your GitHub repository:

```text
TEST_DISCORD_TOKEN        # Staging bot token
GOOGLE_API_KEY            # Google API key
ANTHROPIC_API_KEY         # Anthropic API key  
YOUTUBE_API_KEY           # YouTube API key
TWITCH_CLIENT_ID          # Twitch client ID
TWITCH_CLIENT_SECRET      # Twitch client secret
```

## Railway Staging Setup

### 1. Create Staging Environment

1. Go to your Railway project
2. Create a new environment called "staging"
3. Connect it to your `develop` branch

### 2. Configure Staging Environment Variables

In Railway staging environment, set:

```env
# Bot Configuration
DISCORD_TOKEN=your_staging_bot_token
DATABASE_URL=${{ Postgres.DATABASE_URL }}  # Railway PostgreSQL

# API Keys (same as production)
GOOGLE_API_KEY=your_google_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
YOUTUBE_API_KEY=your_youtube_api_key
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret

# Test Environment Channel IDs
GUILD_ID=123456789012345678
VIOLATION_CHANNEL_ID=123456789012345679
MOD_ALERT_CHANNEL_ID=123456789012345680
TWITCH_HISTORY_CHANNEL_ID=123456789012345681
YOUTUBE_HISTORY_CHANNEL_ID=123456789012345682
RECOMMEND_CHANNEL_ID=123456789012345683
```

### 3. Database Setup

Railway will automatically create a PostgreSQL instance for staging. The database will be initialized automatically when the bot starts.

## Deployment Process

### Development Workflow

1. **Local Development**

   ```bash
   # Create feature branch from develop
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   
   # Make changes and test locally
   ./run_tests.sh --coverage --lint
   
   # Commit and push
   git add .
   git commit -m "Add: your feature description"
   git push origin feature/your-feature-name
   ```

2. **Pull Request**
   - Create pull request to `develop` branch
   - Automated tests will run via GitHub Actions
   - All tests must pass before merging

3. **Staging Deployment**
   - Merge PR into `develop` branch
   - Railway automatically deploys to staging environment
   - Test functionality in staging environment

4. **Production Deployment**
   - When staging tests pass, merge `develop` into `main`
   - Railway automatically deploys to production
   - Monitor for issues

### Pre-deployment Checklist

- [ ] All unit tests pass locally
- [ ] All integration tests pass locally  
- [ ] Code formatting and linting checks pass
- [ ] Security scans show no critical issues
- [ ] Environment variables are configured for staging
- [ ] Database migrations (if any) are tested
- [ ] Bot functionality tested in staging Discord server

## Troubleshooting

### Common Issues

#### Tests Failing Locally

```bash
# Check environment variables
python test_config.py

# Run specific test with verbose output
./run_tests.sh --database --verbose

# Check test dependencies
pip install -r tests/requirements-test.txt
```

#### CI/CD Pipeline Failures

1. **Database Connection Issues**
   - Verify PostgreSQL service is running in GitHub Actions
   - Check DATABASE_URL format

2. **API Key Issues**
   - Verify GitHub secrets are set correctly
   - Check API key permissions and quotas

3. **Import Errors**
   - Verify all dependencies in requirements.txt
   - Check Python path configuration

#### Railway Deployment Issues

1. **Build Failures**

   ```bash
   # Check Railway logs
   railway logs
   
   # Verify Procfile and start command
   cat Live/Procfile
   ```

2. **Runtime Errors**

   ```bash
   # Check environment variables
   railway variables
   
   # Verify database connection
   railway connect
   ```

3. **Discord Bot Not Responding**
   - Verify bot token is correct
   - Check bot permissions in Discord server
   - Verify channel IDs are correct

### Getting Help

1. **Check Logs**
   - Railway: `railway logs`
   - Local: Check console output
   - GitHub Actions: Check workflow run details

2. **Validate Configuration**

   ```bash
   # Test environment setup
   python test_config.py
   
   # Run smoke test
   ./run_tests.sh --smoke
   ```

3. **Debug Mode**

   ```bash
   # Run with verbose output
   ./run_tests.sh --verbose
   
   # Run specific failing test
   python -m pytest tests/test_specific.py::TestClass::test_method -vv
   ```

## Test Coverage Goals

- **Database Operations**: >95% coverage
- **Command Handlers**: >90% coverage
- **AI Integration**: >85% coverage
- **Message Processing**: >90% coverage
- **Error Handling**: >80% coverage

## Performance Benchmarks

- **Test Suite Runtime**: <5 minutes locally, <10 minutes in CI
- **Bot Startup Time**: <30 seconds
- **Database Query Performance**: <100ms average
- **AI Response Time**: <5 seconds average

---

For questions or issues with the testing framework, please check the troubleshooting section or create an issue in the repository.
