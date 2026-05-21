"""Tests for the Python installer.

Stdlib-only, no external deps. Imports the `installer/` package
directly — post-refactor, `install.py` at the repo root is just a
thin bootstrap and the real code lives here as a package.
"""

from __future__ import annotations

import io
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

import installer as install  # kept as `install` so the test reads naturally
from installer.cli import build_install_steps
from installer.cli import main as cli_main

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def quiet_logger():
    """A Logger that writes to an in-memory buffer (no terminal noise)."""
    buf = io.StringIO()
    log = install.Logger(stream=buf, isatty=False)
    log.buffer = buf
    return log


@pytest.fixture
def cfg(tmp_path):
    """A Config whose state lives under tmp_path."""
    return install.Config(
        barista_home=tmp_path / ".barista",
        domain="test.localhost",
        port_start=19000,
        no_traefik=False,
        dry_run=False,
        script_dir=tmp_path / "checkout",
    )


@pytest.fixture
def fake_docker(quiet_logger):
    """A Docker stub that captures run() calls and answers queries."""
    d = install.Docker(quiet_logger, dry_run=False)
    d.run = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    d.installed = MagicMock(return_value=True)
    d.daemon_up = MagicMock(return_value=True)
    d.network_exists = MagicMock(return_value=False)
    d.container_running = MagicMock(return_value=False)
    return d


@pytest.fixture
def installer(cfg, quiet_logger, fake_docker):
    return install.Installer(cfg, quiet_logger, docker=fake_docker)


# ===========================================================================
# Config
# ===========================================================================

class TestConfig:
    def test_defaults(self):
        c = install.Config.from_argv([])
        assert c.mode == "install"
        assert c.domain == install.DEFAULTS_DOMAIN
        assert c.port_start == install.DEFAULTS_PORT_START
        assert c.dry_run is False
        assert c.no_traefik is False

    def test_flags_parsed(self):
        c = install.Config.from_argv([
            "--domain", "shop.example.com",
            "--email", "ops@example.com",
            "--port-start", "20000",
            "--no-traefik",
            "--dry-run",
        ])
        assert c.domain == "shop.example.com"
        assert c.email == "ops@example.com"
        assert c.port_start == 20000
        assert c.no_traefik is True
        assert c.dry_run is True

    def test_uninstall_mode(self):
        assert install.Config.from_argv(["--uninstall"]).mode == "uninstall"

    def test_purge_mode(self):
        assert install.Config.from_argv(["--purge"]).mode == "purge"

    def test_mutually_exclusive_modes(self):
        with pytest.raises(SystemExit):
            install.Config.from_argv(["--uninstall", "--purge"])

    def test_derived_paths(self, tmp_path):
        c = install.Config(barista_home=tmp_path / "home")
        assert c.state_dir == tmp_path / "home" / ".state"
        assert c.env_file == tmp_path / "home" / ".env"
        assert c.compose_file == tmp_path / "home" / "docker-compose.yml"
        assert c.src_dir == tmp_path / "home" / "src" / "docker-manager"

    def test_data_dirs_include_state(self, tmp_path):
        c = install.Config(barista_home=tmp_path / "home")
        assert c.state_dir in c.data_dirs


# ===========================================================================
# Templates
# ===========================================================================

