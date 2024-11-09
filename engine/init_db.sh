#!/bin/bash

# Use parameter expansion to replace the last part
NEW_DATABASE_URL="${DATABASE_URL%/postgres}/monster_engine"

psql $NEW_DATABASE_URL < engine_schema.sql
