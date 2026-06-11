#!/usr/bin/env bash
set -euo pipefail

awslocal s3 mb s3://hf-cdss-raw || true
awslocal s3 mb s3://hf-cdss-processed || true