class TestTemplates:
    def test_mariadb_cnf_has_slow_log(self):
        text = install.Templates.mariadb_cnf()
        assert "slow_query_log = 1" in text
        assert "utf8mb4" in text
        # binlog must be commented out by default
        assert "# log_bin" in text

    def test_traefik_yml_basic(self):
        text = install.Templates.traefik_yml(
            network="barista-net", email="", domain="barista.localhost"
        )
        assert "entryPoints" in text
        assert "network: barista-net" in text
        # no Let's Encrypt block for .localhost
        assert "certificatesResolvers" not in text

    def test_traefik_yml_with_letsencrypt(self):
        text = install.Templates.traefik_yml(
            network="barista-net", email="ops@example.com",
            domain="barista.example.com",
        )
        assert "certificatesResolvers" in text
        assert "ops@example.com" in text

    def test_traefik_yml_skips_le_on_localhost(self):
        """Even with an email, .localhost domains shouldn't get LE."""
        text = install.Templates.traefik_yml(
            network="barista-net", email="ops@example.com",
            domain="barista.localhost",
        )
        assert "certificatesResolvers" not in text

    def test_env_file_contents(self):
        text = install.Templates.env_file(
            mariadb_pw="m", barista_pw="b", manager_token="t",
            timezone="UTC", port_start=18000, domain="d",
            email="", network="n",
        )
        for line in (
            "BARISTA_MARIADB_ROOT_PASSWORD=m",
            "BARISTA_ADMIN_PASSWORD=b",
            "BARISTA_DOCKER_MANAGER_TOKEN=t",
            "BARISTA_HTTP_PORT_RANGE_START=18000",
            "BARISTA_DOMAIN=d",
            "BARISTA_DOCKER_NETWORK=n",
        ):
            assert line in text

    def test_compose_yml_includes_all_services(self):
        text = install.Templates.compose_yml(
            home="/x", network="barista-net", no_traefik=False
        )
        for name in ("mariadb", "redis", "docker-manager", "traefik"):
            assert f"  {name}:" in text

    def test_compose_yml_marks_network_external(self):
        """install.py pre-creates the network before `compose up`, so
        compose has to treat it as external. Otherwise compose refuses
        to adopt the un-labelled network and fails on Ubuntu/Docker
        29+ with: 'network ... was found but has incorrect label
        com.docker.compose.network'."""
        text = install.Templates.compose_yml(
            home="/x", network="barista-net", no_traefik=False
        )
        network_block = text.split("services:")[0]
        assert "external: true" in network_block

    def test_compose_yml_omits_traefik_when_disabled(self):
        text = install.Templates.compose_yml(
            home="/x", network="barista-net", no_traefik=True
        )
        assert "barista-traefik" not in text
        # the others are still present
        for name in ("mariadb", "redis", "docker-manager"):
            assert f"  {name}:" in text

    def test_compose_yml_docker_manager_has_no_published_ports(self):
        """The whole point: docker-manager must not be reachable from
        the host."""
        text = install.Templates.compose_yml(
            home="/x", network="barista-net", no_traefik=False
        )
        # find the docker-manager block and confirm no `ports:` line
        dm_block = text.split("  docker-manager:")[1].split("\n  traefik:")[0]
        assert "ports:" not in dm_block


# ===========================================================================
# Installer — individual steps
# ===========================================================================

class TestEnsureDirs:
    def test_creates_all_data_dirs(self, installer):
        installer.ensure_dirs()
        for d in installer.cfg.data_dirs:
            assert d.is_dir(), f"missing dir: {d}"

    def test_is_idempotent(self, installer):
        installer.ensure_dirs()
        installer.ensure_dirs()  # would raise on collision otherwise
        for d in installer.cfg.data_dirs:
            assert d.is_dir()


class TestWriteEnv:
    def test_creates_env_file_with_secrets(self, installer, monkeypatch):
        # Installer.write_env reads random_hex through the utils
        # submodule (so tests can patch it here without rebinding
        # imports in every caller).
        monkeypatch.setattr(install.utils, "random_hex",
                             lambda n=16: "x" * n)
        installer.ensure_dirs()
        installer.write_env()
        text = installer.cfg.env_file.read_text()
        assert "BARISTA_MARIADB_ROOT_PASSWORD=" in text
        assert "BARISTA_DOCKER_MANAGER_TOKEN=" in text

    def test_does_not_overwrite_existing_env(self, installer):
        installer.ensure_dirs()
        installer.cfg.env_file.write_text("BARISTA_ADMIN_PASSWORD=keep-me\n")
        installer.write_env()
        assert installer.cfg.env_file.read_text() == \
            "BARISTA_ADMIN_PASSWORD=keep-me\n"

    def test_env_file_is_chmod_600(self, installer):
        if sys.platform == "win32":
            pytest.skip("permission bits irrelevant on Windows")
        installer.ensure_dirs()
        installer.write_env()
        mode = installer.cfg.env_file.stat().st_mode & 0o777
        assert mode == 0o600


