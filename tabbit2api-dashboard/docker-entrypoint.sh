#!/bin/sh
# Initialize SQLite database on first run
npx prisma db push --skip-generate 2>/dev/null || true
exec node server.js
