#!/usr/bin/env bash
set -euo pipefail

awslocal s3 mb s3://hf-cdss-data || true