class TestWriteConfigs:
    def test_write_mariadb_conf(self, installer):
        installer.ensure_dirs()
        installer.write_mariadb_conf()
        text = (installer.cfg.barista_home / "config" / "mariadb" / "my.cnf").read_text()
        assert "slow_query_log" in text

    def test_write_traefik_conf(self, installer):
        installer.ensure_dirs()
        installer.write_traefik_conf()
        cfg = installer.cfg.barista_home / "config" / "traefik"
        assert (cfg / "traefik.yml").exists()
        assert (cfg / "dynamic.yml").exists()


class TestWriteCompose:
    def test_write_compose_creates_file(self, installer):
        installer.ensure_dirs()
        installer.write_compose()
        assert installer.cfg.compose_file.exists()
        text = installer.cfg.compose_file.read_text()
        assert "barista-mariadb" in text
        assert "barista-docker-manager" in text


class TestStageDockerManager:
    def test_copies_from_local_checkout_when_present(self, installer, tmp_path):
        local = installer.cfg.script_dir / "docker-manager"
        local.mkdir(parents=True)
        (local / "Dockerfile").write_text("FROM x")
        (local / "src").mkdir()
        (local / "src" / "app.py").write_text("# app")

        installer.ensure_dirs()
        installer.stage_docker_manager()

        dst = installer.cfg.src_dir
        assert (dst / "Dockerfile").exists()
        assert (dst / "src" / "app.py").read_text() == "# app"


class TestPreflight:
    def test_passes_with_docker_present(self, installer):
        installer.preflight()   # docker is mocked as installed + up

    def test_fails_when_docker_missing(self, installer, monkeypatch):
        installer.docker.installed = MagicMock(return_value=False)
        # On macOS we point at Desktop without installing.
        if sys.platform == "darwin":
            with pytest.raises(install.InstallerError):
                installer.preflight()

    def test_fails_when_daemon_down(self, installer):
        installer.docker.daemon_up = MagicMock(return_value=False)
        with pytest.raises(install.InstallerError):
            installer.preflight()


# ===========================================================================
# StepRunner
# ===========================================================================

class TestStepRunner:
    def test_runs_each_step_in_order(self, tmp_path, quiet_logger):
        order = []
        r = install.StepRunner(tmp_path / "state", quiet_logger)
        r.add("a", lambda: order.append("a"))
        r.add("b", lambda: order.append("b"))
        r.add("c", lambda: order.append("c"))
        r.run()
        assert order == ["a", "b", "c"]

    def test_marks_steps_as_done(self, tmp_path, quiet_logger):
        r = install.StepRunner(tmp_path / "state", quiet_logger)
        r.add("a", lambda: None)
        r.run()
        assert (tmp_path / "state" / "a.done").exists()

    def test_skips_completed_steps(self, tmp_path, quiet_logger):
        state = tmp_path / "state"
        state.mkdir()
        (state / "a.done").touch()
        count = []
        r = install.StepRunner(state, quiet_logger)
        r.add("a", lambda: count.append(1))
        r.run()
        assert count == []   # never ran

    def test_stops_on_failure(self, tmp_path, quiet_logger):
        order = []
        def fail(): raise RuntimeError("boom")
        r = install.StepRunner(tmp_path / "state", quiet_logger)
        r.add("a", lambda: order.append("a"))
        r.add("b", fail)
        r.add("c", lambda: order.append("c"))
        with pytest.raises(RuntimeError):
            r.run()
        assert order == ["a"]   # c was never reached

    def test_does_not_mark_failed_step(self, tmp_path, quiet_logger):
        def fail(): raise RuntimeError
        r = install.StepRunner(tmp_path / "state", quiet_logger)
        r.add("a", fail)
        with pytest.raises(RuntimeError):
            r.run()
        assert not (tmp_path / "state" / "a.done").exists()

    def test_dry_run_does_not_write_markers(self, tmp_path, quiet_logger):
        r = install.StepRunner(tmp_path / "state", quiet_logger, dry_run=True)
        r.add("a", lambda: None)
        r.run()
        assert not (tmp_path / "state" / "a.done").exists()


