#!/bin/bash

# Git History Reset Script
# This will create a completely fresh git history with a single initial commit

set -e

echo "========================================="
echo "   Git History Reset Script"
echo "========================================="
echo ""
echo "⚠️  WARNING: This will completely reset git history!"
echo "All commit history will be lost."
echo ""

# Check current branch
CURRENT_BRANCH=$(git branch --show-current)
echo "Current branch: $CURRENT_BRANCH"

# Get remote URL
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [ -z "$REMOTE_URL" ]; then
    echo "❌ No remote origin found"
    exit 1
fi
echo "Remote URL: $REMOTE_URL"
echo ""

# Create backup of .git directory
echo "📦 Creating backup of git history..."
cp -r .git .git-backup-$(date +%Y%m%d-%H%M%S)
echo "✅ Backup created"
echo ""

# Remove git directory
echo "🗑️  Removing current git history..."
rm -rf .git
echo "✅ Git history removed"
echo ""

# Initialize new repository
echo "🎉 Initializing fresh repository..."
git init
echo "✅ Repository initialized"
echo ""

# Add all files
echo "📝 Adding all files..."
git add .
echo "✅ Files staged"
echo ""

# Create initial commit
echo "💫 Creating initial commit..."
git commit -m "Initial open source release

Jaces - Personal data collection and analysis platform

Features:
- iOS app for continuous data collection (location, health, audio)
- macOS app for activity monitoring
- Web dashboard for data visualization  
- Python data processing pipeline
- OAuth integration for Google and Notion
- Real-time data syncing with background support

Architecture:
- Monorepo structure with clear separation of concerns
- Configuration-driven source and signal definitions
- Stream-based data processing
- Docker-based development environment

Technologies:
- Swift/SwiftUI for native apps
- SvelteKit for web application
- Python/FastAPI for backend services
- PostgreSQL, Redis, MinIO for data storage
- Celery for task scheduling

Documentation:
- See README.md for setup instructions
- See CONTRIBUTING.md for development guidelines
- See SECURITY.md for security policies

License: MIT"

echo "✅ Initial commit created"
echo ""

# Add remote
echo "🔗 Adding remote origin..."
git remote add origin $REMOTE_URL
echo "✅ Remote added"
echo ""

# Rename branch to main
echo "🌿 Setting main branch..."
git branch -M main
echo "✅ Branch set to main"
echo ""

echo "========================================="
echo "   ✅ Git History Reset Complete!"
echo "========================================="
echo ""
echo "Your repository now has a single initial commit."
echo "All previous history has been removed."
echo ""
echo "To push to GitHub (this will REPLACE all remote history):"
echo "  git push -u origin main --force"
echo ""
echo "⚠️  WARNING: Force pushing will:"
echo "  - Delete all commit history on GitHub"
echo "  - Break any open PRs and issues"  
echo "  - Require all contributors to re-clone"
echo ""
echo "Backup of old .git directory saved with timestamp"