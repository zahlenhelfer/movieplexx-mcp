"""Tests for BearerAuth and the `serve` command's transport dispatch."""

from __future__ import annotations

import argparse
from unittest.mock import Mock

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from movieplexx.http import BearerAuth


def _protected_app(token: str) -> Starlette:
    async def ok(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", ok)])
    app.add_middleware(BearerAuth, token=token)
    return app


def test_bearer_auth_rejects_missing_header():
    resp = TestClient(_protected_app("secret")).get("/")
    assert resp.status_code == 401


def test_bearer_auth_rejects_wrong_token():
    resp = TestClient(_protected_app("secret")).get(
        "/", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_bearer_auth_rejects_missing_bearer_prefix():
    resp = TestClient(_protected_app("secret")).get(
        "/", headers={"Authorization": "secret"})
    assert resp.status_code == 401


def test_bearer_auth_accepts_correct_token():
    resp = TestClient(_protected_app("secret")).get(
        "/", headers={"Authorization": "Bearer secret"})
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_cmd_serve_stdio_runs_mcp(monkeypatch):
    from movieplexx import cli, server

    run_mock = Mock()
    monkeypatch.setattr(server.mcp, "run", run_mock)
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)

    assert cli.cmd_serve(argparse.Namespace()) == 0
    run_mock.assert_called_once()


def test_cmd_serve_http_requires_token(monkeypatch):
    from movieplexx import cli

    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

    assert cli.cmd_serve(argparse.Namespace()) == 1


def test_cmd_serve_http_rejects_mismatched_tls_pair(monkeypatch):
    from movieplexx import cli

    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    monkeypatch.setenv("MCP_TLS_CERTFILE", "/tmp/cert.pem")
    monkeypatch.delenv("MCP_TLS_KEYFILE", raising=False)

    assert cli.cmd_serve(argparse.Namespace()) == 1


def test_cmd_serve_http_calls_run_http_server(monkeypatch):
    from movieplexx import cli, http as http_mod

    run_mock = Mock()
    monkeypatch.setattr(http_mod, "run_http_server", run_mock)
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    monkeypatch.delenv("MCP_TLS_CERTFILE", raising=False)
    monkeypatch.delenv("MCP_TLS_KEYFILE", raising=False)

    assert cli.cmd_serve(argparse.Namespace()) == 0
    run_mock.assert_called_once()
    _, kwargs = run_mock.call_args
    assert kwargs["token"] == "secret"
    assert kwargs["tls_certfile"] is None
    assert kwargs["tls_keyfile"] is None


def test_cmd_serve_http_passes_tls_paths(monkeypatch):
    from movieplexx import cli, http as http_mod

    run_mock = Mock()
    monkeypatch.setattr(http_mod, "run_http_server", run_mock)
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    monkeypatch.setenv("MCP_TLS_CERTFILE", "/tmp/cert.pem")
    monkeypatch.setenv("MCP_TLS_KEYFILE", "/tmp/key.pem")

    assert cli.cmd_serve(argparse.Namespace()) == 0
    _, kwargs = run_mock.call_args
    assert kwargs["tls_certfile"] == "/tmp/cert.pem"
    assert kwargs["tls_keyfile"] == "/tmp/key.pem"


def test_cmd_serve_unknown_transport(monkeypatch):
    from movieplexx import cli

    monkeypatch.setenv("MCP_TRANSPORT", "carrier-pigeon")
    assert cli.cmd_serve(argparse.Namespace()) == 1
