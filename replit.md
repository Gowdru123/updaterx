# Telegram Movie Bot

## Overview
A sophisticated Telegram bot that automatically processes movie/TV show files uploaded to a channel and creates organized posts with metadata, quality information, and download links.

## Current State
- **Status**: Ready to run, waiting for API credentials
- **Language**: Python 3.11
- **Dependencies**: Telethon, Replit DB, asyncio
- **Workflow**: Configured and running

## Features
- **Smart File Processing**: Automatically extracts movie names, quality, language, and episode information
- **Batch Updates**: Groups multiple files for the same movie/series together
- **Episode Tracking**: Handles TV series with season/episode organization
- **Language Detection**: Supports multiple languages (Hindi, English, Tamil, etc.)
- **Quality Recognition**: Detects video quality (720p, 1080p, 4K, etc.)
- **Download Links**: Generates Telegram deep links for easy file access
- **Persistent Storage**: Uses Replit database to maintain state

## Architecture
- **main.py**: Core bot logic with file processing and message handling
- **config.py**: Configuration settings and patterns
- **file_handler.py**: File processing utilities
- **message_formatter.py**: Message formatting functions

## Setup Requirements
The bot needs these environment variables (requested via secrets tool):
- `API_ID`: Telegram API ID from https://my.telegram.org/apps
- `API_HASH`: Telegram API Hash 
- `BOT_TOKEN`: Bot token from @BotFather
- `DB_CHANNEL_ID`: Channel where movies are uploaded (negative number)
- `UPDATE_CHANNEL_ID`: Channel for posting organized movie info (negative number)

## Recent Changes
- Fixed environment variable handling to prevent TypeError crashes
- Added proper error messages for missing credentials
- Configured workflow for console output monitoring
- Set up dependency management with proper versions

## User Preferences
- Prefers clear error messages over crashes
- Values automated file organization
- Needs reliable Telegram integration