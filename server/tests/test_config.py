"""Deployment configuration validation tests."""

import os
import subprocess
import sys


def load_config(**values: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in ("MARS_ENV", "MARS_SECRET_KEY", "MARS_ALLOWED_ORIGINS", "MARS_ALLOWED_HOSTS"):
        env.pop(key, None)
    env.update(values)
    return subprocess.run(
        [sys.executable, "-c", "import app.config"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_development_defaults_are_valid():
    assert load_config().returncode == 0


def test_production_rejects_default_secret():
    result = load_config(
        MARS_ENV="production",
        MARS_ALLOWED_ORIGINS="https://mars.example.com",
        MARS_ALLOWED_HOSTS="mars.example.com",
    )
    assert result.returncode != 0
    assert "MARS_SECRET_KEY" in result.stderr


def test_production_requires_origins():
    result = load_config(MARS_ENV="production", MARS_SECRET_KEY="x" * 32, MARS_ALLOWED_HOSTS="mars.example.com")
    assert result.returncode != 0
    assert "MARS_ALLOWED_ORIGINS" in result.stderr


def test_wildcard_origin_is_rejected_in_every_environment():
    result = load_config(MARS_ALLOWED_ORIGINS="*")
    assert result.returncode != 0
    assert "wildcard" in result.stderr


def test_production_rejects_http_origin():
    result = load_config(
        MARS_ENV="production",
        MARS_SECRET_KEY="x" * 32,
        MARS_ALLOWED_ORIGINS="http://mars.example.com",
        MARS_ALLOWED_HOSTS="mars.example.com",
    )
    assert result.returncode != 0
    assert "HTTPS" in result.stderr


def test_production_accepts_strong_secret_and_https_origins():
    result = load_config(
        MARS_ENV="production",
        MARS_SECRET_KEY="x" * 32,
        MARS_ALLOWED_ORIGINS="https://mars.example.com,https://admin.example.com",
        MARS_ALLOWED_HOSTS="mars.example.com,admin.example.com",
    )
    assert result.returncode == 0, result.stderr


def test_production_requires_allowed_hosts():
    result = load_config(
        MARS_ENV="production",
        MARS_SECRET_KEY="x" * 32,
        MARS_ALLOWED_ORIGINS="https://mars.example.com",
    )
    assert result.returncode != 0
    assert "MARS_ALLOWED_HOSTS" in result.stderr


def test_wildcard_host_is_rejected():
    result = load_config(MARS_ALLOWED_HOSTS="*")
    assert result.returncode != 0
    assert "wildcard" in result.stderr