# ===========================================================================
# main()
# ===========================================================================

class TestMain:
    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as ei:
            cli_main(["--help"])
        assert ei.value.code == 0

    def test_uninstall_runs_uninstall_only(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BARISTA_HOME", str(tmp_path / ".barista"))
        called = []
        monkeypatch.setattr(install.Installer, "uninstall",
                             lambda self: called.append("uninstall"))
        rc = cli_main(["--uninstall"])
        assert rc == 0
        assert called == ["uninstall"]


# ===========================================================================
# parse env helper
# ===========================================================================

class TestParseEnvFile:
    def test_parses_lines(self, tmp_path):
        f = tmp_path / "env"
        f.write_text("FOO=bar\n# comment\n\nBAZ=qux\n")
        out = install.parse_env_file(f)
        assert out == {"FOO": "bar", "BAZ": "qux"}

    def test_missing_file_returns_empty(self, tmp_path):
        assert install.parse_env_file(tmp_path / "nope") == {}

    def test_handles_equals_in_value(self, tmp_path):
        f = tmp_path / "env"
        f.write_text("URL=http://x?y=z\n")
        assert install.parse_env_file(f) == {"URL": "http://x?y=z"}


# ===========================================================================
# build_install_steps — the public contract that defines the install order
# ===========================================================================

class TestStepOrder:
    def test_step_order_is_stable(self, installer):
        steps = build_install_steps(installer)
        names = [s[0] for s in steps]
        assert names == [
            "preflight",
            "ensure_dirs",
            "write_env",
            "write_mariadb_conf",
            "write_traefik_conf",
            "stage_docker_manager",
            "write_compose",
            "compose_up",
            "bootstrap_cp",
        ]


# ===========================================================================
# Bench (extracted from Installer)
# ===========================================================================

class TestBench:
    def test_installer_owns_a_bench(self, installer):
        assert isinstance(installer.bench, install.Bench)

    def test_bench_dir_lives_under_barista_home(self, installer):
        expected = installer.cfg.barista_home / "data" / "benches" / "default"
        assert installer.bench.dir == expected

    def test_bench_container_name_constant(self, installer):
        assert installer.bench.name == install.BENCH_CONTAINER_NAME
        assert installer.bench.name == "barista-bench-default"

    def test_init_cmd_rewrites_venv_shebangs(self):
        cmd = install.Bench._bench_init_cmd()
        # the move target is /home/frappe/bench/env, so the sed must
        # rewrite the throw-away /tmp/b/env path to that
        assert "/tmp/b/env" in cmd
        assert install.BENCH_RUNTIME_PATH + "/env" in cmd
        assert "find /work/env/bin" in cmd
        assert "/work/env/pyvenv.cfg" in cmd

    def test_traefik_labels_off_with_no_traefik(self, tmp_path, quiet_logger,
                                                  fake_docker):
        cfg = install.Config(barista_home=tmp_path / "h", no_traefik=True)
        bench = install.Bench(cfg, quiet_logger, fake_docker)
        assert bench._traefik_labels(env={}) == []

    def test_traefik_labels_add_le_when_email_and_real_domain(
        self, tmp_path, quiet_logger, fake_docker,
    ):
        cfg = install.Config(
            barista_home=tmp_path / "h",
            email="ops@example.com",
            domain="shop.example.com",
        )
        bench = install.Bench(cfg, quiet_logger, fake_docker)
        labels = bench._traefik_labels(env={"BARISTA_DOMAIN": "shop.example.com"})
        assert any("certresolver=le" in lbl for lbl in labels)

    def test_traefik_labels_skip_le_on_localhost(
        self, tmp_path, quiet_logger, fake_docker,
    ):
        cfg = install.Config(
            barista_home=tmp_path / "h",
            email="ops@example.com",
            domain="barista.localhost",
        )
        bench = install.Bench(cfg, quiet_logger, fake_docker)
        labels = bench._traefik_labels(env={"BARISTA_DOMAIN": "barista.localhost"})
        assert not any("certresolver" in lbl for lbl in labels)

    def test_bootstrap_force_removes_stale_container_after_init(
        self, tmp_path, quiet_logger, fake_docker, monkeypatch,
    ):
        """If we just (re)created the host bench dir, any pre-existing
        container with the bench name has a stale bind-mount pointing at
        the previous inode — so bootstrap() must force-remove it before
        the keep-alive step, otherwise `docker exec ... bench …` runs
        against an empty mount and dies with FileNotFoundError.
        """
        cfg = install.Config(barista_home=tmp_path / "h", domain="test.localhost")
        cfg.barista_home.mkdir()
        cfg.env_file.write_text(
            "BARISTA_DOMAIN=test.localhost\n"
            "BARISTA_ADMIN_PASSWORD=x\n"
            "BARISTA_MARIADB_ROOT_PASSWORD=y\n"
            "BARISTA_DOCKER_MANAGER_TOKEN=t\n"
            "BARISTA_HTTP_PORT_RANGE_START=19000\n"
        )
        bench = install.Bench(cfg, quiet_logger, fake_docker)

        # Pretend the previous keep-alive container is still up but the
        # host bench dir is fresh (sites/ does not exist).
        fake_docker.container_running.return_value = True
        monkeypatch.setattr(bench, "_init", MagicMock())
        monkeypatch.setattr(bench, "_install_barista_app", MagicMock())
        monkeypatch.setattr(bench, "_app_present", lambda: True)
        monkeypatch.setattr(bench, "_site_present", lambda: True)
        monkeypatch.setattr(bench, "_ensure_serving", MagicMock())

        bench.bootstrap()

        # The stale container must have been force-removed.
        rm_calls = [c.args[0] for c in fake_docker.run.call_args_list
                     if c.args[0][:3] == ["docker", "rm", "-f"]]
        assert ["docker", "rm", "-f", bench.name] in rm_calls

    def test_bootstrap_skips_rm_when_bench_dir_already_populated(
        self, tmp_path, quiet_logger, fake_docker, monkeypatch,
    ):
        """Conversely, a normal re-run (sites/ already exists) must NOT
        rip the running keep-alive container out from under us."""
        cfg = install.Config(barista_home=tmp_path / "h")
        cfg.barista_home.mkdir()
        cfg.env_file.write_text("BARISTA_DOMAIN=test.localhost\n")
        bench = install.Bench(cfg, quiet_logger, fake_docker)
        bench.dir.mkdir(parents=True, exist_ok=True)
        (bench.dir / "sites").mkdir()  # pretend bench is already initialised

        fake_docker.container_running.return_value = True
        monkeypatch.setattr(bench, "_app_present", lambda: True)
        monkeypatch.setattr(bench, "_site_present", lambda: True)
        monkeypatch.setattr(bench, "_ensure_serving", MagicMock())

        bench.bootstrap()

        rm_calls = [c.args[0] for c in fake_docker.run.call_args_list
                     if c.args[0][:3] == ["docker", "rm", "-f"]]
        assert rm_calls == []
