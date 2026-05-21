"""Pure string-rendering helpers for the config files the installer writes.

Every method is a `@staticmethod` taking primitives and returning a
string. No filesystem or subprocess in here — that lives in
`installer.py`. This split makes the rendered output trivially
testable.
"""

from __future__ import annotations

from .constants import __version__


class Templates:
    @staticmethod
    def mariadb_cnf() -> str:
        return (
            "[mysqld]\n"
            "character-set-client-handshake = FALSE\n"
            "character-set-server = utf8mb4\n"
            "collation-server = utf8mb4_unicode_ci\n"
            "\n"
            "# Slow log — Barista reads this\n"
            "slow_query_log = 1\n"
            "slow_query_log_file = /var/log/mysql/slow.log\n"
            "long_query_time = 0.5\n"
            "log_queries_not_using_indexes = 0\n"
            "\n"
            "# Bin log (off by default; Barista flips this on via Settings)\n"
            "# log_bin = /var/lib/mysql/binlog\n"
            "# binlog_format = ROW\n"
            "# expire_logs_days = 7\n"
            "\n"
            "[client]\n"
            "default-character-set = utf8mb4\n"
        )

    @staticmethod
    def traefik_yml(network: str, email: str, domain: str) -> str:
        base = (
            "entryPoints:\n"
            "  web:\n"
            "    address: \":80\"\n"
            "  websecure:\n"
            "    address: \":443\"\n"
            "\n"
            "providers:\n"
            "  docker:\n"
            "    exposedByDefault: false\n"
            f"    network: {network}\n"
            "  file:\n"
            "    directory: /etc/traefik\n"
            "    watch: true\n"
            "\n"
            "api:\n"
            "  dashboard: false\n"
        )
        if email and not domain.endswith(".localhost"):
            base += (
                "\ncertificatesResolvers:\n"
                "  le:\n"
                "    acme:\n"
                f"      email: {email}\n"
                "      storage: /data/acme.json\n"
                "      tlsChallenge: {}\n"
            )
        return base

    @staticmethod
    def env_file(*, mariadb_pw: str, barista_pw: str, manager_token: str,
                  timezone: str, port_start: int, domain: str,
                  email: str, network: str) -> str:
        return (
            f"BARISTA_VERSION={__version__}\n"
            f"BARISTA_MARIADB_ROOT_PASSWORD={mariadb_pw}\n"
            f"BARISTA_ADMIN_PASSWORD={barista_pw}\n"
            f"BARISTA_DOCKER_MANAGER_TOKEN={manager_token}\n"
            f"BARISTA_TIMEZONE={timezone}\n"
            f"BARISTA_HTTP_PORT_RANGE_START={port_start}\n"
            f"BARISTA_DOMAIN={domain}\n"
            f"BARISTA_LETSENCRYPT_EMAIL={email}\n"
            f"BARISTA_DOCKER_NETWORK={network}\n"
        )

    @staticmethod
    def compose_yml(*, home: str, network: str, no_traefik: bool) -> str:
        body = [
            "name: barista",
            "networks:",
            f"  {network}:",
            f"    name: {network}",
            # Pre-created by install.py before `compose up`; compose
            # must treat it as external or it will refuse to adopt the
            # un-labelled network and fail.
            "    external: true",
            "",
            "services:",
            "  mariadb:",
            "    container_name: barista-mariadb",
            "    image: mariadb:11",
            "    restart: unless-stopped",
            f"    networks: [{network}]",
            "    environment:",
            "      MARIADB_ROOT_PASSWORD: ${BARISTA_MARIADB_ROOT_PASSWORD}",
            "    volumes:",
            f"      - {home}/data/mariadb:/var/lib/mysql",
            f"      - {home}/data/mariadb-logs:/var/log/mysql",
            f"      - {home}/config/mariadb/my.cnf:/etc/mysql/conf.d/my.cnf:ro",
            "    ports:",
            "      - \"127.0.0.1:13306:3306\"",
            "",
            "  redis:",
            "    container_name: barista-redis",
            "    image: redis:7-alpine",
            "    restart: unless-stopped",
            f"    networks: [{network}]",
            "    volumes:",
            f"      - {home}/data/redis:/data",
            "",
            "  docker-manager:",
            "    container_name: barista-docker-manager",
            "    image: barista/docker-manager:local",
            "    build:",
            f"      context: {home}/src/docker-manager",
            "    restart: unless-stopped",
            f"    networks: [{network}]",
            "    environment:",
            "      BARISTA_DOCKER_MANAGER_TOKEN: ${BARISTA_DOCKER_MANAGER_TOKEN}",
            f"      NETWORK: {network}",
            "      BARISTA_DATA_ROOT: /data",
            "      BARISTA_TRAEFIK_DYNAMIC: /etc/traefik/dynamic.yml",
            "    volumes:",
            "      - /var/run/docker.sock:/var/run/docker.sock",
            f"      - {home}/data:/data",
            f"      - {home}/config/traefik:/etc/traefik",
            "    labels:",
            "      barista.role: docker-manager",
        ]
        if not no_traefik:
            body += [
                "",
                "  traefik:",
                "    container_name: barista-traefik",
                # v3.7 is the first tag with a Docker client new enough
                # to talk to Docker 28+ daemons. Earlier (3.1) shipped
                # an API-1.24 client and just spammed
                # `client version 1.24 is too old` until the box fell
                # over; routes were never installed.
                "    image: traefik:v3.7",
                "    restart: unless-stopped",
                f"    networks: [{network}]",
                "    ports:",
                "      - \"80:80\"",
                "      - \"443:443\"",
                "    volumes:",
                f"      - {home}/config/traefik:/etc/traefik:ro",
                f"      - {home}/data/traefik:/data",
                "      - /var/run/docker.sock:/var/run/docker.sock:ro",
            ]
        return "\n".join(body) + "\n"
