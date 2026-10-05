#!/bin/sh
# Placeholder alert hook: replace the echo with your chat/e-mail notifier.
# Never hardcode a webhook secret here - read it from the environment.
echo "[$(date -Iseconds)] revenue-change-tracker job '$1' failed" >&2
